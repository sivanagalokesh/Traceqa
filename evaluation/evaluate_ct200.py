"""Evaluate TraceQA parsing/version-change behavior against supplied CT-200 PDFs.

The ground truth is manually transcribed in ground_truth_ct200.json. Metrics here
cover numbered section headings, parent assignments, exact-path version matching,
and section-level change detection. They do not measure full-text CER, table-cell
accuracy beyond selected smoke checks, or semantic quality of generated LLM cases.
"""
from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.parser import extract_pdf, parse_text  # noqa: E402
from evaluation.metrics import precision_recall_f1  # noqa: E402


def norm(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).strip()


def load_nodes(path: Path):
    text, method = extract_pdf(path)
    return text, method, parse_text(text)


def binary_metrics(expected: set[str], predicted: set[str]) -> dict:
    labels = sorted(expected | predicted)
    if not labels:
        return {"n": 0, "tp": 0, "fp": 0, "fn": 0, "tn": 0,
                "precision": None, "recall": None, "f1": None,
                "accuracy": None, "false_negative_rate": None,
                "note": "No expected or predicted positive examples; metrics are undefined."}
    return precision_recall_f1(
        [int(label in expected) for label in labels],
        [int(label in predicted) for label in labels],
    )


def main() -> int:
    gt = json.loads((ROOT / "evaluation" / "ground_truth_ct200.json").read_text(encoding="utf-8"))
    parsed = {}
    texts = {}
    methods = {}
    for version in ("v1", "v2"):
        path = ROOT / gt["source_files"][version]
        if not path.exists():
            print(f"ERROR: missing source PDF: {path}", file=sys.stderr)
            return 2
        texts[version], methods[version], parsed[version] = load_nodes(path)

    report = {"source_files": gt["source_files"], "extraction_methods": methods, "versions": {}}
    maps = {}
    for version in ("v1", "v2"):
        expected_parents = {norm(k): (norm(v) if v else None) for k, v in gt[f"parents_{version}"].items()}
        section_nodes = [n for n in parsed[version] if norm(n.heading) != "Document introduction"]
        predicted_headings = {norm(n.heading) for n in section_nodes}
        expected_headings = set(expected_parents)
        heading = binary_metrics(expected_headings, predicted_headings)
        by_heading = {norm(n.heading): n for n in section_nodes}
        correct_parent = 0
        wrong_parent = []
        for name, expected_parent in expected_parents.items():
            node = by_heading.get(name)
            actual_parent = norm(parsed[version][node.parent_index].heading) if node and node.parent_index is not None else None
            if actual_parent == "Document introduction":
                actual_parent = None
            if actual_parent == expected_parent:
                correct_parent += 1
            else:
                wrong_parent.append({"heading": name, "expected_parent": expected_parent, "actual_parent": actual_parent})
        maps[version] = {n.logical_key: n for n in section_nodes}
        report["versions"][version] = {
            "pdf_pages": 6 if version == "v1" else 7,
            "extracted_characters": len(texts[version]),
            "parsed_nodes_including_title_intro": len(parsed[version]),
            "expected_section_headings": len(expected_headings),
            "predicted_section_headings": len(predicted_headings),
            "heading_precision_recall_f1": heading,
            "parent_assignment_accuracy": correct_parent / len(expected_parents),
            "parent_assignments_correct": correct_parent,
            "parent_assignments_total": len(expected_parents),
            "parent_errors": wrong_parent,
        }

    v1, v2 = maps["v1"], maps["v2"]
    common_keys = set(v1) & set(v2)
    expected_common = set(gt["parents_v1"]) & set(gt["parents_v2"])
    predicted_common_headings = {norm(v1[k].heading) for k in common_keys}
    match_metrics = binary_metrics({norm(h) for h in expected_common}, predicted_common_headings)
    changed = {norm(v1[k].heading) for k in common_keys if v1[k].content_hash != v2[k].content_hash}
    added = {norm(n.heading) for k, n in v2.items() if k not in v1}
    removed = {norm(n.heading) for k, n in v1.items() if k not in v2}
    expected_changed = {norm(x) for x in gt["expected_modified_sections"]}
    expected_added = {norm(x) for x in gt["expected_added_sections"]}
    expected_removed = {norm(x) for x in gt["expected_removed_sections"]}
    report["version_matching"] = {
        "exact_logical_key_common_sections": len(common_keys),
        "expected_common_sections": len(expected_common),
        "precision_recall_f1_by_section_identity": match_metrics,
    }
    report["change_detection"] = {
        "expected_modified": sorted(expected_changed),
        "predicted_modified": sorted(changed),
        "modified_precision_recall_f1": binary_metrics(expected_changed, changed),
        "expected_added": sorted(expected_added),
        "predicted_added": sorted(added),
        "added_precision_recall_f1": binary_metrics(expected_added, added),
        "expected_removed": sorted(expected_removed),
        "predicted_removed": sorted(removed),
        "removed_precision_recall_f1": binary_metrics(expected_removed, removed),
        "section_level_staleness_proxy_recall": binary_metrics(expected_changed, changed)["recall"],
        "note": "Section-level hash-change proxy only; not an end-to-end evaluation of generated QA cases or their clinical relevance.",
    }
    table_checks = {}
    for version in ("v1", "v2"):
        by_heading = {norm(n.heading): n for n in parsed[version]}
        specs = by_heading[norm("2.1 General Specifications")].body_text
        errors = by_heading[norm("4.2 Error Codes")].body_text
        table_checks[version] = {
            "specification_table_markdown": "| Pressure range | 0–299 mmHg |" in specs,
            "error_table_markdown": "| E3 | Overpressure condition |" in errors,
            "contains_e6_row": "| E6 | Bluetooth sync failure |" in errors,
        }
    report["table_smoke_checks"] = table_checks
    report["not_measured"] = [
        "Full-document CER/WER: no manually transcribed complete reference text was prepared.",
        "LLM test-case quality: no LLM-generated cases were human-scored in this evaluation.",
        "API end-to-end behavior is covered by tests/test_api_workflow.py, not by this section-metric report.",
    ]
    out = ROOT / "evaluation" / "ct200_evaluation_report.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\\nSaved report: {out.relative_to(ROOT)}")
    return 0 if all(
        report["versions"][v]["heading_precision_recall_f1"]["f1"] == 1.0
        and report["versions"][v]["parent_assignment_accuracy"] == 1.0
        for v in ("v1", "v2")
    ) and report["change_detection"]["modified_precision_recall_f1"]["f1"] == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
