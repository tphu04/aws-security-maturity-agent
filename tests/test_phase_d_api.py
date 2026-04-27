"""Phase D — Scanner API hardening (POST + /v1/, SQLite jobs, CORS).

Tests intentionally avoid running prowler. The worker is monkey-patched out;
we only verify HTTP semantics, payload validation, persistence, and CORS.
"""

from __future__ import annotations

import importlib
import json
import os
import sys

import pytest


@pytest.fixture
def api(monkeypatch, tmp_path):
    """Reload api_server with isolated SQLite DB and a no-op worker."""
    db_path = tmp_path / "jobs.db"
    monkeypatch.chdir(tmp_path)
    # Force fresh import so module-level _init_job_db runs against tmp_path.
    sys.modules.pop("pdca.api_server", None)
    api_server = importlib.import_module("pdca.api_server")
    monkeypatch.setattr(api_server, "JOB_DB_PATH", str(db_path), raising=True)
    api_server._init_job_db()

    # Replace BackgroundTasks worker with a no-op so endpoints return synchronously.
    monkeypatch.setattr(api_server, "_run_prowler_command_worker", lambda jid: None)

    from fastapi.testclient import TestClient

    return api_server, TestClient(api_server.app)


# ---------------------------------------------------------------------------
# D2 — POST + /v1/ semantics
# ---------------------------------------------------------------------------


def test_post_scan_group_returns_job_id(api):
    _, client = api
    r = client.post("/v1/scan/group", json={"group": "s3"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "pending"
    assert body["job_id"].startswith("job_")


def test_post_scan_group_rejects_unknown_group(api):
    _, client = api
    r = client.post("/v1/scan/group", json={"group": "not_a_real_service"})
    assert r.status_code == 400


def test_post_scan_group_validates_payload(api):
    _, client = api
    r = client.post("/v1/scan/group", json={})
    assert r.status_code == 422  # pydantic validation


def test_post_scan_checks_returns_job_id(api):
    _, client = api
    r = client.post(
        "/v1/scan/checks",
        json={"check_ids": "s3_block_account_public_access,iam_root_mfa_enabled"},
    )
    assert r.status_code == 200
    assert r.json()["job_id"].startswith("job_")


def test_post_scan_checks_rejects_empty(api):
    _, client = api
    r = client.post("/v1/scan/checks", json={"check_ids": "  "})
    # Empty / whitespace-only fails pydantic validator (422).
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Argument-injection defence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {"check_ids": "s3_check --services iam"},   # flag injection
        {"check_ids": "s3_check;rm -rf /"},          # shell metachar
        {"check_ids": "-rf"},                        # leading dash
        {"check_ids": "S3_Check"},                   # uppercase rejected (Prowler IDs are lowercase)
        {"check_ids": "s3_check|cat"},               # pipe
        {"check_ids": "s3.check"},                   # dot
        {"check_ids": "s3_check`whoami`"},           # backtick
    ],
)
def test_post_scan_checks_rejects_injection(api, payload):
    _, client = api
    r = client.post("/v1/scan/checks", json=payload)
    assert r.status_code == 422, payload


@pytest.mark.parametrize(
    "payload",
    [
        {"group": "s3 --services iam"},
        {"group": "-s3"},
        {"group": "s3;ls"},
        {"group": "S3"},
    ],
)
def test_post_scan_group_rejects_injection(api, payload):
    _, client = api
    r = client.post("/v1/scan/group", json=payload)
    # Token validator (422) catches most; ALLOWED_GROUPS (400) catches valid token but unknown group.
    assert r.status_code in (400, 422), payload


def test_scan_checks_canonical_form_in_db(api):
    """Validator must split + re-emit comma-separated tokens, no spaces."""
    api_server, client = api
    r = client.post(
        "/v1/scan/checks",
        json={"check_ids": "  s3_check ,iam_check ,  kms_check "},
    )
    assert r.status_code == 200
    job = api_server._get_job(r.json()["job_id"])
    assert job["task_value"] == "s3_check,iam_check,kms_check"


def test_worker_builds_argv_list_no_shell(monkeypatch, tmp_path):
    """Worker must call subprocess.run with argv list and shell=False."""
    monkeypatch.chdir(tmp_path)
    sys.modules.pop("pdca.api_server", None)
    api_server = importlib.import_module("pdca.api_server")
    monkeypatch.setattr(api_server, "JOB_DB_PATH", str(tmp_path / "j.db"), raising=True)
    api_server._init_job_db()

    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        raise RuntimeError("stop")

    monkeypatch.setattr(api_server.subprocess, "run", fake_run)
    api_server._insert_job(
        "job_t",
        task_type="custom_file",
        task_value="s3_check,iam_check",
        command_details="x",
    )
    api_server._run_prowler_command_worker("job_t")

    assert isinstance(captured["argv"], list)
    assert captured["kwargs"].get("shell") is False
    # --check is followed by separate argv tokens, not one space-joined string.
    idx = captured["argv"].index("--check")
    assert captured["argv"][idx + 1] == "s3_check"
    assert captured["argv"][idx + 2] == "iam_check"
    # No injected flags.
    assert "--services" not in captured["argv"]


def test_worker_rejects_tampered_db_value(monkeypatch, tmp_path):
    """If task_value is tampered to contain a flag, worker must fail-closed."""
    monkeypatch.chdir(tmp_path)
    sys.modules.pop("pdca.api_server", None)
    api_server = importlib.import_module("pdca.api_server")
    monkeypatch.setattr(api_server, "JOB_DB_PATH", str(tmp_path / "j.db"), raising=True)
    api_server._init_job_db()

    called = []
    monkeypatch.setattr(
        api_server.subprocess, "run", lambda *a, **kw: called.append(a) or (_ for _ in ()).throw(AssertionError("must not run"))
    )

    # Insert tampered row directly bypassing API validation.
    api_server._insert_job(
        "job_evil",
        task_type="custom_file",
        task_value="s3_check --services iam",  # would-be injection
        command_details="x",
    )
    api_server._run_prowler_command_worker("job_evil")

    job = api_server._get_job("job_evil")
    assert job["status"] == "failed"
    assert "invalid task_value" in (job["error"] or {}).get("error", "")
    assert called == []  # subprocess never invoked


def test_scan_custom_validates_each_check_id(api, tmp_path, monkeypatch):
    """Custom file with malicious check_id must be rejected."""
    api_server, client = api
    checks_dir = tmp_path / "custom_checks"
    checks_dir.mkdir()
    monkeypatch.setattr(api_server, "CHECKS_DIR", str(checks_dir), raising=True)

    bad = checks_dir / "bad.json"
    bad.write_text(json.dumps(["s3_check", "--services iam"]), encoding="utf-8")

    r = client.post("/v1/scan/custom", json={"filename": "bad.json"})
    assert r.status_code == 400
    assert "check_id" in r.json()["detail"].lower()


def test_scan_custom_accepts_valid_check_list(api, tmp_path, monkeypatch):
    api_server, client = api
    checks_dir = tmp_path / "custom_checks"
    checks_dir.mkdir()
    monkeypatch.setattr(api_server, "CHECKS_DIR", str(checks_dir), raising=True)

    good = checks_dir / "good.json"
    good.write_text(json.dumps(["s3_check", "iam_check"]), encoding="utf-8")

    r = client.post("/v1/scan/custom", json={"filename": "good.json"})
    assert r.status_code == 200
    job = api_server._get_job(r.json()["job_id"])
    assert job["task_value"] == "s3_check,iam_check"




def test_post_scan_custom_rejects_path_traversal(api):
    _, client = api
    r = client.post("/v1/scan/custom", json={"filename": "../etc/passwd"})
    assert r.status_code in (400, 422)


def test_legacy_get_endpoints_are_gone(api):
    _, client = api
    r = client.get("/scan/check", params={"group": "s3"})
    assert r.status_code in (404, 405)


# ---------------------------------------------------------------------------
# D3 — SQLite persistence
# ---------------------------------------------------------------------------


def test_job_persists_after_module_reload(api, monkeypatch, tmp_path):
    api_server, client = api
    db_path = api_server.JOB_DB_PATH

    r = client.post("/v1/scan/group", json={"group": "s3"})
    job_id = r.json()["job_id"]

    # Simulate restart: drop module, re-import. DB file remains.
    sys.modules.pop("pdca.api_server", None)
    api_server2 = importlib.import_module("pdca.api_server")
    monkeypatch.setattr(api_server2, "JOB_DB_PATH", db_path, raising=True)

    job = api_server2._get_job(job_id)
    assert job is not None
    assert job["job_id"] == job_id
    assert job["status"] == "pending"
    assert job["task_type"] == "group"
    assert job["task_value"] == "s3"


def test_get_job_returns_404_for_unknown(api):
    _, client = api
    r = client.get("/v1/job/job_nonexistent")
    assert r.status_code == 404


def test_get_job_returns_persisted_record(api):
    _, client = api
    job_id = client.post("/v1/scan/group", json={"group": "iam"}).json()["job_id"]
    r = client.get(f"/v1/job/{job_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["job_id"] == job_id
    assert body["status"] == "pending"
    assert body["task_value"] == "iam"


def test_list_jobs_supports_pagination(api):
    _, client = api
    ids = []
    for g in ("s3", "iam", "ec2", "rds", "kms"):
        ids.append(client.post("/v1/scan/group", json={"group": g}).json()["job_id"])

    r = client.get("/v1/jobs", params={"limit": 2, "offset": 0})
    assert r.status_code == 200
    body = r.json()
    assert body["limit"] == 2 and body["offset"] == 0
    assert len(body["items"]) == 2

    r2 = client.get("/v1/jobs", params={"limit": 2, "offset": 2})
    assert len(r2.json()["items"]) == 2

    # Newest-first ordering.
    first_ids = [item["job_id"] for item in body["items"]]
    assert first_ids[0] in ids


def test_list_jobs_validates_limit(api):
    _, client = api
    assert client.get("/v1/jobs", params={"limit": 0}).status_code == 400
    assert client.get("/v1/jobs", params={"offset": -1}).status_code == 400


# ---------------------------------------------------------------------------
# D4 — CORS
# ---------------------------------------------------------------------------


def test_cors_header_present_on_response(api):
    _, client = api
    r = client.get(
        "/v1/jobs",
        headers={"Origin": "http://localhost:3000"},
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") in ("*", "http://localhost:3000")


def test_cors_preflight(api):
    _, client = api
    r = client.options(
        "/v1/scan/group",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert r.status_code in (200, 204)
    assert "access-control-allow-origin" in {k.lower() for k in r.headers.keys()}


def test_cors_wildcard_does_not_allow_credentials(api):
    """Spec invariant — wildcard origin must not pair with credentials=true."""
    _, client = api
    r = client.get("/v1/jobs", headers={"Origin": "http://localhost:3000"})
    # Either no header OR header is not "true".
    assert r.headers.get("access-control-allow-credentials", "false") != "true"


# ---------------------------------------------------------------------------
# D2.2 — AWS profile from settings
# ---------------------------------------------------------------------------


def test_worker_uses_settings_profile(monkeypatch, tmp_path):
    """Worker reads aws_profile / aws_default_region from settings, not hardcoded."""
    monkeypatch.chdir(tmp_path)
    sys.modules.pop("pdca.api_server", None)
    api_server = importlib.import_module("pdca.api_server")
    monkeypatch.setattr(
        api_server, "JOB_DB_PATH", str(tmp_path / "j.db"), raising=True
    )
    api_server._init_job_db()

    from pdca.config import settings as _s

    monkeypatch.setattr(_s, "aws_profile", "test-profile", raising=False)
    monkeypatch.setattr(_s, "aws_default_region", "eu-west-1", raising=False)

    captured = {}

    def fake_run(args, **kwargs):
        captured["cmd"] = " ".join(args) if isinstance(args, list) else args
        raise RuntimeError("stop early — we only inspect command")

    monkeypatch.setattr(api_server.subprocess, "run", fake_run)

    api_server._insert_job(
        "job_test", task_type="group", task_value="s3", command_details="x"
    )
    api_server._run_prowler_command_worker("job_test")

    assert "--profile test-profile" in captured["cmd"]
    assert "--region eu-west-1" in captured["cmd"]


# ---------------------------------------------------------------------------
# D1 — tools/scanner.py uses settings + new endpoints
# ---------------------------------------------------------------------------


def test_scanner_tools_call_v1_endpoints(monkeypatch):
    from pdca.tools import scanner as scanner_tools

    captured = {}

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"job_id": "job_x", "status": "pending"}

    def fake_post(url, json=None, timeout=None):
        captured["post_url"] = url
        captured["post_json"] = json
        return FakeResp()

    def fake_get(url, timeout=None):
        captured["get_url"] = url
        return FakeResp()

    monkeypatch.setattr(scanner_tools.requests, "post", fake_post)
    monkeypatch.setattr(scanner_tools.requests, "get", fake_get)

    scanner_tools.start_scan_by_group.invoke({"group": "s3"})
    assert captured["post_url"].endswith("/v1/scan/group")
    assert captured["post_json"] == {"group": "s3"}

    scanner_tools.start_scan_by_check_ids.invoke({"check_ids": "c1,c2"})
    assert captured["post_url"].endswith("/v1/scan/checks")
    assert captured["post_json"] == {"check_ids": "c1,c2"}

    scanner_tools.check_job_status.invoke({"job_id": "job_abc"})
    assert captured["get_url"].endswith("/v1/job/job_abc")


def test_no_hardcoded_api_server_url():
    """Tools must not contain the legacy hardcoded URL constant."""
    import pathlib

    root = pathlib.Path(__file__).parent.parent / "pdca" / "tools"
    for py in root.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        assert "API_SERVER_URL" not in text, f"{py}: legacy constant present"
        assert "127.0.0.1:8000" not in text, f"{py}: hardcoded URL present"
