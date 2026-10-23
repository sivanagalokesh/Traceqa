# TraceQA evaluation protocol

## Evaluation on the supplied CT-200 manuals

The supplied PDFs are included at `data/ct200_manual_v1.pdf` and `data/ct200_manual_v2.pdf`. Ground-truth section headings, parent relationships, and the expected version changes are recorded in `ground_truth_ct200.json` after reviewing the PDFs.

Run from the repository root:

```bash
python -m evaluation.evaluate_ct200
python -m pytest -q
```

The evaluation script writes `ct200_evaluation_report.json`. On this labeled pair, the parser recovered 27/27 section headings and parent assignments in v1, 28/28 in v2, matched the 27 common section identities, flagged the four manually labeled modified sections, and detected the added `5.3 Data Export` section. Section-level precision/recall/F1 are 1.00 for this small dataset. This is not a general accuracy guarantee and does not evaluate semantic equivalence after section renames or moves.

An isolated integration test additionally runs the real API flow: ingest v1, create a version-pinned selection, generate QA cases, ingest v2, and verify that the prior generation is marked stale.

## What is not measured

- Full-document CER/WER: no complete human transcription has been prepared.
- General OCR accuracy: the supplied PDFs contain selectable text, so OCR was not needed for these files.
- Semantic accuracy or clinical safety of generated QA cases: generated cases need human review and scoring.
- Robustness on renamed/moved headings, duplicate reordering, image-only PDFs, and other manuals.
- Generalization beyond this pair of documents.

## Ground-truth protocol for future versions

1. Have a reviewer label section headings, parent-child links, cross-version section matches, actual changes, and generated cases affected by each change.
2. Include normal cases and difficult cases: duplicate headings, renamed/moved sections, changed thresholds or units, deleted warnings, table content, page headers/footers, OCR errors, and unrelated edits.
3. Freeze the labels before evaluation. Keep a separate holdout set for final reporting.
4. Report sample counts and confusion matrices alongside precision, recall, F1, and false-negative rate. Break out critical changes rather than averaging them with ordinary edits.
5. For generated test cases, use at least two reviewers where possible. Score factual correctness, coverage, executability, traceability, and version correctness from 0–2; report average scores and critical unsupported-claim counts.

`metrics.py` contains precision/recall/F1, character error rate (CER), and human-rubric summary helpers. They are metric calculators; the ground-truth labels and predictions must be supplied by an evaluation run.
