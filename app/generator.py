"""Source-grounded QA test generation with a deterministic local fallback.

The local generator deliberately prefers narrow, traceable tests over generic
cases that invent thresholds or expected device behavior. LLM generation is
optional; returned cases are schema-validated and checked for unsupported
numeric values before they are accepted.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import httpx
from pydantic import ValidationError

from .schemas import TestCase

DATA_PATH = Path(os.getenv("GENERATIONS_JSON", "./data/generations.json"))


def _refs(citations: list[dict[str, Any]]) -> list[str]:
    return [f"Node {x['node_id']} — {x['heading']} (v{x.get('version', '?')})" for x in citations]


def _joined(citations: list[dict[str, Any]]) -> str:
    return "\n".join(f"{c.get('heading', '')}\n{c.get('text', '')}" for c in citations).strip()


def _case(title: str, objective: str, preconditions: list[str], steps: list[str], expected: str,
          priority: str, refs: list[str]) -> dict[str, Any]:
    return TestCase(
        title=title, objective=objective, preconditions=preconditions, steps=steps,
        expected_result=expected, priority=priority, requirement_refs=refs,
    ).model_dump()


def _fallback(citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build three distinct test ideas from the selected excerpt without guessing values."""
    refs = _refs(citations)
    text = _joined(citations)
    lower = text.casefold()
    heading = " ".join(c.get("heading", "") for c in citations)
    common = [
        "Use the cited manual version and follow the approved test procedure.",
        "Use calibrated equipment and applicable safety controls where relevant.",
    ]

    # Battery behavior: use only the threshold and estimate explicitly in the source.
    if "battery life" in lower or "low-battery" in lower or "low battery" in lower:
        threshold = re.search(r"(?:below|falls below)\s+(\d+(?:\.\d+)?\s*%)", text, re.I)
        threshold_text = threshold.group(1).replace(" ", "") if threshold else None
        cycles = re.search(r"approximately\s+(\d+)\s+measurement cycles", text, re.I)
        cycle_text = cycles.group(1) if cycles else None
        cases = []
        if threshold_text:
            cases.append(_case(
                "Verify low-battery alert threshold",
                "Confirm the alert behavior at the explicitly documented remaining-capacity threshold.",
                common + ["Prepare a device with a measurable remaining-capacity indication."],
                [f"Reduce remaining capacity under a controlled procedure to below {threshold_text}.",
                 "Observe and record the displayed low-battery indication.",
                 "Repeat above the threshold if the approved procedure supports this comparison."],
                f"The low-battery icon appears when remaining capacity falls below {threshold_text}, as stated in the selected source.",
                "High", refs))
        if cycle_text:
            cases.append(_case(
                "Verify documented battery-use estimate",
                "Check the battery-life estimate under the usage pattern described by the manual.",
                common + ["Use the battery type and measurement frequency specified in the source."],
                ["Run the approved usage profile (three measurements per day, if applicable to this source).",
                 "Record the observed measurement count and replacement point.",
                 "Compare the observation with the source estimate, accounting for the stated approximate nature of the value."],
                f"The source estimates approximately {cycle_text} measurement cycles before battery replacement; record deviations for review rather than treating the estimate as an exact pass/fail limit.",
                "High", refs))
        cases.append(_case(
            "Review battery requirement and acceptance criteria",
            "Ensure the battery-related requirement can be tested without assuming undocumented behavior.",
            ["The selected source section is available for review."],
            ["Confirm the battery type, usage profile, alert threshold, and stated estimate in the source.",
             "Record any missing measurement method or acceptance criterion for the document owner.",
             "Approve a pass/fail procedure only after the missing criteria are resolved."],
            "Any missing criteria are documented for review; no additional battery threshold or exact lifetime is assumed.",
            "Medium", refs))
        return cases[:3]

    # Error-code tables can contain several independently testable behaviors.
    if "error codes" in lower or re.search(r"\|\s*E[1-9]\s*\|", text):
        cases = []
        e3 = re.search(r"\|\s*E3\s*\|[^\n]*", text, re.I)
        if e3:
            e3_row = re.sub(r"\s*\|\s*", " — ", e3.group(0)).strip(" —")
            timing = re.search(r"(?:within|in)\s+(\d+(?:\.\d+)?)\s*seconds?", e3.group(0), re.I)
            time_phrase = f"within {timing.group(1)} seconds" if timing else "within the time stated in the source"
            cases.append(_case(
                "Verify E3 overpressure response",
                "Check the E3 response and automatic deflation described by the selected error-code entry.",
                common + ["Perform only the approved overpressure test procedure; do not exceed approved safety limits."],
                ["Trigger the documented E3 condition using the approved test fixture and procedure.",
                 f"Measure the deflation response against the source's stated timing ({time_phrase}).",
                 "Record the displayed error code and observed device response."],
                f"The observed response matches the selected source entry: {e3_row}. If other prose specifies a different timing, flag the conflict for human review.",
                "High", refs))
        e6 = re.search(r"\|\s*E6\s*\|[^\n]*", text, re.I)
        if e6:
            e6_row = re.sub(r"\s*\|\s*", " — ", e6.group(0)).strip(" —")
            cases.append(_case(
                "Verify Bluetooth sync failure handling",
                "Confirm the documented E6 indication and whether measurement behavior is affected.",
                common + ["Use a test setup that can safely reproduce a Bluetooth synchronization failure."],
                ["Cause a synchronization failure using the approved test setup.",
                 "Observe the displayed error indication and the behavior on the next sync attempt.",
                 "Verify whether measurement behavior is affected and record the result."],
                f"The observed behavior matches the selected source entry: {e6_row}.",
                "High", refs))
        cases.append(_case(
            "Review error-code acceptance criteria",
            "Check that each selected error-code behavior has a clear, source-supported pass/fail criterion.",
            ["The selected error-code table and related prose are available for review."],
            ["Compare each tested code's meaning with its documented device behavior.",
             "Check related prose for conflicting timing or response statements.",
             "Record conflicts or missing recovery criteria for human resolution before execution."],
            "The test procedure uses source-supported criteria, and any conflicting or missing requirements are flagged rather than silently reconciled.",
            "Medium", refs))
        return cases[:3]

    # Data export and Bluetooth sync are separate requirements and should not be conflated.
    if "data export" in lower or "csv file" in lower or "exporting stored readings" in lower:
        csv_fields = ["timestamp", "profile", "systolic", "diastolic", "pulse", "classification"]
        mentioned = [field for field in csv_fields if re.search(rf"\b{field}\b", lower)]
        field_list = ", ".join(mentioned) if mentioned else "the CSV fields explicitly listed by the source"
        cases = [
            _case("Verify CSV export content", "Confirm that exported readings contain the fields documented by the manual.",
                  common + ["Use a device and companion-app setup with stored readings."],
                  ["Prepare stored readings using the approved test procedure.", "Export the readings as a CSV file.",
                   f"Inspect the exported columns and verify the documented fields: {field_list}.",
                   "Record missing, unexpected, or incorrectly labeled columns."],
                  f"The CSV contains the fields explicitly listed by the selected source ({field_list}); no additional field requirements are assumed.", "High", refs),
            _case("Verify export prerequisite after Bluetooth sync", "Check the documented prerequisite for exporting stored readings.",
                  common + ["Use a test session where Bluetooth synchronization can be observed."],
                  ["Complete at least one successful Bluetooth sync in the current session.",
                   "Attempt to export stored readings.", "Record whether export is available and whether the file meets the documented format."],
                  "Export is tested only after the documented successful-sync prerequisite has been met; any behavior before that prerequisite is not assumed unless separately specified.", "High", refs),
            _case("Review export requirement completeness", "Ensure export requirements define the fields and preconditions needed for an objective pass/fail decision.",
                  ["The selected export section is available for review."],
                  ["Verify the documented firmware condition, file format, required columns, and sync prerequisite.",
                   "Record any unspecified encoding, delimiter, filename, or error behavior as open questions rather than requirements.",
                   "Obtain approval for any additional acceptance criteria before execution."],
                  "All pass/fail criteria are traceable to the manual or explicitly approved by the document owner.", "Medium", refs),
        ]
        return cases

    if "cuff inflation" in lower or "inflation" in lower:
        increment = re.search(r"(\d+)\s*mmhg", text, re.I)
        increment_text = f"{increment.group(1)} mmHg" if increment else None
        step = (f"Record each documented inflation increment and compare it with {increment_text}." if increment_text
                else "Record the observed inflation sequence and compare it with the exact sequence stated in the source.")
        return [
            _case("Verify cuff inflation sequence", "Confirm the inflation sequence against the selected manual section.", common,
                  ["Set up the cuff and approved pressure measurement equipment.", "Start the documented measurement sequence.", step,
                   "Record the sequence and any deviation."],
                  "The observed sequence matches the selected source. Do not infer a missing increment or upper limit.", "High", refs),
            _case("Verify inflation sequence termination", "Check that the sequence ends or transitions as described by the source.", common,
                  ["Run the approved inflation procedure.", "Observe the documented transition or termination condition.",
                   "Record the pressure trace and device indication."],
                  "The transition matches the explicit source statement; if the termination condition is not specified, mark it for review.", "High", refs),
            _case("Review inflation acceptance criteria", "Identify missing details that prevent objective execution of the inflation test.",
                  ["The selected source section is available for review."],
                  ["Identify the documented sequence, increment, and stopping condition.", "List any missing tolerance or timing criteria.",
                   "Have the document owner approve missing criteria before pass/fail execution."],
                  "No undocumented pressure, tolerance, or timing requirement is assumed.", "Medium", refs),
        ]

    # Safe generic fallback for requirements that do not match a known pattern.
    excerpt = re.sub(r"\s+", " ", text).strip()
    excerpt = excerpt[:500] if excerpt else "The selected source section has no readable body text."
    return [
        _case("Verify documented requirement behavior", "Check the behavior explicitly described in the selected source.", common,
              ["Read the selected section and identify its stated condition and action.",
               "Execute the condition using the approved procedure.", "Record the observable output and compare it with the source."],
              f"Observed behavior conforms to the explicit source statement: {excerpt}", "High", refs),
        _case("Verify documented alternate or error path", "Check an alternate path only if it is explicitly described in the selected section.", common,
              ["Identify any alternate condition or error path explicitly stated in the selected source.",
               "Execute that path if one is documented and approved.", "Record the response; if no alternate path is specified, record that limitation."],
              "Only source-documented behavior is evaluated; missing alternate-path requirements are flagged for review.", "Medium", refs),
        _case("Review source completeness before execution", "Ensure the requirement contains enough information to execute and judge a test.",
              ["The selected source section is available for review."],
              ["Check for an explicit condition, action, and expected outcome.",
               "Record missing acceptance criteria for the document owner.", "Confirm each pass/fail criterion is supported by the manual."],
              "Missing criteria are documented and reviewed before pass/fail execution; no undocumented threshold or behavior is assumed.",
              "Medium", refs),
    ]


def _validate_numeric_grounding(cases: list[dict[str, Any]], citations: list[dict[str, Any]]) -> bool:
    """Reject LLM output that introduces numeric values absent from selected source text."""
    source = _joined(citations)
    source_numbers = set(re.findall(r"\d+(?:\.\d+)?", source))
    generated = json.dumps(cases, ensure_ascii=False)
    generated_numbers = set(re.findall(r"\d+(?:\.\d+)?", generated))
    # Numbers in node IDs/version references are not test requirements, but are included
    # in both the refs and source metadata; conservatively reject only novel numerals.
    return generated_numbers.issubset(source_numbers | {str(c.get("node_id")) for c in citations} | {str(c.get("version")) for c in citations})


async def generate_cases(citations: list[dict]) -> tuple[list[dict], str]:
    base = os.getenv("LLM_BASE_URL", "").strip()
    key = os.getenv("LLM_API_KEY", "").strip()
    model = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
    if base and key:
        user_prompt = {
            "role": "user",
            "content": (
                "Create exactly 3 QA test-case ideas grounded ONLY in these selected manual excerpts. "
                "Return JSON only with key test_cases and fields title, objective, preconditions, steps, "
                "expected_result, priority (Low/Medium/High/Critical), requirement_refs. "
                "Do not invent thresholds, units, limits, or expected behavior. If a criterion is missing, "
                "make the case a review task and state the gap. Use distinct test purposes, not paraphrases. Excerpts: "
                + json.dumps(citations, ensure_ascii=False)
            ),
        }
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                response = await client.post(
                    base.rstrip("/") + "/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json={"model": model, "messages": [
                        {"role": "system", "content": "You are a careful QA assistant. Never invent requirements. Output valid JSON only."},
                        user_prompt,
                    ], "temperature": 0.1},
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            raw_cases = parsed.get("test_cases") if isinstance(parsed, dict) else None
            if not isinstance(raw_cases, list) or len(raw_cases) != 3:
                raise ValueError("Expected exactly three distinct test cases")
            validated = [TestCase.model_validate(case).model_dump() for case in raw_cases]
            titles = [case["title"].casefold().strip() for case in validated]
            if len(set(titles)) != len(titles) or not _validate_numeric_grounding(validated, citations):
                raise ValueError("Duplicate titles or unsupported numeric values")
            # Ensure every case includes at least one exact source reference.
            if any(not case["requirement_refs"] for case in validated):
                raise ValueError("Missing requirement reference")
            return validated, model
        except (Exception, ValidationError):
            # The deterministic fallback is safer than returning unverified LLM output.
            pass
    return [TestCase.model_validate(c).model_dump() for c in _fallback(citations)], "source-grounded-local"


def load_store() -> list[dict]:
    if not DATA_PATH.exists():
        return []
    try:
        value = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def save_store(records: list[dict]) -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
