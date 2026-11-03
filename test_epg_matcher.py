#!/usr/bin/env python3
"""Regression tests for the EPG matcher and EXTINF parsing."""

import unittest

from epg_matcher import ChannelMatcher, SourceChannel, normalize
from generate_epg import split_extinf_title

SOURCES = [
    SourceChannel("c1", ["Colors HD"]),
    SourceChannel("c2", ["Colors SD"]),
    SourceChannel("c3", ["ABN Andhra Jyothi"]),
    SourceChannel("c4", ["Dangal"]),
    SourceChannel("c5", ["Nickelodeon Jr."]),
    SourceChannel("c6", ["Star Movies HD"]),
    SourceChannel("c7", ["PM e Vidya 04"]),
    SourceChannel("c8", ["Moon TV"]),
    SourceChannel("c9", ["Moon TV HD"]),
    SourceChannel("c10", ["Zee TV HD"]),
    SourceChannel("c11", ["Zee TV SD"]),
]


class NormalizeTests(unittest.TestCase):
    def test_quality_and_brackets_are_ignored(self):
        self.assertEqual(normalize("Colors Cineplex Superhits (576p)"), "colorscineplexsuperhits")
        self.assertEqual(normalize("History TV18 HD [Geo-blocked]"), "historytv18")
        self.assertEqual(normalize("The Voice TV"), "voicetv")

    def test_loose_keeps_region_words(self):
        self.assertNotEqual(normalize("The Voice TV", loose=True), normalize("India Voice", loose=True))


class MatcherTests(unittest.TestCase):
    def setUp(self):
        self.matcher = ChannelMatcher(SOURCES, {"E-Vidya 4": "PM e Vidya 04"})

    def test_variant_tag_disambiguates_hd_and_sd(self):
        hd = self.matcher.match(tvg_id="Colors.in@HD", title="Colors HD (1080p)")
        sd = self.matcher.match(tvg_id="Colors.in@SD", title="Colors (576p)")
        self.assertEqual(hd.source_id, "c1")
        self.assertEqual(sd.source_id, "c2")

    def test_transliteration_is_allowed(self):
        result = self.matcher.match(title="ABN Andhra Jyoti (720p)")
        self.assertEqual(result.status, "fuzzy")
        self.assertEqual(result.source_id, "c3")

    def test_number_guard_blocks_wrong_sibling(self):
        result = self.matcher.match(title="Dangal 2 (720p)")
        self.assertFalse(result.matched)

    def test_distinctive_suffix_guard(self):
        result = self.matcher.match(title="Nickelodeon (India) (576p)")
        self.assertFalse(result.matched)

    def test_missing_token_guard(self):
        result = self.matcher.match(title="Star Maa Movies (576p)")
        self.assertFalse(result.matched)

    def test_alias_is_applied(self):
        result = self.matcher.match(title="E-Vidya 4 (576p)")
        self.assertEqual(result.status, "alias")
        self.assertEqual(result.source_id, "c7")

    def test_no_variant_tag_prefers_unmarked_source(self):
        result = self.matcher.match(title="Moon TV (576p)")
        self.assertEqual(result.source_id, "c8")

    def test_untagged_duplicate_is_ambiguous(self):
        result = self.matcher.match(title="Zee TV (576p)")
        self.assertEqual(result.status, "ambiguous")


class ExtinfTests(unittest.TestCase):
    def test_user_agent_commas_do_not_truncate_title(self):
        line = (
            '#EXTINF:-1 tvg-id="GoldminesMovies.in@SD" '
            'http-user-agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36" '
            'group-title="Movies",Goldmines Movies (576p)'
        )
        self.assertEqual(split_extinf_title(line), "Goldmines Movies (576p)")


if __name__ == "__main__":
    unittest.main()
