# TraceQA Approach Document

## 1. Goal
TraceQA converts the CardioTrack CT-200 manual into a navigable versioned tree, supports source-pinned selections, generates 3–5 QA test-case ideas, and exposes whether saved generations may be stale after a new manual version is ingested.

## 2. Parsing strategy
The implementation extracts the supplied PDFs directly using PyMuPDF text blocks and layout coordinates, reconstructs substantial detected tables as Markdown, and then applies CT-200-focused heading heuristics. `pypdf` is a fallback selectable-text extractor; Tesseract OCR is an optional fallback for scanned PDFs when Tesseract and Poppler are installed. Numbered headings establish their actual section depth; a stack assigns each node to the nearest existing lower-level ancestor. Synthetic page markers are excluded, and numbered list items containing a colon are not treated as section headings. Every node stores a SHA-256 hash over normalized heading + body text. Duplicate headings remain separate using a parent-path + normalized-heading + occurrence key.

This approach was selected because it is lightweight, debuggable, and does not require a paid document AI service. It is not a universal PDF parser. The supplied PDFs contain selectable text, so OCR was not needed for this dataset. The main specifications and error-code tables are retained as Markdown within their sections, but table detection can produce false positives on other PDFs and captions/figures are not represented as first-class nodes. Visual inspection and fixture-based assertions remain necessary.

## 3. Version model and matching
Each ingestion creates a new `DocumentVersion`; earlier nodes are never overwritten. A logical key based on parent path, normalized heading, and duplicate occurrence matches likely corresponding sections. Matching nodes with equal hashes are `unchanged`; matching nodes with differing hashes are `modified`; unmatched nodes are `new`. The API's diff endpoint compares text for a matching logical key and reports additions/removals when a node does not exist in both versions.

Known failure modes: renamed/reparented headings change the key; inserting an earlier duplicate can shift occurrence numbers; parent path changes can cascade to descendants. This is a transparent baseline, not semantic equivalence. A stronger matcher would combine exact path matches, normalized title similarity, body similarity, and explicit confidence thresholds, then route ambiguous candidates for review.

## 4. Data model and storage
SQLite via SQLAlchemy stores document identity, version records, section nodes, named selections, and selection items. A selection item stores the exact node ID, version ID, content hash, heading, and body snapshot. This ensures retrieval does not silently resolve an old selection to newer text. Generated JSON output is stored in `data/generations.json`, a justified lightweight document store for this single-user prototype. For concurrent production use, replace it with MongoDB or a transactional database and add locking/atomic writes.

## 5. API and UI
FastAPI exposes ingestion, overview, version listing, root sections, node retrieval, search, diffs, selections, generation, and generation retrieval. The frontend is a responsive dashboard with overview metrics, upload/version history, tree explorer, content/hash details, selection flow, generated QA cards, and a traceability monitor. No frontend framework is required for the assignment; the vanilla HTML/CSS/JS frontend keeps the deployment simple.

## 6. LLM prompt and output validation
The optional provider is an OpenAI-compatible chat-completions endpoint. The prompt requires JSON containing 3–5 cases with title, objective, preconditions, steps, expected result, priority, and source references. The response is parsed as JSON and each case is validated by Pydantic. The provider call is attempted once with a 45-second timeout. If the request, JSON parsing, schema validation, source-reference check, or numeric-grounding check fails, a local deterministic fallback returns three source-aware test ideas that avoid inventing thresholds. This deliberately favors a predictable safe response over repeated calls; production use should add bounded retries/backoff and structured-output support. Configure a provider using environment variables. The fallback ensures the API remains demonstrable without an API key.

Repeated generation policy: by default, a second request for the same selection returns the most recent stored generation (idempotent behavior). Passing `force_new: true` creates another generation. This avoids unnecessary LLM calls while allowing intentional regeneration.

## 7. Staleness detection
At retrieval time, each generation's original source node is matched by logical key against the latest document version. A differing content hash or missing node marks the generation stale. This is conservative and makes the status queryable through the retrieval API. It does not judge whether a change is clinically important; a punctuation change and a changed pressure limit both flag review. A future version could classify semantic/risk-sensitive changes, but must not automatically clear a stale flag without review.

## 8. Validation and debugging
The parser was evaluated against the supplied CT-200 v1/v2 PDFs. The fixture tests assert the exact numbered-heading inventory, expected parent for every section, preservation of the two main tables as Markdown, and the observed change inventory. The source PDFs expose an unusual `2.1.1.1` heading without a visible `2.1.1` parent, section 3.4 appearing before 3.3 in reading order, a numbered classification list that must remain body content, tables whose cells must remain separated, and page-boundary paragraph continuation. Explicit parser regression tests cover duplicate headings, missing intermediate parents, numbered list items with colons, page sentinels, parent-child hierarchy, and content-hash changes. A source inconsistency also remains in v2: Section 4.1 prose says the overpressure condition should vent within 2 seconds while the E3 table says 1.5 seconds. TraceQA preserves the extracted source statements and does not silently reconcile them; this discrepancy requires document-owner review. The parser preserves the actual depth and attaches 2.1.1.1 to the nearest existing ancestor 2.1. Table/caption extraction should still be visually checked before submission.

## 9. Required decision log
1. **Most likely silent failure:** heading misclassification can create a plausible but incorrect hierarchy. Detect it using visual review, expected-path assertions, and page-level regression fixtures.
2. **Simplicity chosen:** path-based matching is simpler than semantic matching but can misidentify renamed, moved, or reordered duplicate sections. These false change reports would be the first weakness in production.
3. **Unsupported input:** scanned PDFs without configured OCR dependencies produce an explicit error. This is preferable to silently accepting empty or misleading content.

## 10. What I would improve next
- Preserve page numbers and bounding boxes for stronger auditability.
- Extract figures/captions into first-class nodes and retain page provenance.
- Use a confidence-scored version matcher with reviewable ambiguous matches.
- Use MongoDB or another transactional store for generated records under concurrent requests.
- Add provider-specific structured output, bounded retries/backoff, timeouts, and audit logs.
- Add a source-grounding validator to reject generated expected results that introduce values absent from the selected text.

## 11. Tight evaluation protocol
Evaluation is separated from implementation tests. `evaluation/ground_truth_ct200.json` contains manually reviewed heading/parent labels and the expected changes for these two PDFs. Run `python -m evaluation.evaluate_ct200` to create `evaluation/ct200_evaluation_report.json`. On this pair, the current parser recovers all 27 numbered section headings and parent assignments in v1 and all 28 in v2; it matches the 27 shared section identities, flags four modified sections, and detects the added `5.3 Data Export` section. Section-level precision/recall/F1 are 1.00 for this labeled pair. These are measured results on a small two-document dataset, not a general accuracy guarantee. Full-document CER/WER and human-scored generated-case quality have not been measured. A separate automated API integration test covers the real v1-ingest → selection → generation → v2-ingest → stale-retrieval workflow. LLM-generated cases require separate human scoring for factual correctness, coverage, executability, traceability, and version correctness, plus a separate count of critical unsupported claims.
