"""
Regression test for S1: scrub_all_metadata must strip annotation PII.

PDF annotations routinely carry the reviewer's name in /T (title/author),
free-text comment bodies, and timestamps — exactly the data a "scrub" is
expected to remove.  This test builds a PDF with a known annotation, runs
scrub_all_metadata, and asserts that the identifying data does not survive.

Run with:
    .venv/bin/python -m pytest tests/test_scrub_annotations.py -v
"""

import os
import sys
import tempfile
import unittest

import fitz  # PyMuPDF

# ── path setup ────────────────────────────────────────────────────────────────
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SITE = os.path.join(_PROJECT_ROOT, "Sources", "Marcedit", "python_site")
if _SITE not in sys.path:
    sys.path.insert(0, _SITE)

from editor_pkg import core  # noqa: E402


def _cleanup(*paths):
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.unlink(p)
        except OSError:
            pass


class TestScrubAnnotations(unittest.TestCase):
    """scrub_all_metadata must remove reviewer-identifying annotation data."""

    def setUp(self):
        # Build a PDF that has:
        #   • A Text annotation with reviewer name and comment
        #   • Document-level metadata (author, title)
        fd, self.src = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        fd, self.dst = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)

        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Reviewable content", fontsize=12)

        # Add a Text (sticky-note) annotation with PII in title + content.
        annot = page.add_text_annot((100, 100), "secret reviewer note")
        annot.set_info(title="Jane Reviewer", content="secret reviewer note")
        annot.update()

        doc.set_metadata({
            "author": "Secret Author",
            "title": "Secret Title",
        })
        doc.save(self.src)
        doc.close()

    def tearDown(self):
        _cleanup(self.src, self.dst)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _all_annot_infos(self, path: str) -> list[dict]:
        """Collect info dicts for every annotation in every page of path."""
        infos = []
        with fitz.open(path) as doc:
            for page in doc:
                for annot in page.annots():
                    infos.append(annot.info)
        return infos

    # ── tests ─────────────────────────────────────────────────────────────────

    def test_scrub_returns_success(self):
        result = core.scrub_all_metadata(self.src, self.dst, data_dir=None)
        self.assertTrue(result.get("success"), f"scrub_all_metadata failed: {result}")

    def test_document_metadata_cleared(self):
        core.scrub_all_metadata(self.src, self.dst, data_dir=None)
        with fitz.open(self.dst) as doc:
            meta = doc.metadata
        # After scrub the author and title must be absent / empty.
        self.assertFalse(
            meta.get("author"),
            f"Document author survived scrub: {meta.get('author')!r}",
        )
        self.assertFalse(
            meta.get("title"),
            f"Document title survived scrub: {meta.get('title')!r}",
        )

    def test_annotation_reviewer_name_removed(self):
        """No annotation in the output may expose 'Jane Reviewer'."""
        core.scrub_all_metadata(self.src, self.dst, data_dir=None)
        for info in self._all_annot_infos(self.dst):
            self.assertNotIn(
                "Jane Reviewer",
                info.get("title", ""),
                f"Reviewer name survived scrub in annot info: {info}",
            )
            self.assertNotIn(
                "Jane Reviewer",
                info.get("content", ""),
                f"Reviewer name survived in content: {info}",
            )

    def test_annotation_comment_text_removed(self):
        """No annotation in the output may expose the original comment text."""
        core.scrub_all_metadata(self.src, self.dst, data_dir=None)
        for info in self._all_annot_infos(self.dst):
            self.assertNotIn(
                "secret reviewer note",
                info.get("content", ""),
                f"Comment text survived scrub: {info}",
            )

    def test_no_annotations_remain_after_scrub(self):
        """Full-delete strategy: the output PDF must have zero annotations."""
        core.scrub_all_metadata(self.src, self.dst, data_dir=None)
        remaining = self._all_annot_infos(self.dst)
        self.assertEqual(
            0,
            len(remaining),
            f"Expected 0 annotations after scrub, found {len(remaining)}: {remaining}",
        )

    def test_output_file_is_valid_pdf(self):
        """The scrubbed output must open without errors and have at least one page."""
        core.scrub_all_metadata(self.src, self.dst, data_dir=None)
        with fitz.open(self.dst) as doc:
            self.assertGreater(doc.page_count, 0)

    def test_debug_log_reports_annotation_removal(self):
        """The log must mention how many annotations were removed."""
        result = core.scrub_all_metadata(self.src, self.dst, data_dir=None)
        log_text = "\n".join(result.get("log", []))
        self.assertIn(
            "annotation",
            log_text.lower(),
            f"Expected annotation mention in debug log, got:\n{log_text}",
        )

    def test_multiple_annotations_all_removed(self):
        """Scrub must remove all annotations, not just the first one."""
        fd, src2 = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        fd, dst2 = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        try:
            doc = fitz.open()
            page = doc.new_page()
            for i in range(5):
                annot = page.add_text_annot((50 + i * 30, 100), f"note {i}")
                annot.set_info(title=f"Reviewer{i}", content=f"comment {i}")
                annot.update()
            doc.save(src2)
            doc.close()

            result = core.scrub_all_metadata(src2, dst2, data_dir=None)
            self.assertTrue(result.get("success"))
            remaining = self._all_annot_infos(dst2)
            self.assertEqual(0, len(remaining),
                             f"Expected 0 annotations, found {len(remaining)}")
        finally:
            _cleanup(src2, dst2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
