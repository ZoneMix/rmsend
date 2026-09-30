"""PDF completeness boundary, HTML title extraction and the article template (stdlib only)."""
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rmsend_lib import config, render  # noqa: E402


@dataclass(frozen=True)
class FakeArticle:
    title: str = "A <Title>"
    subtitle: str = "sub"
    author: str = ""
    published: str = "1 January 2026"
    html: str = "<p>body</p>"


class PdfCompleteTests(unittest.TestCase):
    def check(self, size, trailer):
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "x.pdf"
            pdf.write_bytes(b"x" * size + (b"%%EOF\n" if trailer else b""))
            return render.pdf_is_complete(pdf)

    def test_small_files_are_not_complete(self):
        self.assertFalse(self.check(config.MIN_PDF_BYTES - 10, True))

    def test_file_between_min_and_window_no_longer_crashes(self):
        # 1024 <= size < 2048 used to raise OSError on the seek
        size = config.MIN_PDF_BYTES + 100
        self.assertLess(size, config.PDF_TRAILER_WINDOW)
        self.assertTrue(self.check(size, True))
        self.assertFalse(self.check(size, False))

    def test_large_file_with_trailer(self):
        self.assertTrue(self.check(config.PDF_TRAILER_WINDOW * 3, True))

    def test_missing_file(self):
        self.assertFalse(render.pdf_is_complete(Path("/nonexistent/x.pdf")))


class HtmlTitleTests(unittest.TestCase):
    def test_reads_title_tag_and_unescapes(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp) / "paper.html"
            page.write_text("<html><head><title>The Belisario Daily &mdash;\n  18 Sep</title></head></html>")
            self.assertEqual(render.html_title(page), "The Belisario Daily — 18 Sep")

    def test_falls_back_to_stem(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp) / "untitled.html"
            page.write_text("<p>no title</p>")
            self.assertEqual(render.html_title(page), "untitled")


class TemplateTests(unittest.TestCase):
    def test_escapes_title_and_omits_empty_lines(self):
        out = render.render_document(FakeArticle(), "body{}")
        self.assertIn("A &lt;Title&gt;", out)
        self.assertIn('class="subtitle"', out)
        self.assertNotIn('class="byline"', out)
        self.assertIn("<p>body</p>", out)


if __name__ == "__main__":
    unittest.main()
