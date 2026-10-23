"""Isolated end-to-end API smoke test using the real CT-200 PDFs."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_real_v1_to_v2_generation_is_flagged_stale(tmp_path):
    code = r'''
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
root = Path("data")
v1 = root / "ct200_manual_v1.pdf"
v2 = root / "ct200_manual_v2.pdf"
response = client.post("/api/ingest", files={"file": (v1.name, v1.read_bytes(), "application/pdf")})
assert response.status_code == 200, response.text
assert response.json()["version"] == 1

sections = client.get("/api/sections?version=1").json()["sections"]
def walk(nodes):
    for node in nodes:
        yield node
        yield from walk(node["children"])
all_nodes = list(walk(sections))
source = next(node for node in all_nodes if node["heading"].startswith("2.1.1.1 Battery Life"))
selection = client.post("/api/selections", json={"name": "Battery life regression", "node_ids": [source["id"]], "version": 1})
assert selection.status_code == 200, selection.text
generation = client.post("/api/generations", json={"selection_id": selection.json()["id"]})
assert generation.status_code == 200, generation.text
assert 3 <= len(generation.json()["test_cases"]) <= 5
# Duplicate submissions are idempotent unless force_new is explicitly requested.
repeat = client.post("/api/generations", json={"selection_id": selection.json()["id"]})
assert repeat.status_code == 200, repeat.text
assert repeat.json()["id"] == generation.json()["id"]
assert repeat.json()["deduplicated"] is True

response = client.post("/api/ingest", files={"file": (v2.name, v2.read_bytes(), "application/pdf")})
assert response.status_code == 200, response.text
assert response.json()["version"] == 2
retrieved = client.get(f"/api/generations?selection_id={selection.json()['id']}")
assert retrieved.status_code == 200, retrieved.text
record = retrieved.json()["generations"][0]
assert record["staleness"]["is_stale"] is True
assert record["staleness"]["nodes"][0]["status"] == "modified"
by_node = client.get(f"/api/generations?node_id={source['id']}")
assert by_node.status_code == 200, by_node.text
assert any(g["id"] == generation.json()["id"] for g in by_node.json()["generations"])
assert any(node["heading"].startswith("5.3 Data Export") for node in walk(client.get("/api/sections?version=2").json()["sections"]))
print("PASS: real v1 ingest -> version-pinned selection -> generation -> v2 ingest -> stale retrieval")
'''
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{(tmp_path / 'workflow.db').as_posix()}"
    env["GENERATIONS_JSON"] = str(tmp_path / "generations.json")
    env.pop("LLM_API_KEY", None)
    env.pop("LLM_BASE_URL", None)
    env.pop("LLM_MODEL", None)
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, env=env,
        text=True, capture_output=True, timeout=60,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "PASS: real v1 ingest" in result.stdout
