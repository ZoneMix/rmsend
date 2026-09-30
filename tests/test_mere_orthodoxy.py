"""Reader exports at the HTTP boundary: synthetic payloads, never a real tablet."""
import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests
from lxml import html

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rmsend_lib.article import fetch_article

SITE = "https://mereorthodoxy.com"
LIBRARY = "https://mo-tfr-library.mo-podcast-feed.workers.dev"
URL = SITE + "/the-faith-received/read/?w=test-work&p=2"


def response(payload, status=200, compressed=False):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(payload).encode()
    if compressed:
        result._content = gzip.compress(result._content)
    result.headers["Content-Type"] = "application/json"
    return result


class ReaderTests(unittest.TestCase):
    def export(self, resources, **kwargs):
        def get(url, **_):
            if url not in resources:
                self.fail(f"Unexpected HTTP request: {url}")
            return resources[url]
        with tempfile.TemporaryDirectory() as tmp, patch("requests.get", side_effect=get):
            return fetch_article(URL, Path(tmp), **kwargs)

    def classic(self, meta, files):
        resources = {
            SITE + "/assets/data/faith-received/public-slugs.json": response({"works": {}}),
            LIBRARY + "/v1/works/test-work/meta.json": response(meta),
        }
        resources.update({LIBRARY + "/v1/works/test-work/" + k: response(v) for k, v in files.items()})
        return resources

    def test_whole_single_work_preserves_sections_emphasis_and_footnotes(self):
        resources = self.classic(
            {"title": "Test Work", "single": "work.json", "n_pages": 2},
            {"work.json": {"pages": [
                {"n": 1, "en": "### First\n\n*One* paragraph[^x].\n\n[^x]: A note."},
                {"n": 2, "en": "### Last\n\nFinal paragraph."},
            ]}},
        )
        article = self.export(resources)
        doc = html.fragment_fromstring(article.html, create_parent="article")
        self.assertEqual(article.title, "Test Work")
        self.assertEqual(doc.xpath(".//h3/text()"), ["First", "Last"])
        self.assertEqual(doc.xpath(".//em/text()"), ["One"])
        self.assertIn("A note.", doc.text_content())
        self.assertIn("Final paragraph.", doc.text_content())
        self.assertIn('href="#part-0-fn1"', article.html)
        self.assertIn(URL.split("&p=")[0], article.html)

    def test_all_shards_are_exported_in_declared_order(self):
        resources = self.classic(
            {"title": "Test", "n_pages": 2, "shards": [{"file": "a.json"}, {"file": "b.json"}]},
            {"a.json": {"pages": [{"n": 5, "en": "Opening."}]},
             "b.json": {"pages": [{"n": 6, "en": "Ending."}]}},
        )
        body = self.export(resources).html
        self.assertLess(body.index("Opening."), body.index("Ending."))

    def test_missing_english_or_incomplete_work_fails_instead_of_partial_export(self):
        for pages in ([{"n": 1, "en": "One."}],
                      [{"n": 1, "en": "One."}, {"n": 2, "en": "", "la": "Latin."}]):
            with self.subTest(pages=pages), self.assertRaises(SystemExit):
                self.export(self.classic({"title": "Test", "single": "work.json", "n_pages": 2},
                                         {"work.json": {"pages": pages}}))

    def eebo(self, modern_status=200):
        return {
            SITE + "/assets/data/faith-received/public-slugs.json": response({"works": {"eebo-123": "test-work"}}),
            LIBRARY + "/eebo/123.json.gz": response({
                "meta": {"title": "Book", "author": "An Author", "year": 1698},
                "toc": [{"label": "Front", "kids": [{"label": "Preface", "html": "<b>Preface</b><p>Old preface.</p>"}]},
                        {"label": "Sermon", "html": '<p>Final <i>words</i><span class="note">A gloss.</span>.</p>'}],
            }, compressed=True),
            LIBRARY + "/eebo_modern/123.json.gz": response({"m": {"0.0": "<p>Modern preface.</p>"}},
                                                        status=modern_status, compressed=True),
        }

    def test_public_alias_gzip_and_nested_eebo_export_with_partial_modernization(self):
        article = self.export(self.eebo())
        self.assertEqual(article.author, "An Author")
        self.assertIn("Modern preface.", article.html)
        self.assertNotIn("Old preface.", article.html)
        self.assertIn("Final <i>words</i>", article.html)
        self.assertIn("A gloss.", article.html)
        self.assertLess(article.html.index("Preface"), article.html.index("Sermon"))

    def test_only_missing_modern_sidecar_falls_back_to_original(self):
        self.assertIn("Old preface.", self.export(self.eebo(modern_status=404)).html)
        with self.assertRaises(SystemExit):
            self.export(self.eebo(modern_status=503))

    def test_original_option_does_not_request_modern_text(self):
        resources = self.eebo()
        del resources[LIBRARY + "/eebo_modern/123.json.gz"]
        body = self.export(resources, original=True).html
        self.assertIn("Old preface.", body)
        doc = html.fragment_fromstring(body, create_parent="article")
        self.assertEqual(doc.xpath(".//h3[text()='Preface']/text()"), ["Preface"])

    def test_active_html_is_removed_without_losing_paragraphs(self):
        resources = self.classic({"title": "Test", "single": "work.json", "n_pages": 1},
            {"work.json": {"pages": [{"n": 1, "en":
                '<p onclick="bad()">Safe <em>text</em><script>bad()</script>'
                '<a href="javascript:bad()">label</a></p><iframe src="https://example.org"></iframe>'}]}})
        body = self.export(resources).html
        self.assertIn("<em>text</em>", body)
        self.assertIn("label", body)
        for unsafe in ("onclick", "<script", "javascript:", "<iframe", "bad()"):
            self.assertNotIn(unsafe, body)

    def test_unsafe_shard_path_is_rejected_before_http(self):
        with self.assertRaises(SystemExit):
            self.export(self.classic({"title": "Test", "single": "../other.json"}, {}))


if __name__ == "__main__":
    unittest.main()
