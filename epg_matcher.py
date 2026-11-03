#!/usr/bin/env python3
"""
Channel-name matcher for the Jio EPG adapter.

The goal is to map playlist channels (M3U) to official Jio EPG source
channels as accurately as possible, and to *never* silently guess when the
evidence is weak.

Matching is staged, strongest evidence first:

    1. exact source id
    2. exact normalised name (strict, then loose)
    3. curated alias from ``channel_aliases.json``
    4. guarded fuzzy match

Every stage can return ``ambiguous`` instead of a match when more than one
source channel is a plausible candidate.  That keeps wrong programme data out
of the guide and gives the review report something actionable to show.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set

# Video quality / encoding markers that carry no identity information.
QUALITY_TOKENS = {
    "hd", "sd", "fhd", "uhd", "4k", "8k", "hdr", "hevc", "x264", "x265",
    "1080p", "720p", "576p", "540p", "504p", "480p", "396p", "360p",
}
# Set-top-box / packaging markers.
FORMAT_TOKENS = {"stb", "mobile", "ott"}
# Only dropped when building the "loose" key, never for the strict key.
# Kept deliberately small: dropping region words like "India" made
# "The Voice TV" collide with "India Voice".
LOOSE_STOPWORDS = {"tv", "channel", "network", "the", "and"}

# Language / region tokens. If a playlist name and a source name disagree on
# these, the match is rejected: "Colors Tamil" must never become
# "Colors Kannada".
LANGUAGE_TOKENS = {
    "tamil", "telugu", "hindi", "kannada", "malayalam", "marathi", "bengali",
    "bangla", "punjabi", "gujarati", "odia", "odiya", "urdu", "bhojpuri",
    "assamese", "english", "sanskrit", "konkani", "kashmiri", "nepali",
    "india", "indian", "asia", "usa", "america", "uk", "canada", "australia",
    "arabia", "global", "world",
}

# Tokens that distinguish sibling channels ("Dangal" vs "Dangal 2",
# "Nickelodeon" vs "Nickelodeon Jr.").  A mismatch on any of these blocks a
# fuzzy match even when the strings look similar.
DISTINCTIVE_TOKENS = {
    "jr", "junior", "kids", "news", "movies", "movie", "music", "sports",
    "gold", "plus", "max", "prime", "action", "classic", "classics", "comedy",
    "crime", "history", "wild", "life", "live", "shopping", "yoga", "bhakti",
    "devotional", "regional", "national", "international", "24x7",
}

BRACKET_RE = re.compile(r"[\(\[\{][^\)\]\}]*[\)\]\}]")
TOKEN_RE = re.compile(r"[a-z0-9]+")
DIGITS_RE = re.compile(r"\d+")

FUZZY_MIN_SCORE = 0.86
FUZZY_MIN_MARGIN = 0.05


def _raw_tokens(name: str) -> List[str]:
    """Lower-case alphanumeric tokens with accents/brackets removed."""
    if not name:
        return []
    text = unicodedata.normalize("NFKD", name)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("&", " and ")
    text = BRACKET_RE.sub(" ", text)
    return TOKEN_RE.findall(text)


def _identity_tokens(name: str) -> List[str]:
    tokens = [
        t for t in _raw_tokens(name)
        if t not in QUALITY_TOKENS and t not in FORMAT_TOKENS
    ]
    # Drop a leading "the" so "The History Channel" == "History Channel".
    if tokens and tokens[0] == "the":
        tokens = tokens[1:]
    return tokens


def normalize(name: str, loose: bool = False) -> str:
    """Compact matching key for a channel name.

    ``loose=True`` additionally drops generic words such as ``tv`` and
    ``india``.  Loose keys are only trusted when they resolve to exactly one
    source channel.
    """
    tokens = _identity_tokens(name)
    if loose:
        tokens = [t for t in tokens if t not in LOOSE_STOPWORDS]
    return "".join(tokens)


def _digits(name: str) -> Set[str]:
    return set(DIGITS_RE.findall(normalize(name)))


def _language_tokens(name: str) -> Set[str]:
    return {t for t in _identity_tokens(name) if t in LANGUAGE_TOKENS}


def _tokens(name: str) -> Set[str]:
    return {t for t in _identity_tokens(name) if t not in LOOSE_STOPWORDS}


@dataclass
class SourceChannel:
    source_id: str
    names: List[str]

    @property
    def primary_name(self) -> str:
        return self.names[0] if self.names else self.source_id


def _variant(name: str) -> str:
    """Return ``hd`` / ``sd`` / ``""`` for a quality marker in a name."""
    tokens = set(_raw_tokens(name))
    if tokens & {"hd", "fhd", "uhd", "4k", "hdr"}:
        return "hd"
    if "sd" in tokens:
        return "sd"
    return ""


def _query_variant(tvg_id: str, title: str) -> str:
    """Infer the feed variant, preferring the playlist ``@HD``/``@SD`` tag."""
    if "@" in tvg_id:
        suffix = tvg_id.rsplit("@", 1)[-1].strip().lower()
        if suffix in {"hd", "fhd", "uhd", "4k"}:
            return "hd"
        if suffix == "sd":
            return "sd"
    return _variant(title)


@dataclass
class MatchResult:
    status: str  # exact | alias | fuzzy | ambiguous | unmatched
    source_id: Optional[str] = None
    method: str = ""
    score: float = 0.0
    candidates: List[str] = field(default_factory=list)
    note: str = ""

    @property
    def matched(self) -> bool:
        return self.source_id is not None


class ChannelMatcher:
    """Index a set of source channels and match playlist names against them."""

    def __init__(
        self,
        sources: Iterable[SourceChannel],
        aliases: Optional[Dict[str, str]] = None,
    ) -> None:
        self.sources: Dict[str, SourceChannel] = {s.source_id: s for s in sources}
        self.variants: Dict[str, str] = {
            sid: _variant(source.primary_name) for sid, source in self.sources.items()
        }
        # key -> source ids (a list so collisions stay visible)
        self._strict: Dict[str, List[str]] = {}
        self._loose: Dict[str, List[str]] = {}
        self._norm_name: Dict[str, List[str]] = {}
        self._alias_raw = aliases or {}
        self.aliases: Dict[str, str] = {
            normalize(k): v for k, v in self._alias_raw.items()
        }
        self._build_index()

    # ------------------------------------------------------------------ index
    def _add(self, index: Dict[str, List[str]], key: str, source_id: str) -> None:
        if not key:
            return
        bucket = index.setdefault(key, [])
        if source_id not in bucket:
            bucket.append(source_id)

    def _build_index(self) -> None:
        for source in self.sources.values():
            self._add(self._strict, normalize(source.source_id), source.source_id)
            for name in source.names:
                strict = normalize(name)
                loose = normalize(name, loose=True)
                self._add(self._strict, strict, source.source_id)
                self._add(self._loose, loose, source.source_id)
                self._add(self._norm_name, normalize(name), source.source_id)

    def _exact(
        self,
        key: str,
        index: Dict[str, List[str]],
        query_variant: str,
    ) -> Optional[MatchResult]:
        if not key:
            return None
        ids = index.get(key, [])
        if not ids:
            return None
        source_id, ambiguous = self._choose_by_variant(ids, query_variant)
        if source_id:
            return MatchResult("exact", source_id, "exact-name", 1.0)
        return MatchResult(
            "ambiguous", None, "exact-name", 1.0, ambiguous,
            "name maps to multiple source channels",
        )

    def _choose_by_variant(
        self, ids: Sequence[str], query_variant: str
    ) -> tuple[Optional[str], List[str]]:
        """Pick the feed variant (HD/SD) that matches the playlist tvg-id tag."""
        if len(ids) == 1:
            return ids[0], []

        ranked: List[tuple[int, str]] = []
        for source_id in ids:
            source_variant = self.variants.get(source_id, "")
            if query_variant and source_variant == query_variant:
                rank = 0
            elif not source_variant:
                rank = 1
            elif not query_variant:
                rank = 2
            else:
                rank = 3
            ranked.append((rank, source_id))
        ranked.sort(key=lambda item: item[0])
        best_rank = ranked[0][0]
        best = [source_id for rank, source_id in ranked if rank == best_rank]
        if len(best) == 1:
            return best[0], []
        return None, list(ids)

    # ------------------------------------------------------------------ match
    def match(
        self,
        *,
        tvg_id: str = "",
        title: str = "",
        tvg_name: str = "",
    ) -> MatchResult:
        base_id = (tvg_id or "").split("@")[0]
        base_id = base_id.split(".")[0] if "." in base_id else base_id
        query_variant = _query_variant(tvg_id, title or tvg_name)

        # 1. Source id, exactly.
        for cand in (tvg_id, base_id):
            if cand and cand in self.sources:
                return MatchResult("exact", cand, "source-id", 1.0)

        # 2. Exact normalised names (strict first, then loose).
        for key in (normalize(title), normalize(tvg_name), normalize(base_id)):
            result = self._exact(key, self._strict, query_variant)
            if result:
                if result.status == "exact":
                    result.method = "exact-name"
                return result

        for key in (
            normalize(title, loose=True),
            normalize(tvg_name, loose=True),
            normalize(base_id, loose=True),
        ):
            result = self._exact(key, self._loose, query_variant)
            if result:
                if result.status == "exact":
                    result.method = "exact-name-loose"
                return result

        # 3. Curated aliases.
        for key in (
            normalize(title),
            normalize(tvg_name),
            normalize(base_id),
        ):
            target = self.aliases.get(key)
            if not target:
                continue
            resolved = self._resolve_alias(target)
            if resolved:
                return MatchResult("alias", resolved, "alias", 1.0)

        # 4. Guarded fuzzy match.
        return self._fuzzy(title or tvg_name or base_id)

    def _resolve_alias(self, target: str) -> Optional[str]:
        if target in self.sources:
            return target
        for index in (self._strict, self._loose):
            ids = index.get(normalize(target)) or index.get(normalize(target, loose=True))
            if ids and len(ids) == 1:
                return ids[0]
            if ids and len(ids) > 1:
                return None
        return None

    def _fuzzy(self, query: str) -> MatchResult:
        q_tokens = _tokens(query)
        q_norm = normalize(query)
        if not q_tokens or len(q_norm) < 4:
            return MatchResult("unmatched", None, "fuzzy", 0.0)

        q_digits = _digits(query)
        q_langs = _language_tokens(query)
        q_first = _first_token(query)

        scored: List[tuple] = []
        for source in self.sources.values():
            best_for_source = 0.0
            for name in source.names or [source.source_id]:
                # Cheap pre-filter: fuzzy_score enforces this anyway.
                if q_first and _first_token(name) != q_first:
                    continue
                score = self._score(
                    q_tokens, q_norm, q_digits, q_langs, q_first, name
                )
                best_for_source = max(best_for_source, score)
            if best_for_source > 0:
                scored.append((best_for_source, source.source_id))

        if not scored:
            return MatchResult("unmatched", None, "fuzzy", 0.0)

        scored.sort(key=lambda item: item[0], reverse=True)
        best_score, best_id = scored[0]
        runner_up = scored[1][0] if len(scored) > 1 else 0.0

        if best_score < FUZZY_MIN_SCORE:
            return MatchResult("unmatched", None, "fuzzy", best_score)

        if runner_up and (best_score - runner_up) < FUZZY_MIN_MARGIN:
            return MatchResult(
                "ambiguous", None, "fuzzy", best_score,
                [sid for _, sid in scored[:3]],
                f"top candidates too close ({best_score:.2f} vs {runner_up:.2f})",
            )

        return MatchResult("fuzzy", best_id, "fuzzy", best_score)

    @staticmethod
    def _score(
        q_tokens: Set[str],
        q_norm: str,
        q_digits: Set[str],
        q_langs: Set[str],
        q_first: str,
        candidate_name: str,
    ) -> float:
        c_tokens = _tokens(candidate_name)
        c_norm = normalize(candidate_name)
        if not c_tokens or not c_norm:
            return 0.0

        # Guard: numeric identity must match (Dangal != Dangal 2).
        if _digits(candidate_name) != q_digits:
            return 0.0

        # Guard: language/region markers must not conflict.
        c_langs = _language_tokens(candidate_name)
        if q_langs and c_langs and q_langs != c_langs:
            return 0.0

        # Guard: the distinguishing word must agree.  This rejects
        # "Nickelodeon" -> "Nickelodeon Jr." and "Dangal" -> "Dangal 2".
        q_dist = q_tokens & DISTINCTIVE_TOKENS
        c_dist = c_tokens & DISTINCTIVE_TOKENS
        if q_dist != c_dist:
            return 0.0

        # Guard: the first meaningful token must agree
        # ("NTV Telugu" must not become "TV9 Telugu").
        if q_first and _first_token(candidate_name) != q_first:
            return 0.0

        # Guard: every meaningful token must be nearly present on the other
        # side.  This rejects "Star Maa Movies" -> "Star Movies" because
        # "maa" has no counterpart, while still allowing spelling variants
        # such as "Jyothi" -> "Jyoti".
        if not _tokens_cover(q_tokens, c_tokens):
            return 0.0

        token_ratio = len(q_tokens & c_tokens) / len(q_tokens | c_tokens)
        seq_ratio = SequenceMatcher(None, q_norm, c_norm).ratio()
        return max(token_ratio, seq_ratio)


def _tokens_cover(left: Set[str], right: Set[str], threshold: float = 0.8) -> bool:
    """True when every token on each side has a near-match on the other."""
    if not left or not right:
        return False
    for token in left | right:
        other = right if token in left else left
        if not any(
            token == candidate
            or SequenceMatcher(None, token, candidate).ratio() >= threshold
            for candidate in other
        ):
            return False
    return True


def _first_token(name: str) -> str:
    for token in _identity_tokens(name):
        if token not in LOOSE_STOPWORDS and token not in QUALITY_TOKENS:
            return token
    return ""


def load_aliases(path: str | Path) -> Dict[str, str]:
    """Load the alias map from JSON.

    Accepted shape::

        {"aliases": {"playlist name or normalised key": "Source display name"}}

    A bare ``{key: value}`` object is also accepted.
    """
    path = Path(path)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, dict) and "aliases" in data:
        data = data["aliases"]
    if not isinstance(data, dict):
        return {}
    return {
        str(key): str(value)
        for key, value in data.items()
        if isinstance(key, str) and isinstance(value, str) and not key.startswith("_")
    }
