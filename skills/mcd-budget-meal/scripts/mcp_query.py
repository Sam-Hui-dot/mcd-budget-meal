"""Bounded, read-only McDonald's Streamable HTTP client. Python 3.10+, stdlib only."""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ENDPOINT = "https://mcp.mcd.cn"
TOOLS = ("query-nearby-stores", "query-meals", "query-store-coupons", "query-meal-detail", "calculate-price")
MAX_RESPONSE = 4_000_000


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError("Endpoint redirect refused")


def authorization(use_workbuddy_config):
    token = os.environ.get("MCD_MCP_TOKEN", "").strip()
    if token and not use_workbuddy_config:
        return "Bearer " + token
    if use_workbuddy_config:
        config_path = Path.home() / ".workbuddy" / "mcp.json"
        config = json.loads(config_path.read_text(encoding="utf-8-sig"))
        server = config["mcpServers"]["mcd-mcp"]
        if server.get("url", "").rstrip("/") != ENDPOINT:
            raise RuntimeError("WorkBuddy endpoint differs from official endpoint")
        value = server.get("headers", {}).get("Authorization", "")
        if not value.startswith("Bearer ") or "${" in value or not value[7:].strip():
            raise RuntimeError("No usable local authorization")
        return value
    raise RuntimeError("Set MCD_MCP_TOKEN or explicitly use --use-workbuddy-config")


class Client:
    def __init__(self, auth):
        self.headers = {"Authorization": auth, "Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        self.opener = urllib.request.build_opener(NoRedirect())
        self.session = None
        self.protocol = None
        self.counter = 0

    def rpc(self, method, params, notification=False):
        self.counter += 1
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        if not notification:
            payload["id"] = self.counter
        headers = dict(self.headers)
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        if self.protocol:
            headers["MCP-Protocol-Version"] = self.protocol
        request = urllib.request.Request(ENDPOINT, json.dumps(payload).encode("utf-8"), headers, method="POST")
        with self.opener.open(request, timeout=25) as response:
            self.session = response.headers.get("Mcp-Session-Id", self.session)
            if response.status in (202, 204):
                return None
            if "text/event-stream" in response.headers.get("Content-Type", ""):
                data, size = [], 0
                for raw in response:
                    size += len(raw)
                    if size > MAX_RESPONSE:
                        raise RuntimeError("Response size limit exceeded")
                    line = raw.decode("utf-8").rstrip("\r\n")
                    if line.startswith("data:"):
                        data.append(line[5:].lstrip())
                    elif not line and data:
                        result = json.loads("\n".join(data))
                        if result.get("id") == payload.get("id"):
                            return result
                        data = []
                raise RuntimeError("Missing MCP response")
            raw = response.read(MAX_RESPONSE + 1)
            if len(raw) > MAX_RESPONSE:
                raise RuntimeError("Response size limit exceeded")
            return json.loads(raw) if raw else None

    def initialize(self):
        response = self.rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "mcd-budget-meal", "version": "0.1.0"}})
        if not response or "error" in response:
            raise RuntimeError("MCP initialization failed")
        self.protocol = response["result"]["protocolVersion"]
        self.rpc("notifications/initialized", {}, notification=True)

    def describe(self, tool):
        if tool not in TOOLS:
            raise ValueError("Tool outside read-only allowlist")
        response = self.rpc("tools/list", {})
        if not isinstance(response, dict) or "error" in response:
            raise RuntimeError("Cannot read current tool schema")
        result = response.get("result", {})
        for definition in result.get("tools", []):
            if definition.get("name") == tool:
                return definition
        raise RuntimeError("Required tool unavailable in first tools/list page")

    def call(self, tool, arguments):
        if tool not in TOOLS:
            raise ValueError("Tool outside read-only allowlist")
        return self.rpc("tools/call", {"name": tool, "arguments": arguments})


def structured_result(response):
    """Extract a successful official business response, never invent a zero price."""
    if not isinstance(response, dict) or "error" in response:
        raise ValueError("MCP 返回协议错误或空响应")
    result = response.get("result")
    if not isinstance(result, dict) or result.get("isError"):
        raise ValueError("MCP 工具返回错误")
    payload = result.get("structuredContent")
    if not isinstance(payload, dict):
        raise ValueError("缺少 structuredContent；需检查服务返回格式")
    if payload.get("success") is not True:
        raise ValueError("官方核价未明确成功；本轮停止，不重试")
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tool", choices=TOOLS)
    parser.add_argument("--args", type=Path, help="JSON object with current official tool arguments")
    parser.add_argument("--describe", action="store_true", help="Get this tool's current schema instead of calling it")
    parser.add_argument("--output", type=Path, help="Optional private file for exact request/response record")
    parser.add_argument("--use-workbuddy-config", action="store_true", help="Read existing local mcd-mcp authorization; never modify config")
    opts = parser.parse_args()
    if not opts.describe and opts.args is None:
        parser.error("--args is required unless --describe is used")
    arguments = None
    if not opts.describe:
        arguments = json.loads(opts.args.read_text(encoding="utf-8-sig"))
        if not isinstance(arguments, dict):
            raise RuntimeError("Arguments must be a JSON object")
        if opts.tool == "calculate-price" and (not isinstance(arguments.get("items"), list) or not arguments["items"]):
            raise RuntimeError("calculate-price requires a nonempty items array")
    client = Client(authorization(opts.use_workbuddy_config))
    client.initialize()
    if opts.describe:
        output = client.describe(opts.tool)
    else:
        response = client.call(opts.tool, arguments)
        record = {"recorded_at": datetime.now(timezone.utc).isoformat(), "transport": "direct Streamable HTTP", "tool": opts.tool, "arguments": arguments, "response": response}
        if opts.output:
            opts.output.parent.mkdir(parents=True, exist_ok=True)
            opts.output.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        output = response.get("result", {}).get("structuredContent", response)
        if "error" in response or response.get("result", {}).get("isError") or output.get("success") is False:
            print(json.dumps(output, ensure_ascii=False))
            return 1
    print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        sys.exit(main())
    except Exception as exc:
        # Do not print exception strings that might contain credentials or request headers.
        print(json.dumps({"error_type": type(exc).__name__, "http_status": getattr(exc, "code", None), "message": "Stopped; no automatic retry. Check local args/config and network."}))
        sys.exit(1)
