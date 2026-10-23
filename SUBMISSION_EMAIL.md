# Submission email draft

**Subject:** Tri9T AI Engineering Internship Assignment — TraceQA

Dear Tri9T AI Team,

Please find my submission for the AI Engineering Internship assignment. I built TraceQA, a FastAPI-based document ingestion and traceability prototype for the CT-200 manuals. It supports structured section extraction, versioned ingestion, version-pinned selections, QA test-case generation, and retrieval-time stale-traceability checks.

- **Live demo:** https://traceqa.onrender.com/
- **GitHub repository:** https://github.com/sivanagalokesh/Traceqa
- **Approach document:** https://github.com/sivanagalokesh/Traceqa/blob/main/APPROACH.md
- **Validation:** `python -m pytest -q` and `python -m evaluation.evaluate_ct200`

The included evaluation reports perfect section-heading and parent-assignment scores on the manually labeled CT-200 v1/v2 pair, and detects the expected four modified sections and the added `5.3 Data Export` section. I have documented the evaluation scope and limitations, including that full-document CER/WER and human-scored QA quality have not been measured. I also flagged the unresolved v2 discrepancy between the Section 4.1 overpressure prose (2 seconds) and the E3 error table (1.5 seconds) for human review.

Thank you for your time and consideration. I would be happy to walk through the design decisions and limitations.

Best regards,  
Siva Naga Lokesh Bajathri
