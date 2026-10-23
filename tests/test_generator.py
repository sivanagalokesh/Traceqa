from app.generator import _fallback, _validate_numeric_grounding


def test_battery_cases_use_selected_threshold_and_estimate_without_duplicate_titles():
    citations = [{
        "node_id": 7, "version": 1, "heading": "2.1.1.1 Battery Life Under Typical Use",
        "text": "Four AA alkaline batteries provide approximately 300 measurement cycles. The device displays a low-battery icon once remaining capacity falls below 15%.",
        "content_hash": "abc",
    }]
    cases = _fallback(citations)
    assert len(cases) == 3
    assert len({c["title"] for c in cases}) == 3
    combined = " ".join(c["expected_result"] for c in cases)
    assert "15%" in combined
    assert "300" in combined
    assert all(c["requirement_refs"] and "v1" in c["requirement_refs"][0] for c in cases)


def test_error_code_cases_cover_e3_timing_and_e6_sync_behavior():
    citations = [{
        "node_id": 44, "version": 2, "heading": "4.2 Error Codes",
        "text": "| Code | Meaning | Device Behavior |\n| --- | --- | --- |\n| E3 | Overpressure condition | Auto-deflates within 1.5 seconds, displays E3 |\n| E6 | Bluetooth sync failure | Displays E6 on next sync attempt; does not affect measurement |",
        "content_hash": "def",
    }]
    cases = _fallback(citations)
    combined = " ".join(c["title"] + " " + c["expected_result"] for c in cases)
    assert len(cases) == 3
    assert "E3" in combined and "1.5 seconds" in combined
    assert "E6" in combined and "Bluetooth" in combined
    assert all(c["requirement_refs"] for c in cases)


def test_export_cases_check_csv_fields_and_successful_sync_prerequisite():
    citations = [{
        "node_id": 49, "version": 2, "heading": "5.3 Data Export",
        "text": "The companion app supports exporting stored readings as a CSV file containing timestamp, profile, systolic, diastolic, pulse, and classification columns. Export requires at least one successful Bluetooth sync in the current session.",
        "content_hash": "ghi",
    }]
    cases = _fallback(citations)
    combined = " ".join(str(c) for c in cases).lower()
    assert len(cases) == 3
    assert "timestamp" in combined and "classification" in combined
    assert "successful bluetooth sync" in combined
    assert len({c["title"] for c in cases}) == 3


def test_numeric_grounding_rejects_new_thresholds():
    citations = [{"node_id": 1, "version": 1, "heading": "Battery", "text": "Alert below 15%.", "content_hash": "x"}]
    assert _validate_numeric_grounding([{"title": "Alert below 15%", "steps": ["Check 15%"]}], citations)
    assert not _validate_numeric_grounding([{"title": "Alert below 20%", "steps": ["Check 20%"]}], citations)
