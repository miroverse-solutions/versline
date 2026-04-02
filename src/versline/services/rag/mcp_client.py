from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx

from versline.services.rag.runtime import scoped_proxy


@dataclass
class MCPClientConfig:
    transport: str
    tool_name: str
    timeout_seconds: int
    max_context_chars: int
    server_url: Optional[str] = None
    server_command: Optional[str] = None
    server_args: Optional[str] = None
    proxy: Optional[str] = None


class MCPContextClient:
    def __init__(self, config: MCPClientConfig):
        self.config = config

    def fetch_context(self, query: str, top_k: int = 5, metadata: Optional[Dict[str, Any]] = None) -> str:
        payload = {
            "query": query,
            "top_k": top_k,
            "metadata": metadata or {},
        }

        transport = (self.config.transport or "http").lower()
        if transport == "stdio":
            context = self._fetch_stdio(payload)
        else:
            context = self._fetch_http(payload)

        return context[: self.config.max_context_chars]

    def _fetch_http(self, payload: Dict[str, Any]) -> str:
        if not self.config.server_url:
            return ""

        client = httpx.Client(proxy=self.config.proxy) if self.config.proxy else httpx.Client()
        with scoped_proxy(self.config.proxy):
            response = client.post(self.config.server_url, json=payload, timeout=self.config.timeout_seconds)
        response.raise_for_status()
        data = response.json()

        if isinstance(data, dict):
            for key in ("context", "result", "text", "output"):
                value = data.get(key)
                if isinstance(value, str):
                    return value
                if isinstance(value, dict):
                    nested = value.get("text") or value.get("content")
                    if isinstance(nested, str):
                        return nested
        if isinstance(data, str):
            return data
        return ""

    def _read_message(self, stream) -> Dict[str, Any]:
        headers = {}
        while True:
            line = stream.readline()
            if not line:
                raise RuntimeError("MCP stream closed")
            line = line.decode("utf-8")
            if line in ("\r\n", "\n", ""):
                break
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip().lower()] = value.strip()

        content_length = int(headers.get("content-length", "0"))
        if content_length <= 0:
            return {}
        body = stream.read(content_length)
        return json.loads(body.decode("utf-8"))

    def _write_message(self, stream, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8")
        stream.write(header)
        stream.write(body)
        stream.flush()

    def _request(self, process: subprocess.Popen, payload: Dict[str, Any], expected_id: int) -> Dict[str, Any]:
        self._write_message(process.stdin, payload)

        while True:
            message = self._read_message(process.stdout)
            if not isinstance(message, dict):
                continue
            if message.get("id") == expected_id:
                return message

    def _extract_tool_text(self, result: Dict[str, Any]) -> str:
        content = result.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
            if parts:
                return "\n".join(parts)

        for key in ("text", "output", "result", "context"):
            value = result.get(key)
            if isinstance(value, str):
                return value
        return ""

    def _fetch_stdio(self, payload: Dict[str, Any]) -> str:
        if not self.config.server_command:
            return ""

        cmd = [self.config.server_command]
        if self.config.server_args:
            cmd.extend(shlex.split(self.config.server_args))

        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            init_response = self._request(
                process,
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "versline", "version": "0.1.3"},
                    },
                },
                expected_id=1,
            )
            if init_response.get("error"):
                return ""

            tool_response = self._request(
                process,
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": self.config.tool_name,
                        "arguments": payload,
                    },
                },
                expected_id=2,
            )
            if tool_response.get("error"):
                return ""

            result = tool_response.get("result")
            if isinstance(result, dict):
                return self._extract_tool_text(result)
            return ""
        finally:
            try:
                process.terminate()
            except Exception:
                pass
