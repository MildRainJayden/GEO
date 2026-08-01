from __future__ import annotations

import asyncio
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from pydantic import ValidationError

from ..models import AuditRequest
from ..report.pdf import write_pdf_report
from ..services.audit_service import default_service


class AIVCRequestHandler(BaseHTTPRequestHandler):
    server_version = "AIVC/0.1"

    def do_OPTIONS(self) -> None:
        self._send_empty(204)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._send_static("frontend/static/index.html")
            return
        if path == "/openapi.json":
            self._send_json(_openapi())
            return
        if path == "/providers":
            self._send_json({"providers": default_service.registry.names})
            return
        parts = [part for part in path.split("/") if part]
        if len(parts) >= 2 and parts[0] == "audit":
            record = default_service.get_audit(parts[1])
            if not record:
                self._send_json({"error": "audit not found"}, 404)
                return
            if len(parts) == 2:
                self._send_json(record.model_dump(mode="json"))
                return
            if len(parts) == 3 and parts[2] == "result":
                if not record.result:
                    self._send_json({"error": "result not ready"}, 409)
                    return
                self._send_json(record.result.model_dump(mode="json"))
                return
            if len(parts) == 3 and parts[2] == "report":
                if not record.result or not record.result.report_html:
                    self._send_json({"error": "report not ready"}, 409)
                    return
                self._send_html(record.result.report_html)
                return
            if len(parts) == 3 and parts[2] == "report.pdf":
                if not record.result:
                    self._send_json({"error": "report not ready"}, 409)
                    return
                output_path = Path("outputs") / f"{record.id}-report.pdf"
                write_pdf_report(record.result, output_path)
                self._send_bytes(output_path.read_bytes(), "application/pdf")
                return
        self._send_json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            payload = self._read_json()
            if path == "/audit":
                request = AuditRequest(**payload)
                record = asyncio.run(default_service.create_audit(request))
                if record.status == "failed":
                    self._send_json(record.model_dump(mode="json"), 502)
                    return
                self._send_json(record.model_dump(mode="json"), 201)
                return
            if path == "/compare":
                request = AuditRequest(**payload)
                record = asyncio.run(default_service.create_audit(request))
                if record.status == "failed":
                    self._send_json(record.model_dump(mode="json"), 502)
                    return
                competitors = record.result.competitors if record.result else []
                self._send_json({"audit_id": record.id, "competitors": [c.model_dump() for c in competitors]})
                return
            if path == "/optimize":
                request = AuditRequest(**payload)
                record = asyncio.run(default_service.create_audit(request))
                if record.status == "failed":
                    self._send_json(record.model_dump(mode="json"), 502)
                    return
                result = record.result
                self._send_json(
                    {
                        "audit_id": record.id,
                        "score": result.score.model_dump() if result else None,
                        "geo_suggestions": [s.model_dump() for s in result.geo_suggestions] if result else [],
                    }
                )
                return
            if path == "/content/generate":
                request = AuditRequest(**payload)
                record = asyncio.run(default_service.create_audit(request))
                if record.status == "failed":
                    self._send_json(record.model_dump(mode="json"), 502)
                    return
                result = record.result
                self._send_json(
                    {
                        "audit_id": record.id,
                        "content": [s.model_dump() for s in result.geo_suggestions] if result else [],
                    }
                )
                return
        except ValidationError as exc:
            self._send_json({"error": "validation_error", "details": exc.errors()}, 422)
            return
        except json.JSONDecodeError:
            self._send_json({"error": "invalid json"}, 400)
            return
        self._send_json({"error": "not found"}, 404)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        return json.loads(raw)

    def _send_static(self, rel_path: str) -> None:
        root = Path(__file__).resolve().parents[3]
        file_path = root / rel_path
        self._send_bytes(file_path.read_bytes(), "text/html; charset=utf-8")

    def _send_html(self, html: str, status: int = 200) -> None:
        self._send_bytes(html.encode("utf-8"), "text/html; charset=utf-8", status)

    def _send_json(self, payload: object, status: int = 200) -> None:
        self._send_bytes(
            json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
            "application/json; charset=utf-8",
            status,
        )

    def _send_empty(self, status: int) -> None:
        self.send_response(status)
        self._headers("text/plain")
        self.end_headers()

    def _send_bytes(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self._headers(content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _headers(self, content_type: str) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), AIVCRequestHandler)
    print(f"AIVC server running at http://{host}:{port}")
    server.serve_forever()


def _openapi() -> dict:
    return {
        "openapi": "3.1.0",
        "info": {"title": "AI Visibility China API", "version": "0.1.0"},
        "paths": {
            "/audit": {"post": {"summary": "创建并执行 AI 可见度测评"}},
            "/audit/{id}": {"get": {"summary": "获取测评任务状态"}},
            "/audit/{id}/result": {"get": {"summary": "获取测评结果 JSON"}},
            "/audit/{id}/report": {"get": {"summary": "获取 HTML 报告"}},
            "/audit/{id}/report.pdf": {"get": {"summary": "下载 PDF 报告"}},
            "/compare": {"post": {"summary": "生成竞品矩阵"}},
            "/optimize": {"post": {"summary": "生成 GEO 优化建议"}},
            "/content/generate": {"post": {"summary": "生成可复制内容"}},
            "/providers": {"get": {"summary": "获取已注册 Provider 列表"}},
        },
    }
