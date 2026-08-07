from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib import error, request


class ProductionApiIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.directory = tempfile.TemporaryDirectory()
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            cls.port = listener.getsockname()[1]
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        cls.reader_key = "reader-integration-secret-000001"
        cls.operator_key = "operator-integration-secret-001"
        cls.admin_key = "admin-integration-secret-000001"
        environment = os.environ.copy()
        environment.update(
            {
                "DOCOPS_ENVIRONMENT": "production",
                "DOCOPS_DATABASE_PATH": str(Path(cls.directory.name) / "integration.db"),
                "DOCOPS_API_KEYS": (
                    f"reader:reader:{cls.reader_key},"
                    f"operator:operator:{cls.operator_key},"
                    f"admin:admin:{cls.admin_key}"
                ),
                "DOCOPS_TRUSTED_HOSTS": "127.0.0.1,localhost",
                "DOCOPS_DOCS_ENABLED": "false",
                "DOCOPS_LLM_PROVIDER": "extractive",
                "DOCOPS_LOG_LEVEL": "WARNING",
            }
        )
        cls.process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "docops_agent.api:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(cls.port),
                "--no-access-log",
            ],
            cwd=Path(__file__).resolve().parents[1],
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
        )
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if cls.process.poll() is not None:
                raise RuntimeError("integration API exited during startup")
            try:
                status, _, _ = cls._request("GET", "/health/ready")
                if status == 200:
                    break
            except (error.URLError, ConnectionError):
                pass
            time.sleep(0.1)
        else:
            cls.process.terminate()
            raise RuntimeError("integration API did not become ready")

    @classmethod
    def tearDownClass(cls) -> None:
        if os.name == "nt":
            cls.process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            cls.process.terminate()
        try:
            cls.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            cls.process.kill()
            cls.process.wait(timeout=5)
        cls.directory.cleanup()

    @classmethod
    def _request(
        cls,
        method: str,
        path: str,
        *,
        api_key: str | None = None,
        payload: dict[str, object] | None = None,
    ) -> tuple[int, dict[str, object] | list[dict[str, object]], dict[str, str]]:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload else None
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["X-API-Key"] = api_key
        http_request = request.Request(
            f"{cls.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with request.urlopen(http_request, timeout=5) as response:
                body = json.loads(response.read())
                return response.status, body, dict(response.headers)
        except error.HTTPError as exc:
            body = json.loads(exc.read())
            return exc.code, body, dict(exc.headers)

    def test_auth_rbac_approval_and_audit_flow(self) -> None:
        status, ready, headers = self._request("GET", "/health/ready")
        self.assertEqual(status, 200)
        self.assertEqual(ready["status"], "ready")
        self.assertIn("x-request-id", {key.lower() for key in headers})

        status, _, _ = self._request("GET", "/me")
        self.assertEqual(status, 401)
        status, identity, _ = self._request("GET", "/me", api_key=self.reader_key)
        self.assertEqual(status, 200)
        self.assertEqual(identity, {"name": "reader", "role": "reader"})
        status, _, _ = self._request("GET", "/docs")
        self.assertEqual(status, 404)

        document = {
            "document_id": "integration-policy",
            "title": "集成测试制度",
            "text": "正式员工每年享有十五天带薪年假。",
        }
        status, _, _ = self._request(
            "POST",
            "/documents/text",
            api_key=self.reader_key,
            payload=document,
        )
        self.assertEqual(status, 403)
        status, created, _ = self._request(
            "POST",
            "/documents/text",
            api_key=self.admin_key,
            payload=document,
        )
        self.assertEqual(status, 200)
        self.assertEqual(created["document_id"], "integration-policy")

        status, answer, _ = self._request(
            "POST",
            "/query",
            api_key=self.reader_key,
            payload={"question": "正式员工有多少天年假？"},
        )
        self.assertEqual(status, 200)
        self.assertFalse(answer["abstained"])
        self.assertGreater(len(answer["citations"]), 0)

        status, pending, _ = self._request(
            "POST",
            "/agent/run",
            api_key=self.operator_key,
            payload={"message": "创建工单：集成测试电脑故障"},
        )
        self.assertEqual(status, 200)
        approval_id = pending["approval"]["id"]
        self.assertEqual(pending["approval"]["status"], "pending")

        status, approved, _ = self._request(
            "POST",
            f"/approvals/{approval_id}/approve",
            api_key=self.operator_key,
        )
        self.assertEqual(status, 200)
        self.assertEqual(approved["approval"]["status"], "approved")
        self.assertIsNotNone(approved["ticket"])

        status, _, _ = self._request(
            "POST",
            f"/approvals/{approval_id}/approve",
            api_key=self.operator_key,
        )
        self.assertEqual(status, 409)

        status, audit_events, _ = self._request(
            "GET",
            "/audit-events",
            api_key=self.admin_key,
        )
        self.assertEqual(status, 200)
        self.assertIn("approval.approved", {event["event_type"] for event in audit_events})


if __name__ == "__main__":
    unittest.main()
