# ⚡ TESTING QUICK START GUIDE
## Marcedit PDF Editor - Run Tests in 60 Seconds

---

## 🚀 FASTEST WAY TO RUN TESTS

### Option 1: TUI Menu (Recommended)
```bash
cd /Users/mhm/Documents/Dev/Marcedit
python3 build_tui.py
# Select option 8 (Run all pytest tests)
```

### Option 2: Direct pytest
```bash
cd /Users/mhm/Documents/Dev/Marcedit
pytest tests/ -v
```

### Option 3: CI Script
```bash
cd /Users/mhm/Documents/Dev/Marcedit
./ci_test.sh
```

---

## 📋 WHAT TESTS DO WE HAVE?

**Total Tests**: 61
- **Core Tests**: 34 (test_editor_core.py)
- **Reflow Tests**: 27 (test_reflow_synthesizer.py)

**Execution Time**: ~0.14 seconds

**Pass Rate**: 100% (61/61 passing)

---

## 🎯 COMMON TESTING SCENARIOS

### "I want to run all tests quickly"
```bash
python3 build_tui.py
# Option 8: Run pytest (All Tests)
```

### "I only changed core.py"
```bash
python3 build_tui.py
# Option 9: Run pytest (Core Tests Only)
```

### "I only changed reflow.py or synthesizer.py"
```bash
python3 build_tui.py
# Option 10: Run pytest (Reflow Tests Only)
```

### "I want to see code coverage"
```bash
python3 build_tui.py
# Option 11: Run pytest with Coverage
# Then: open htmlcov/index.html
```

### "I'm about to commit code"
```bash
git add .
git commit -m "My changes"
# Pre-commit hook runs tests automatically!
```

### "I want to run CI tests locally"
```bash
./ci_test.sh
```

---

## 🛠️ IF TESTS FAIL

### Step 1: Run with verbose output
```bash
pytest tests/ -v --tb=long
```

### Step 2: Run only failed tests
```bash
pytest tests/ --lf
```

### Step 3: Run specific test
```bash
pytest tests/test_editor_core.py::TestReferenceCharMetrics::test_none_page_returns_none -v
```

### Step 4: Check dependencies
```bash
pip3 install --user pytest PyMuPDF
```

---

## 📊 EXPECTED OUTPUT

### Success
```
collected 61 items

test_editor_core.py .......................... (34 tests)
test_reflow_synthesizer.py ............... (27 tests)

========================= 61 passed in 0.14s =========================
```

### With Coverage
```
---------- coverage: platform darwin, python 3.11.14 ----------
Name                                             Stmts   Miss  Cover   Missing
-----------------------------------------------------------------------
editor_pkg/core.py                                 280      5    98%
editor_pkg/reflow.py                               240      8    97%
editor_pkg/synthesizer.py                          180      3    99%
editor_pkg/harvester.py                            120      2    98%
-----------------------------------------------------------------------
TOTAL                                              820     18    98%

========================= 61 passed in 0.25s =========================
```

---

## 🔧 TROUBLESHOOTING

### "pytest: command not found"
```bash
pip3 install --user pytest
```

### "No module named 'fitz'"
```bash
pip3 install --user PyMuPDF
```

### "ImportError: No module named 'editor_pkg'"
```bash
cd /Users/mhm/Documents/Dev/Marcedit
export PYTHONPATH="/Users/mhm/Documents/Dev/Marcedit/Sources/Marcedit/python_site:$PYTHONPATH"
pytest tests/ -v
```

### "Tests pass but app fails"
- Tests use system python, app uses bundled python
- Build app first: `python3 build_tui.py` → Option 2
- Then test with bundled python (auto-detected by TUI)

---

## 📚 FULL DOCUMENTATION

See `BUILD_SYSTEM_IMPROVEMENTS.md` for:
- Detailed TUI options (8-12)
- CI/CD setup
- Coverage reporting
- Pre-commit hooks
- Smart Python detection
- Best practices

---

## ✅ CHECKLIST FOR DEVELOPERS

Before pushing code:
- [ ] Run `pytest tests/ -v` (all 61 tests pass)
- [ ] Check coverage with `pytest tests/ --cov`
- [ ] Test with real PDFs manually
- [ ] Update tests if adding new features
- [ ] Commit passes pre-commit hook

---

## 🎓 LEARN MORE

### How Tests Work
1. **Unit tests** test individual functions in isolation
2. **Fixtures** create sample PDFs for testing
3. **Assertions** verify expected behavior
4. **Coverage** measures how much code is tested

### Adding New Tests
```python
# tests/test_editor_core.py
def test_my_new_feature(self):
    """Test my new feature."""
    # Setup
    pdf_path = tmp_path / "test.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 100), "Hello", fontsize=12)
    doc.save(pdf_path)
    doc.close()

    # Test
    result = my_function(page, "Hello")

    # Assert
    assert result is not None
    assert result == "expected_value"
```

### Test Naming Convention
- Test class: `TestFeatureName`
- Test method: `test_specific_behavior`
- Use descriptive names that explain what is being tested

---

**Need help?** See `BUILD_SYSTEM_IMPROVEMENTS.md` or run `python3 build_tui.py` and select option 7 (Show Build Info).

---

*Quick Start Guide: January 22, 2026*
*Test Count: 61*
*Pass Rate: 100%*
*Execution Time: 0.14s*
