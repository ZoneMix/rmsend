"""DOM surgery on fixtures; needs lxml (run via uv, see README). No network is touched."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from lxml import html as lxml_html
    from rmsend_lib import article
except ImportError:  # pragma: no cover — stdlib-only runners skip this module
    raise unittest.SkipTest("lxml/trafilatura not installed; run with uv (see README)")


def body_of(fragment: str):
    return lxml_html.fromstring(f"<body>{fragment}</body>")


class SafeStemTests(unittest.TestCase):
    def test_keeps_unicode_letters_and_collapses_junk(self):
        self.assertEqual(article.safe_stem("Café: Part 1 / “quoted”"), "Café Part 1 quoted")
        self.assertEqual(article.safe_stem("///"), "article")
        self.assertEqual(len(article.safe_stem("x" * 500)), 120)


class RestructureTests(unittest.TestCase):
    def test_headings_demoted_and_boilerplate_dropped(self):
        body = body_of("<h1>Section</h1><p>Share this post</p><p>Real text</p>")
        self.assertEqual(article.demote_headings(body), 1)
        self.assertEqual(article.drop_boilerplate(body), 1)
        self.assertEqual([el.tag for el in body], ["h2", "p"])

    def test_legacy_nested_anchor_unwrapped(self):
        body = body_of('<p>x<a href="#_ftn2"><sup><a href="#note2">2</a></sup></a></p>')
        self.assertEqual(article.unwrap_legacy_anchors(body), 1)
        self.assertEqual(len(body.findall(".//sup/a")), 1)

    def test_figure_gets_caption_from_source_page(self):
        captions = article.harvest_captions(
            '<figure><img src="https://x/y/pic.jpg"><figcaption>A  caption</figcaption></figure>')
        body = body_of('<p><img src="https://x/y/pic.jpg"></p><p>after</p>')
        wrapped, captioned = article.wrap_figures(body, captions)
        self.assertEqual((wrapped, captioned), (1, 1))
        self.assertEqual(body.find(".//figure/figcaption").text, "A caption")

    def test_footnotes_link_both_ways_and_get_sectioned(self):
        body = body_of("<p>Claim<sup>1</sup> and<sup>2</sup></p><p>[1] first</p><p>[2] second</p>")
        notes = article.collect_endnotes(body)
        self.assertEqual(article.link_footnotes(body, notes), 2)
        self.assertTrue(article.group_endnotes(body, notes))
        self.assertIsNotNone(body.find('.//a[@href="#fn-1"]'))
        self.assertIsNotNone(body.find('.//span[@id="fn-2"]'))
        self.assertEqual(body.find(".//section").get("class"), "endnotes")

    def test_pulled_quote_wrapped(self):
        body = body_of("<p>Short wisdom.</p><p>— Someone</p>")
        self.assertEqual(article.wrap_quotations(body), 1)
        self.assertEqual(body.find(".//blockquote/p[@class='attribution']").text, "— Someone")

    def test_restructure_runs_end_to_end_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            inner, report = article.restructure("<body><h1>T</h1><p>text</p></body>", "", Path(tmp))
        self.assertIn("<h2>T</h2>", inner)
        self.assertIn("1 headings demoted", report)


if __name__ == "__main__":
    unittest.main()
