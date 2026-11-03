#!/usr/bin/env python3
"""Regression tests for the USA TV Next converter (no network required)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import convert_stremio_to_m3u as converter
from usa_epg_common import canonical_id, clean_channel_name, slugify


class CommonTests(unittest.TestCase):
    def test_clean_channel_name(self) -> None:
        self.assertEqual(clean_channel_name("  National   Geographic  Wild "), "National Geographic Wild")

    def test_slugify(self) -> None:
        self.assertEqual(slugify("E! Entertainment Television"), "e-entertainment-television")
        self.assertEqual(slugify("Crime + Investigation"), "crime-plus-investigation")
        self.assertEqual(slugify("5StarMax"), "5starmax")

    def test_canonical_id(self) -> None:
        self.assertEqual(canonical_id("ABC"), "abc.us")
        self.assertEqual(canonical_id("National Geographic  Wild"), "national-geographic-wild.us")


class StreamHelperTests(unittest.TestCase):
    def test_quality_and_dead_detection(self) -> None:
        self.assertEqual(converter.quality_of({"name": "FHD"}), "FHD")
        self.assertEqual(converter.quality_of({"name": "[DEAD] HD"}), "HD")
        self.assertEqual(converter.quality_of({"name": "Audio"}), "Audio")
        self.assertTrue(converter.is_dead({"name": "[DEAD] HD"}))
        self.assertFalse(converter.is_dead({"name": "HD"}))

    def test_source_labels(self) -> None:
        self.assertEqual(
            converter.source_of(
                {"url": "https://service-stitcher.clusters.pluto.tv/x.m3u8", "description": "HV:SERVICE-STIT"}
            ),
            "Pluto TV",
        )
        self.assertEqual(
            converter.source_of(
                {"url": "https://aegis-cloudfront-1.tubi.video/x.m3u8", "description": "HV:AEGIS-CLOUDF"}
            ),
            "Tubi",
        )
        self.assertEqual(
            converter.source_of(
                {"url": "https://content.uplynk.com/x.m3u8", "description": "HV:JMP2"}
            ),
            "Uplynk",
        )

    def test_normalize_url_keeps_required_params(self) -> None:
        normalized = converter.normalize_url(
            "https://Example.com/live.m3u8?foo=1&checkedby=iptvcat.com#fragment"
        )
        self.assertEqual(normalized, "https://example.com/live.m3u8?foo=1")


class BuildTests(unittest.TestCase):
    def _make_repo(self, root: Path) -> Path:
        repo = root / "upstream"
        (repo / "catalog" / "tv").mkdir(parents=True)
        (repo / "stream" / "tv").mkdir(parents=True)

        meta = {
            "id": "channel-1",
            "name": "Test Channel ",
            "genre": "Local",
            "logo": "https://example.com/logo.png",
            "streams": [
                {"url": "https://example.com/audio.m3u8", "name": "Audio"},
                {"url": "https://example.com/dead.m3u8", "name": "[DEAD] HD"},
                {"url": "https://c.mjh.nz/abc-nsw.m3u8", "name": "SD"},
                {
                    "url": "https://service-stitcher.clusters.pluto.tv/live.m3u8",
                    "name": "SD",
                    "description": "HV:SERVICE-STIT",
                },
                {
                    "url": "https://aegis-cloudfront-1.tubi.video/one.m3u8",
                    "name": "HD",
                    "description": "HV:AEGIS-CLOUDF",
                },
                {
                    "url": "https://aegis-cloudfront-2.tubi.video/two.m3u8",
                    "name": "HD",
                    "description": "HV:AEGIS-CLOUDF",
                },
            ],
        }
        (repo / "catalog" / "tv" / "all.json").write_text(
            json.dumps({"metas": [meta]}), encoding="utf-8"
        )

        stream_payload = {
            "streams": [
                {"url": "https://example.com/live.m3u8?checkedby=iptvcat.com", "name": "HD"},
                {"url": "https://example.com/live.m3u8", "name": "HD"},
            ]
        }
        (repo / "stream" / "tv" / "channel-1.json").write_text(
            json.dumps(stream_payload), encoding="utf-8"
        )
        return repo

    def test_build_filters_and_labels(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = self._make_repo(root)
            output = root / "out.m3u"
            converter.build(repo, output, "https://example.com/usa_epg.xml.gz")
            text = output.read_text(encoding="utf-8")

            self.assertTrue(text.startswith('#EXTM3U url-tvg="https://example.com/usa_epg.xml.gz"'))
            self.assertNotIn("Audio", text)
            self.assertNotIn("[DEAD]", text)
            self.assertNotIn("abc-nsw", text)
            self.assertEqual(text.count("#EXTINF"), 4)
            self.assertIn('tvg-id="test-channel.us"', text)
            self.assertIn('tvg-name="Test Channel"', text)
            self.assertIn('group-title="USA | Local"', text)
            self.assertIn("Test Channel (Pluto TV - SD)", text)
            self.assertIn("Test Channel (Tubi - HD)", text)
            self.assertIn("Test Channel (Tubi - HD) #2", text)
            self.assertIn("https://example.com/live.m3u8\n", text)


if __name__ == "__main__":
    unittest.main()
