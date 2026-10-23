# TraceQA — Medical Document Intelligence

**Live demo:** https://traceqa.onrender.com/  
**API documentation:** https://traceqa.onrender.com/docs  
**GitHub repository:** https://github.com/sivanagalokesh/Traceqa

A full-stack starter implementation for the Tri9T AI Engineering Internship assignment. TraceQA ingests a technical manual, reconstructs a section tree, preserves versions, pins selections to source snapshots, generates schema-validated QA test-case ideas, and surfaces stale traceability.

## Features

- **Frontend:** responsive dashboard, document upload, version history, section tree/search, node details and hashes, version comparison, QA generation, and traceability monitor.
- **Backend:** FastAPI + Pydantic + SQLAlchemy + SQLite.
- **Document parsing:** PyMuPDF text extraction with Markdown reconstruction for substantial detected tables; `pypdf` fallback and optional Tesseract OCR fallback for scanned PDFs. Section-tree display sorts numbered siblings by their printed section number. Heading recognition remains CT-200-focused and heuristic.
- **Versioning:** every ingestion creates a new immutable version. A logical key derived from parent path, normalized heading, and occurrence distinguishes duplicate headings. Hashes flag body/heading changes.
- **Selection snapshots:** selections store node/version IDs, content hashes, headings, and text snapshots, so they survive future re-ingestion.
- **Generation storage:** generated output is stored in `data/generations.json`, a simple JSON document store justified for a single-user internship prototype. SQLite stores document structure, versions, and selections.
- **QA generation:** source-aware local templates produce distinct test ideas for battery-life, error-code, cuff-inflation, and data-export sections. An optional OpenAI-compatible endpoint can be configured; its response is schema-validated and conservatively rejected if it introduces numeric values absent from the selected source. The local generator is used when no configured response passes validation.
- **Staleness:** retrieval compares each generated source hash with the latest version's matching logical node. Any change is conservatively flagged.

## Quick start

Requires Python 3.10+.

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Windows: copy .env.example .env
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000. Interactive API docs: http://127.0.0.1:8000/docs.

The actual assignment PDFs are included in `data/ct200_manual_v1.pdf` and `data/ct200_manual_v2.pdf`. The UI's **Load demo content** button creates illustrative sample text only; use the included PDFs for assignment evaluation. The parser processes the PDF directly, as required by the assignment update, and reconstructs the main specifications and error-code tables as Markdown inside the relevant section body. The section explorer renders Markdown tables as actual HTML tables. Table extraction is heuristic and should be reviewed against the rendered PDF.

## Optional LLM configuration

Copy `.env.example` to `.env`, then set `LLM_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL`. For Groq, the default base URL is `https://api.groq.com/openai/v1`. The application loads `.env` automatically using `python-dotenv`. You can also export these variables in your shell.

Without a key, generation uses the source-aware local generator so the full flow remains demonstrable. Always review generated cases against the cited manual before using them in a real device test.

## OCR for scanned PDFs

Text-based PDFs work with `pypdf`. For image-only scans, install Tesseract OCR and Poppler for your OS, then uncomment `pytesseract` and `pdf2image` in `requirements.txt` and reinstall. OCR accuracy must be manually checked for thresholds, units, warnings, and tables before treating the output as authoritative.

## End-to-end v1 → v2 workflow

1. Start the server and upload the supplied v1 manual through **Documents & versions**.
2. Review the extracted tree and select one or more sections in **Section explorer**.
3. Name and create the selection, then generate QA ideas.
4. Upload the supplied v2 manual using the same upload action. It becomes the next version; v1 remains stored.
5. Open **QA test cases** or **Traceability**. Source hashes are compared against the latest matching logical nodes and stale generations are flagged.
6. Use `/api/nodes/{node_id}/diff` to inspect a lightweight line diff.

The version matcher currently uses parent-path + normalized-heading + duplicate occurrence. It works for stable section paths and duplicate headings in a predictable order, but a rename, reparenting, or insertion before a duplicate heading can make a logical node appear new/removed. A production system should add confidence-scored fuzzy matching and explicit human review for ambiguous matches.

## API overview

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Health check |
| GET | `/api/overview` | Dashboard metrics |
| POST | `/api/ingest` | Upload and ingest PDF as next version |
| POST | `/api/demo/seed` | Add illustrative demo manual if database is empty |
| GET | `/api/versions` | List revisions |
| GET | `/api/sections?version=1` | List root sections for a version |
| GET | `/api/nodes/{id}` | Node body, hash, and immediate children |
| GET | `/api/search?q=pressure&version=1` | Search headings and body text |
| GET | `/api/nodes/{id}/diff?from_version=1&to_version=2` | Compare a logical node across versions |
| POST | `/api/selections` | Create a version-pinned selection |
| GET | `/api/selections/{id}` | Resolve saved source snapshots |
| POST | `/api/generations` | Generate test ideas from a selection |
| GET | `/api/generations?selection_id=1` | Retrieve generations with staleness status |
| GET | `/api/generations/{id}` | Retrieve one generation with status |

## Tests and real-manual evaluation

```bash
python -m pytest -q  # currently 20 automated tests
python -m evaluation.evaluate_ct200
```

The test suite includes the supplied PDFs as fixtures and an isolated API integration test that ingests v1, creates a version-pinned selection, generates cases, ingests v2, and verifies stale status. Explicit parser edge-case tests cover duplicate headings, a missing intermediate parent heading, numbered classification list items with colons, page sentinels, hierarchy, and content-hash changes. The evaluation script writes `evaluation/ct200_evaluation_report.json` and checks manually labeled section headings, parent assignments, logical section matching, modified/added sections, and selected table extraction. It currently reports 27/27 headings and parent assignments for v1, 28/28 for v2, and identifies the four modified sections plus the new `5.3 Data Export` section. On this particular pair, those measured section-level precision/recall/F1 values are 1.00. This is a small, manually labeled two-document evaluation—not a general accuracy guarantee.

Full-document CER/WER is not reported because no complete human transcription was created. The parser evaluation report is not a human assessment of generated QA quality; review cases for factual correctness, coverage, executability, and traceability before submission. The v2 source has an unresolved internal discrepancy: Section 4.1 overpressure prose says 2 seconds, while the E3 error table says 1.5 seconds. The app does not reconcile this conflict automatically; flag it for document-owner review.

## Data model

- `Document`: stable document identity and latest version number.
- `DocumentVersion`: immutable ingestion record.
- `SectionNode`: version-specific node with logical key, parent, body, order, and SHA-256 content hash.
- `Selection` / `SelectionItem`: named selection with pinned version, hash, and text snapshots.
- `data/generations.json`: generated test cases, source node snapshots, model name, timestamp, and retrieval-time staleness result.

## Engineering limitations / decision log

1. **Most likely silent failure:** a heading classifier can mistake an all-caps sentence or numbered paragraph for a section heading, creating a plausible but incorrect tree. Catch it with visual/manual comparison against the source PDF, page-level extraction logs, and fixture tests that assert expected parent-child paths.
2. **Simplicity over correctness:** logical matching uses path + title + duplicate occurrence rather than semantic matching. Renames/reparenting or duplicate reordering can cause false new/removed statuses. A production system needs fuzzy candidate matching, confidence scores, and review of ambiguous mappings.
3. **Unsupported input:** image-only PDFs without Tesseract/Poppler installed cannot be parsed. The API returns an explicit 422 error rather than silently storing an empty tree. Tables are currently extracted as text rather than reliably reconstructed into structured cells.

## Git commit history

Use incremental commits rather than one final commit. Example:

```bash
git init
git add README.md requirements.txt .env.example
git commit -m "chore: scaffold TraceQA project"
git add app/database.py app/models.py app/schemas.py
git commit -m "feat: add versioned document data model"
git add app/parser.py tests/test_parser.py
git commit -m "feat: parse manual structure and test hierarchy edge cases"
git add app/generator.py app/main.py
git commit -m "feat: add ingestion, selection, generation, and traceability APIs"
git add frontend
git commit -m "feat: build responsive TraceQA dashboard"
```

Never claim the parser handles every irregularity until tests against the supplied PDFs demonstrate it.

## Tight evaluation and ground-truth metrics

Use the evaluation protocol in [`evaluation/README.md`](evaluation/README.md) and fill [`evaluation/ground_truth_template.json`](evaluation/ground_truth_template.json) with manually reviewed examples from the real CT-200 v1/v2 PDFs. The included metric helpers calculate precision, recall, F1, false-negative rate, character error rate (CER), and human-rubric summaries; they do not evaluate the application automatically without ground-truth labels and system predictions.

Recommended reporting: section hierarchy and version matching precision/recall/F1; critical-change recall and false-negative count; stale-case precision/recall/F1; human-scored LLM quality for factual correctness, coverage, executability, traceability, and version correctness; and API regression pass rate. Always include sample counts and a confusion matrix. Proposed targets are not measured results. In particular, 100% recall on a defined critical-change suite is not a guarantee of universal safety.
