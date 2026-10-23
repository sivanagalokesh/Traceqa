# TraceQA update checklist

## Implemented in this update

- [x] Replaced broad generic local QA cases with source-aware templates for battery life, error codes, cuff inflation, and data export.
- [x] Added distinct test purposes for documented behavior, explicit prerequisites, and requirement-completeness review.
- [x] Added source references containing section node, heading, and source version.
- [x] Added conservative numeric-grounding validation for optional LLM output; invalid output falls back to local generation.
- [x] Added tests for battery thresholds/estimates, E3 timing, E6 Bluetooth sync, CSV export fields, sync prerequisites, and unsupported numeric values.
- [x] Rendered Markdown table content as an HTML table in the section explorer.
- [x] Sorted numbered sections and children by their printed section number in the tree APIs.
- [x] Updated PDF extraction to use the current `pymupdf` import rather than the legacy `fitz` alias.
- [x] Updated README with current behavior, run commands, and evaluation limitations.
- [x] Added the update checklist to the project package.
- [x] Verified automated tests: `17 passed`.
- [x] Re-ran CT-200 evaluation: v1 headings 27/27, v2 headings 28/28, parent assignments 27/27 and 28/28, expected modifications 4/4, added section 5.3 detected, and table smoke checks passed.
- [x] Checked frontend JavaScript syntax with `node --check frontend/app.js`.

## Still requires manual review or further evaluation

- [ ] Visually verify all extracted tables and section order against both source PDFs.
- [ ] Resolve the source-manual conflict where v2 overpressure prose states 2 seconds but the E3 table states 1.5 seconds; the application intentionally flags rather than reconciles this.
- [ ] Human-score generated QA cases for correctness, coverage, and executability.
- [ ] Add labeled tests for removed sections, renamed headings, and reordered duplicate headings.
- [ ] Test scanned/image-only PDFs with OCR and verify the OCR output manually.
- [ ] Test the app from a clean Windows environment with a fresh virtual environment and database.
- [ ] Deploy publicly only if the assignment requires a hosted URL; this package is a local runnable app, not a hosted deployment.

## Run locally on Windows PowerShell

```powershell
cd traceqa
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m pytest -q
python -m evaluation.evaluate_ct200
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000` for the UI or `http://127.0.0.1:8000/docs` for API documentation.
