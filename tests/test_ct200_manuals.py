import json
import unicodedata
from pathlib import Path

from app.parser import extract_pdf, parse_text

ROOT = Path(__file__).resolve().parents[1]
GT = json.loads((ROOT / "evaluation" / "ground_truth_ct200.json").read_text(encoding="utf-8"))


def norm(value):
    return " ".join(unicodedata.normalize("NFKC", value).split()).strip()


def parsed_version(version):
    path = ROOT / GT["source_files"][version]
    text, method = extract_pdf(path)
    nodes = parse_text(text)
    sections = [n for n in nodes if norm(n.heading) != "Document introduction"]
    return text, method, nodes, sections


def test_actual_manual_heading_inventory_matches_ground_truth():
    for version in ("v1", "v2"):
        _, _, _, sections = parsed_version(version)
        actual = {norm(n.heading) for n in sections}
        expected = {norm(h) for h in GT[f"parents_{version}"]}
        assert actual == expected


def test_actual_manual_parent_child_hierarchy_matches_ground_truth():
    for version in ("v1", "v2"):
        _, _, nodes, sections = parsed_version(version)
        by_heading = {norm(n.heading): n for n in sections}
        expected = {norm(k): (norm(v) if v else None) for k, v in GT[f"parents_{version}"].items()}
        for heading, expected_parent in expected.items():
            node = by_heading[heading]
            actual_parent = norm(nodes[node.parent_index].heading) if node.parent_index is not None else None
            if actual_parent == "Document introduction":
                actual_parent = None
            assert actual_parent == expected_parent, (version, heading, expected_parent, actual_parent)


def test_pdf_tables_are_preserved_as_markdown_and_e6_only_in_v2():
    outputs = {}
    for version in ("v1", "v2"):
        _, method, _, sections = parsed_version(version)
        assert "table extraction" in method
        by_heading = {norm(n.heading): n for n in sections}
        assert "| Pressure range | 0–299 mmHg |" in by_heading[norm("2.1 General Specifications")].body_text
        errors = by_heading[norm("4.2 Error Codes")].body_text
        assert "| E3 | Overpressure condition |" in errors
        outputs[version] = errors
    assert "| E6 | Bluetooth sync failure |" not in outputs["v1"]
    assert "| E6 | Bluetooth sync failure |" in outputs["v2"]


def test_actual_version_change_inventory_and_hash_detection():
    _, _, _, v1_nodes = parsed_version("v1")
    _, _, _, v2_nodes = parsed_version("v2")
    v1 = {n.logical_key: n for n in v1_nodes}
    v2 = {n.logical_key: n for n in v2_nodes}
    changed = {norm(v1[k].heading) for k in v1.keys() & v2.keys() if v1[k].content_hash != v2[k].content_hash}
    added = {norm(v2[k].heading) for k in v2.keys() - v1.keys()}
    removed = {norm(v1[k].heading) for k in v1.keys() - v2.keys()}
    assert changed == {norm(x) for x in GT["expected_modified_sections"]}
    assert added == {norm(x) for x in GT["expected_added_sections"]}
    assert removed == {norm(x) for x in GT["expected_removed_sections"]}
