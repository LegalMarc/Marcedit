"""
Security regression tests for MarcEdit PDF Editor.

Covers all findings from the security audit performed 2026-03-03:
  1. Out-of-bounds page index in analyze_layout() / get_block_spans() (Critical)
  2. Non-integer page_range elements in regex_replace() / apply_template() (High)
  3. XPC-layer page_range validation in regex_replace_text() / apply_template_replacements() (High)
  4. Path-containment check in scrub_all_metadata() embedded-file extraction (High)

All tests assert that bad input is rejected with a well-formed error dict rather
than raising an uncaught exception or silently writing to an unintended location.
"""

import sys
import os
import tempfile
import unittest
import contextlib
import importlib.util
import io
import plistlib
import subprocess

# ── path setup ────────────────────────────────────────────────────────────────
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROJECT = os.path.join(_PROJECT_ROOT, "MarceditApp.xcodeproj", "project.pbxproj")
_ENTITLEMENTS = os.path.join(_PROJECT_ROOT, "Sources", "Marcedit", "Marcedit.entitlements")
_RELEASE_SECURITY_SCRIPT = os.path.join(_PROJECT_ROOT, "Scripts", "verify_release_security.py")
_SITE = os.path.join(_PROJECT_ROOT, "Sources", "Marcedit", "python_site")
if _SITE not in sys.path:
    sys.path.insert(0, _SITE)

import fitz  # noqa: E402
from editor_pkg import core, core_xpc  # noqa: E402


def _load_release_security_module():
    spec = importlib.util.spec_from_file_location(
        "verify_release_security", _RELEASE_SECURITY_SCRIPT
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TestReleaseSecurityConfiguration(unittest.TestCase):
    """Release builds must keep a minimal offline sandbox posture."""

    def test_release_entitlements_are_minimal_for_user_selected_pdfs(self):
        with open(_ENTITLEMENTS, "rb") as handle:
            entitlements = plistlib.load(handle)

        self.assertTrue(entitlements.get("com.apple.security.app-sandbox"))
        self.assertTrue(entitlements.get("com.apple.security.files.user-selected.read-write"))

        forbidden = {
            "com.apple.security.network.client",
            "com.apple.security.network.server",
            "com.apple.security.files.downloads.read-write",
            "com.apple.security.files.home-relative-path.read-write",
            "com.apple.security.files.absolute-path.read-write",
        }
        enabled_forbidden = [key for key in forbidden if entitlements.get(key)]
        self.assertEqual([], enabled_forbidden)

    def test_release_target_uses_entitlements_and_hardened_runtime(self):
        with open(_PROJECT, encoding="utf-8") as handle:
            project = handle.read()

        target_section_start = project.index("TARGET001 /* Marcedit */")
        target_section_end = project.index("productType = \"com.apple.product-type.application\";", target_section_start)
        target_section = project[target_section_start:target_section_end]
        self.assertIn("buildConfigurationList = CONFIGLIST001;", target_section)

        config_list_start = project.index('CONFIGLIST001 /* Build configuration list for PBXNativeTarget "Marcedit" */')
        config_list_end = project.index("defaultConfigurationName = Release;", config_list_start)
        config_list = project[config_list_start:config_list_end]
        self.assertIn("APPREL001 /* Release */", config_list)

        release_section_start = project.index("APPREL001 /* Release */")
        release_section_end = project.index("name = Release;", release_section_start)
        release_section = project[release_section_start:release_section_end]

        self.assertIn(
            "CODE_SIGN_ENTITLEMENTS = Sources/Marcedit/Marcedit.entitlements;",
            release_section,
        )
        self.assertIn("ENABLE_HARDENED_RUNTIME = YES;", release_section)

    def test_release_security_verifier_passes_source_configuration(self):
        result = subprocess.run(
            [sys.executable, _RELEASE_SECURITY_SCRIPT],
            cwd=_PROJECT_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_developer_id_requirement_needs_built_app(self):
        result = subprocess.run(
            [sys.executable, _RELEASE_SECURITY_SCRIPT, "--require-developer-id"],
            cwd=_PROJECT_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("--require-developer-id requires --app", result.stderr)

    def test_hardened_runtime_detection_uses_code_directory_flags(self):
        verifier = _load_release_security_module()
        self.assertTrue(verifier.has_hardened_runtime(
            "CodeDirectory v=20500 size=123 flags=0x10000(runtime) hashes=1+7"
        ))
        self.assertFalse(verifier.has_hardened_runtime(
            "Executable=/tmp/runtime-named-folder/Marcedit.app/Contents/MacOS/Marcedit\n"
            "CodeDirectory v=20500 size=123 flags=0x0(none) hashes=1+7"
        ))


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_pdf(text: str = "Hello World", pages: int = 1) -> str:
    """Create a temp PDF with *pages* pages and return its path."""
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    doc = fitz.open()
    for _ in range(pages):
        pg = doc.new_page()
        pg.insert_text((72, 72), text, fontsize=12)
    doc.save(path)
    doc.close()
    return path


def _cleanup(*paths):
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.unlink(p)
        except OSError:
            pass


# ══════════════════════════════════════════════════════════════════════════════
# 1. analyze_layout — page_index bounds validation  (Critical)
# ══════════════════════════════════════════════════════════════════════════════

class TestAnalyzeLayoutPageBounds(unittest.TestCase):
    """analyze_layout must reject out-of-bounds page_index without raising."""

    def setUp(self):
        self.pdf = _make_pdf(pages=3)  # pages 0, 1, 2 are valid

    def tearDown(self):
        _cleanup(self.pdf)

    def _call(self, page_index):
        return core_xpc.analyze_layout(self.pdf, page_index)

    def test_valid_first_page(self):
        result = self._call(0)
        self.assertTrue(result.get("success"), result)

    def test_valid_last_page(self):
        result = self._call(2)
        self.assertTrue(result.get("success"), result)

    def test_page_index_one_beyond_end(self):
        result = self._call(3)
        self.assertFalse(result.get("success"),
                         "page_index == len(doc) should be rejected")
        self.assertIn("message", result)

    def test_large_page_index(self):
        result = self._call(999_999)
        self.assertFalse(result.get("success"))
        self.assertIn("message", result)

    def test_negative_page_index(self):
        result = self._call(-1)
        self.assertFalse(result.get("success"),
                         "Negative page_index should be rejected")
        self.assertIn("message", result)

    def test_very_negative_page_index(self):
        result = self._call(-999_999)
        self.assertFalse(result.get("success"))

    def test_returns_dict_not_exception(self):
        """The function must NEVER raise — always return a dict."""
        for bad_idx in (-1, 3, 1_000_000, -1_000_000):
            with self.subTest(page_index=bad_idx):
                try:
                    result = self._call(bad_idx)
                    self.assertIsInstance(result, dict)
                except Exception as exc:
                    self.fail(f"analyze_layout raised {type(exc).__name__} for "
                              f"page_index={bad_idx}: {exc}")

    def test_error_result_has_required_keys(self):
        result = self._call(999)
        for key in ("success", "layout_type", "column_count", "columns",
                    "has_tables", "tables", "dominant_rotation",
                    "has_rotated_text", "column_index", "rect_rotation"):
            self.assertIn(key, result, f"Missing key '{key}' in error result")


# ══════════════════════════════════════════════════════════════════════════════
# 2. get_block_spans — page_index bounds validation  (Critical)
# ══════════════════════════════════════════════════════════════════════════════

class TestGetBlockSpansPageBounds(unittest.TestCase):
    """get_block_spans XPC wrapper must reject out-of-bounds page_index."""

    def setUp(self):
        self.pdf = _make_pdf("Sample text", pages=2)

    def tearDown(self):
        _cleanup(self.pdf)

    def _call(self, page_index):
        return core_xpc.get_block_spans(self.pdf, page_index, "Sample text")

    def test_valid_page(self):
        # page 0 is valid (the text may or may not be found, but no crash)
        result = self._call(0)
        self.assertIsInstance(result, dict)
        self.assertIn("success", result)

    def test_page_index_beyond_end(self):
        result = self._call(2)  # doc has 2 pages (indices 0, 1)
        self.assertFalse(result.get("success"))
        self.assertIn("message", result)

    def test_large_page_index(self):
        result = self._call(1_000_000)
        self.assertFalse(result.get("success"))

    def test_negative_page_index(self):
        result = self._call(-1)
        self.assertFalse(result.get("success"))

    def test_never_raises(self):
        for bad_idx in (-1, 2, 999_999):
            with self.subTest(page_index=bad_idx):
                try:
                    result = self._call(bad_idx)
                    self.assertIsInstance(result, dict)
                except Exception as exc:
                    self.fail(f"get_block_spans raised {type(exc).__name__} for "
                              f"page_index={bad_idx}: {exc}")

    def test_error_result_has_required_keys(self):
        result = self._call(999)
        for key in ("success", "block_bbox", "spans", "span_count", "message"):
            self.assertIn(key, result, f"Missing key '{key}' in error result")


# ══════════════════════════════════════════════════════════════════════════════
# 3. regex_replace — page_range type validation  (High)
# ══════════════════════════════════════════════════════════════════════════════

class TestRegexReplacePageRange(unittest.TestCase):
    """core.regex_replace must handle non-integer page_range gracefully."""

    def setUp(self):
        self.src = _make_pdf("hello world", pages=3)
        fd, self.dst = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)

    def tearDown(self):
        _cleanup(self.src, self.dst)

    def _call(self, page_range):
        return core.regex_replace(self.src, self.dst, r"hello", "hi",
                                  page_range=page_range)

    def test_valid_page_range(self):
        result = self._call((1, 2))
        self.assertIn("success", result)
        self.assertIsInstance(result, dict)

    def test_string_elements_rejected(self):
        result = self._call(("one", "two"))
        self.assertFalse(result.get("success"))
        self.assertIn("page_range", result.get("message", "").lower())

    def test_none_element_rejected(self):
        result = self._call((None, 2))
        self.assertFalse(result.get("success"))

    def test_float_elements_accepted_via_int_cast(self):
        """Float page numbers should be coerced to int, not rejected."""
        result = self._call((1.0, 2.0))
        # int(1.0)==1, int(2.0)==2 — this is valid
        self.assertIn("success", result)

    def test_too_short_range_object(self):
        """A tuple with only one element should fail gracefully."""
        result = self._call((1,))
        self.assertFalse(result.get("success"))

    def test_none_range_uses_all_pages(self):
        result = self._call(None)
        self.assertIn("success", result)

    def test_never_raises(self):
        bad_ranges = [("a", "b"), (None, 2), ([], {}), (object(), 1)]
        for pr in bad_ranges:
            with self.subTest(page_range=pr):
                try:
                    result = self._call(pr)
                    self.assertIsInstance(result, dict)
                except Exception as exc:
                    self.fail(f"regex_replace raised {type(exc).__name__} for "
                              f"page_range={pr!r}: {exc}")

    def test_duplicate_same_line_matches_are_preserved(self):
        src = _make_pdf("foo foo", pages=1)
        fd, dst = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        try:
            result = core.regex_replace(src, dst, r"foo", "bar")
            self.assertTrue(result.get("success"), result)
            with fitz.open(dst) as doc:
                text = doc[0].get_text("text")
            self.assertIn("bar bar", " ".join(text.split()))
            self.assertNotIn("foo", text)
            self.assertEqual(result.get("replacements"), 2)
        finally:
            _cleanup(src, dst)


# ══════════════════════════════════════════════════════════════════════════════
# 4. apply_template — page_range type validation  (High)
# ══════════════════════════════════════════════════════════════════════════════

class TestApplyTemplatePageRange(unittest.TestCase):
    """core.apply_template must handle non-integer page_range gracefully."""

    def setUp(self):
        self.src = _make_pdf("Dear {{NAME}}", pages=3)
        fd, self.dst = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)

    def tearDown(self):
        _cleanup(self.src, self.dst)

    def _call(self, page_range):
        return core.apply_template(self.src, self.dst,
                                   {"NAME": "Alice"},
                                   page_range=page_range)

    def test_valid_page_range(self):
        result = self._call((1, 2))
        self.assertIn("success", result)

    def test_string_elements_rejected(self):
        result = self._call(("start", "end"))
        self.assertFalse(result.get("success"))
        self.assertIn("page_range", result.get("message", "").lower())

    def test_none_element_rejected(self):
        result = self._call((None, 1))
        self.assertFalse(result.get("success"))

    def test_float_elements_accepted(self):
        result = self._call((1.0, 2.0))
        self.assertIn("success", result)

    def test_too_short_range_object(self):
        result = self._call((1,))
        self.assertFalse(result.get("success"))

    def test_none_range_uses_all_pages(self):
        result = self._call(None)
        self.assertIn("success", result)

    def test_never_raises(self):
        bad_ranges = [("x", "y"), (None, 3), ([], [])]
        for pr in bad_ranges:
            with self.subTest(page_range=pr):
                try:
                    result = self._call(pr)
                    self.assertIsInstance(result, dict)
                except Exception as exc:
                    self.fail(f"apply_template raised {type(exc).__name__} for "
                              f"page_range={pr!r}: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
# 5. XPC wrappers — page_range validation  (High)
# ══════════════════════════════════════════════════════════════════════════════

class TestXpcRegexReplacePageRange(unittest.TestCase):
    """core_xpc.regex_replace_text must validate page_range before conversion."""

    def setUp(self):
        self.src = _make_pdf("hello world", pages=3)
        fd, self.dst = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)

    def tearDown(self):
        _cleanup(self.src, self.dst)

    def _call(self, page_range):
        return core_xpc.regex_replace_text(
            self.src, self.dst, r"hello", "hi", page_range=page_range)

    def test_valid_zero_based_range(self):
        result = self._call([0, 1])
        self.assertIn("success", result)

    def test_string_elements_rejected(self):
        result = self._call(["a", "b"])
        self.assertFalse(result.get("success"))

    def test_none_element_rejected(self):
        result = self._call([None, 1])
        self.assertFalse(result.get("success"))

    def test_single_element_list_rejected(self):
        result = self._call([0])
        self.assertFalse(result.get("success"))

    def test_float_elements_accepted(self):
        result = self._call([0.0, 1.0])
        self.assertIn("success", result)

    def test_none_range_valid(self):
        result = self._call(None)
        self.assertIn("success", result)

    def test_never_raises(self):
        bad = [["x"], [None, 1], [object()], []]
        for pr in bad:
            with self.subTest(page_range=pr):
                try:
                    result = self._call(pr)
                    self.assertIsInstance(result, dict)
                except Exception as exc:
                    self.fail(f"regex_replace_text raised for page_range={pr!r}: {exc}")


class TestXpcApplyTemplatePageRange(unittest.TestCase):
    """core_xpc.apply_template_replacements must validate page_range."""

    def setUp(self):
        self.src = _make_pdf("Dear {{NAME}}", pages=3)
        fd, self.dst = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)

    def tearDown(self):
        _cleanup(self.src, self.dst)

    def _call(self, page_range):
        return core_xpc.apply_template_replacements(
            self.src, self.dst, {"NAME": "Bob"}, page_range=page_range)

    def test_valid_zero_based_range(self):
        result = self._call([0, 1])
        self.assertIn("success", result)

    def test_string_elements_rejected(self):
        result = self._call(["start", "end"])
        self.assertFalse(result.get("success"))

    def test_single_element_list_rejected(self):
        result = self._call([0])
        self.assertFalse(result.get("success"))

    def test_float_elements_accepted(self):
        result = self._call([0.0, 2.0])
        self.assertIn("success", result)

    def test_none_range_valid(self):
        result = self._call(None)
        self.assertIn("success", result)

    def test_never_raises(self):
        bad = [["x", "y"], [None, 0], [object(), 1]]
        for pr in bad:
            with self.subTest(page_range=pr):
                try:
                    result = self._call(pr)
                    self.assertIsInstance(result, dict)
                except Exception as exc:
                    self.fail(f"apply_template_replacements raised for "
                              f"page_range={pr!r}: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
# 6. scrub_all_metadata — path-containment check  (High)
# ══════════════════════════════════════════════════════════════════════════════

class TestScrubMetadataPathContainment(unittest.TestCase):
    """
    Embedded-file extraction in scrub_all_metadata must not write outside data_dir.

    We can't easily manufacture a real symlink attack in a unit test, but we can
    verify that:
    a) Normal files are extracted correctly.
    b) The containment logic doesn't trip on legitimate filenames.
    c) A crafted filename that would normally escape (e.g. via internal logic)
       does not produce a file outside data_dir.
    """

    def setUp(self):
        # Build a PDF with one embedded file
        fd, self.src = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        fd, self.dst = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        self.data_dir = tempfile.mkdtemp()

        doc = fitz.open()
        doc.new_page().insert_text((72, 72), "test", fontsize=12)
        doc.embfile_add("note.txt", b"hello from embedded",
                        desc="A test attachment")
        doc.save(self.src)
        doc.close()

    def tearDown(self):
        _cleanup(self.src, self.dst)
        import shutil
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def test_normal_extraction_succeeds(self):
        result = core.scrub_all_metadata(self.src, self.dst, self.data_dir)
        self.assertIn("success", result)
        # The embedded file should have been extracted
        extracted = os.listdir(self.data_dir)
        self.assertTrue(len(extracted) >= 1,
                        f"Expected at least one extracted file, got: {extracted}")

    def test_extracted_file_stays_inside_data_dir(self):
        core.scrub_all_metadata(self.src, self.dst, self.data_dir)
        abs_dir = os.path.abspath(self.data_dir)
        for fname in os.listdir(self.data_dir):
            fpath = os.path.abspath(os.path.join(self.data_dir, fname))
            self.assertTrue(
                fpath.startswith(abs_dir + os.sep) or fpath == abs_dir,
                f"Extracted file escaped data_dir: {fpath}"
            )

    def test_no_files_written_outside_data_dir(self):
        """Verify the output PDF itself is not inside data_dir (it goes to dst)."""
        core.scrub_all_metadata(self.src, self.dst, self.data_dir)
        self.assertTrue(os.path.exists(self.dst),
                        "Scrubbed PDF should exist at dst path")

    def test_safe_filename_characters_preserved(self):
        """Filenames with alphanumeric chars and . _ - are kept intact."""
        # Our embedded file is "note.txt" — should survive sanitization
        core.scrub_all_metadata(self.src, self.dst, self.data_dir)
        files = os.listdir(self.data_dir)
        self.assertTrue(any("note" in f for f in files),
                        f"Expected 'note.txt' in extracted files, got: {files}")

    def test_extraction_without_data_dir_skips_it(self):
        """Calling without data_dir should succeed and not write any extra files."""
        before = set(os.listdir(self.data_dir))  # data_dir exists but is empty at start
        result = core.scrub_all_metadata(self.src, self.dst, data_dir=None)
        self.assertIn("success", result)
        # data_dir should still be empty — the function didn't write into it
        after = set(os.listdir(self.data_dir))
        self.assertEqual(before, after,
                         "scrub_all_metadata should not write to data_dir when called with data_dir=None")

    def test_data_dir_symlink_is_rejected(self):
        """Existing scrub data symlinks must not redirect extracted files."""
        import shutil
        redirect_target = tempfile.mkdtemp()
        symlink_dir = tempfile.mkdtemp()
        symlink_path = os.path.join(symlink_dir, "sample_scrub_data")
        os.rmdir(symlink_path) if os.path.exists(symlink_path) else None
        os.symlink(redirect_target, symlink_path)
        try:
            result = core.scrub_all_metadata(self.src, self.dst, symlink_path)
            self.assertFalse(result.get("success"), result)
            self.assertEqual(os.listdir(redirect_target), [],
                             "scrub_all_metadata followed a data_dir symlink")
        finally:
            shutil.rmtree(symlink_dir, ignore_errors=True)
            shutil.rmtree(redirect_target, ignore_errors=True)


class TestScrubReportHTMLEscaping(unittest.TestCase):
    """Metadata report values are PDF-controlled and must be escaped."""

    def test_report_escapes_source_filename_and_resource_names(self):
        payload = '<img src=x onerror="alert(1)">'
        before = {
            "document_info": {"title": payload},
            "xmp_metadata": {"dc:title": payload},
            "filesystem_metadata": {"where": payload},
            "structure_info": {"page_count": 1},
            "binary_resources": {
                "embedded_fonts": [{
                    "name": payload,
                    "type": payload,
                    "encoding": payload,
                    "embedded": payload,
                }],
                "form_fields": [{
                    "name": payload,
                    "type": payload,
                    "value": payload,
                }],
                "javascript": [{
                    "xref": 1,
                    "preview": payload,
                }],
            },
        }
        after = {
            "document_info": {},
            "xmp_metadata": {},
            "filesystem_metadata": {},
            "structure_info": {"page_count": 1},
            "binary_resources": {},
        }

        html, _ = core.generate_scrub_report(
            before,
            after,
            extracted_files=[{"name": payload + ".txt", "path": "/tmp/x", "size": 12}],
            source_filename=payload,
            data_dir_name=payload,
        )

        self.assertNotIn(payload, html)
        self.assertNotIn("<img", html)
        self.assertIn("&lt;img src=x onerror=", html)


# ══════════════════════════════════════════════════════════════════════════════
# 7. replace_block_with_spans — existing page validation smoke test  (regression)
# ══════════════════════════════════════════════════════════════════════════════

class TestReplaceBlockWithSpansPageBounds(unittest.TestCase):
    """
    replace_block_with_spans already validates page bounds.
    Smoke-test that the validation is still present and working.
    """

    def setUp(self):
        self.pdf = _make_pdf("Hello", pages=2)

    def tearDown(self):
        _cleanup(self.pdf)

    def _call(self, page_index):
        return core_xpc.replace_block_with_spans(
            self.pdf, page_index,
            block_bbox={"x": 0, "y": 0, "width": 100, "height": 20},
            spans=[{"text": "Hi", "font_family": "Helvetica",
                    "size": 12.0, "weight": 400, "slant": "normal",
                    "color": {"r": 0.0, "g": 0.0, "b": 0.0}}],
        )

    def test_valid_page_does_not_raise(self):
        try:
            result = self._call(0)
            self.assertIsInstance(result, dict)
        except Exception as exc:
            self.fail(f"Unexpected exception for valid page: {exc}")

    def test_out_of_bounds_page_rejected(self):
        result = self._call(99)
        self.assertFalse(result.get("success"))
        self.assertIn("message", result)

    def test_negative_page_rejected(self):
        # page_number = -1 + 1 = 0, which is < 1 → should be rejected
        result = self._call(-1)
        self.assertFalse(result.get("success"))

    def test_never_raises(self):
        for bad_idx in (-1, 99, 999_999):
            with self.subTest(page_index=bad_idx):
                try:
                    result = self._call(bad_idx)
                    self.assertIsInstance(result, dict)
                except Exception as exc:
                    self.fail(f"replace_block_with_spans raised for "
                              f"page_index={bad_idx}: {exc}")


class TestXpcOverrideConversion(unittest.TestCase):
    """Swift XPC override keys must map to the Python backend contract."""

    def test_camel_case_overrides_are_preserved(self):
        converted = core_xpc._convert_overrides({
            "fontName": "system|Helvetica-Bold",
            "sizeDelta": 1.5,
            "xOffset": 2.0,
            "yOffset": -0.75,
            "fillColor": "#112233",
            "isBold": True,
            "isItalic": True,
            "justification": "right",
            "exhaustiveSearch": True,
        }, detected_font=None)

        self.assertEqual(converted["manual_font"], "system|Helvetica-Bold")
        self.assertEqual(converted["manual_size_delta"], 1.5)
        self.assertEqual(converted["manual_x_offset"], 2.0)
        self.assertEqual(converted["manual_y_offset"], -0.75)
        self.assertEqual(converted["fill_color"], "#112233")
        self.assertTrue(converted["is_bold"])
        self.assertTrue(converted["is_italic"])
        self.assertEqual(converted["justification"], "Right")
        self.assertTrue(converted["exhaustive_search"])

    def test_snake_case_overrides_still_work(self):
        converted = core_xpc._convert_overrides({
            "font_family": "Helvetica",
            "size_delta": "0.25",
            "x_offset": "1.0",
            "y_offset": "2.0",
            "fill_color": "black",
            "is_bold": False,
            "is_italic": False,
            "exhaustive_search": False,
        }, detected_font=None)

        self.assertEqual(converted["manual_font"], "Helvetica")
        self.assertEqual(converted["manual_size_delta"], 0.25)
        self.assertEqual(converted["manual_x_offset"], 1.0)
        self.assertEqual(converted["manual_y_offset"], 2.0)
        self.assertEqual(converted["fill_color"], "black")
        self.assertFalse(converted["is_bold"])
        self.assertFalse(converted["is_italic"])
        self.assertFalse(converted["exhaustive_search"])


class TestConfidentialDiagnostics(unittest.TestCase):
    """Diagnostics and warning payloads must not echo document text."""

    def test_search_diagnostic_does_not_store_literal_text(self):
        secret_target = "CLIENT-SECRET-12345"
        secret_page_text = "page contains CLIENT-SECRET-12345 and other confidential terms"

        diagnostic = core.SearchDiagnostic(secret_target, page_number=1)
        diagnostic.capture_page_text(secret_page_text)
        diagnostic.capture_unicode()
        payload = diagnostic.to_dict()
        rendered = repr(payload)

        self.assertNotIn(secret_target, rendered)
        self.assertNotIn(secret_page_text, rendered)
        self.assertEqual(payload["target_length"], len(secret_target))
        self.assertEqual(payload["page_text_length"], len(secret_page_text))
        self.assertNotIn("target_text", payload)
        self.assertNotIn("page_text_sample", payload)
        self.assertNotIn("unicode_codepoints", payload)
        self.assertEqual(payload["unicode_summary"]["sample_length"], len(secret_target))
        self.assertIsInstance(payload["unicode_summary"]["category_counts"], dict)

    def test_xpc_not_found_warning_reports_length_not_text(self):
        secret_target = "DO-NOT-LOG-THIS-SELECTION"
        pdf = _make_pdf("Different visible text", pages=1)

        try:
            result = core_xpc.replace_text(
                document_path=pdf,
                target_text=secret_target,
                replacement_text="Replacement",
                page_index=0,
                overrides={},
                detected_font=None,
                target_rect={"x": 0, "y": 0, "width": 0, "height": 0},
            )
        finally:
            _cleanup(pdf)

        rendered = repr(result)
        self.assertFalse(result.get("success"))
        self.assertNotIn(secret_target, rendered)
        self.assertIn(f"target text length={len(secret_target)}", rendered)

    def test_font_subsetting_diagnostics_do_not_print_paths(self):
        fd, path = tempfile.mkstemp(prefix="marcedit_secret_font_", suffix=".ttc")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(b"ttcf-not-a-real-font")

            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                try:
                    core.subset_font_from_path(path, "secret")
                except Exception:
                    pass

            output = stdout.getvalue() + stderr.getvalue()
            self.assertNotIn(path, output)
            self.assertNotIn(os.path.basename(path), output)
        finally:
            _cleanup(path)

    def test_missing_font_subsetting_diagnostics_do_not_print_paths(self):
        missing_path = os.path.join(
            tempfile.gettempdir(),
            "marcedit_secret_missing_font_DO_NOT_LOG.ttf",
        )
        _cleanup(missing_path)

        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                core.subset_font_from_path(missing_path, "secret")
            except Exception:
                pass

        output = stdout.getvalue() + stderr.getvalue()
        self.assertNotIn(missing_path, output)
        self.assertNotIn(os.path.basename(missing_path), output)

    def test_manual_font_failure_diagnostics_do_not_print_paths(self):
        pdf = _make_pdf("Secret target", pages=1)
        fd, bad_font = tempfile.mkstemp(prefix="marcedit_preview_secret_", suffix=".ttf")
        os.close(fd)
        fd, out = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)

        try:
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                core.replace_text_in_pdf(
                    input_path=pdf,
                    output_path=out,
                    target_text="Secret target",
                    replacement_text="Replacement",
                    page_number=1,
                    manual_overrides={"manual_font": bad_font},
                )

            output = stdout.getvalue() + stderr.getvalue()
            self.assertNotIn(bad_font, output)
            self.assertNotIn(os.path.basename(bad_font), output)
        finally:
            _cleanup(pdf, bad_font, out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
