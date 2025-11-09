import json
from types import SimpleNamespace

import pytest

from tools import HttpRequestTool


def _fake_metrics():
    return {
        "response_code": 200,
        "http_code": 200,
        "content_type": "application/json",
        "time_total": 0.12,
        "time_connect": 0.01,
        "time_namelookup": 0.002,
        "time_appconnect": 0.02,
        "time_starttransfer": 0.08,
        "size_download": 42,
        "errormsg": None,
        "url": "https://example.com/api",
        "method": "GET",
        "http_version": "2",
        "num_redirects": 0,
        "remote_ip": "93.184.216.34",
        "local_ip": "192.168.1.5",
    }


def test_http_request_tool_parses_metrics_and_returns_envelope(monkeypatch):
    tool = HttpRequestTool()
    marker = "__TEST_MARKER__"
    monkeypatch.setattr(tool, "_build_marker", lambda trace_id: marker)

    body = b'{"message":"ok"}'
    metrics_dict = _fake_metrics()
    metrics = json.dumps(metrics_dict).encode("utf-8")
    stdout = body + marker.encode("utf-8") + metrics
    verbose = (
        "> GET /api HTTP/1.1\n"
        "> Host: example.com\n"
        "< HTTP/1.1 200 OK\n"
        "< Content-Type: application/json\n"
    ).encode()
    fake_result = SimpleNamespace(returncode=0, stdout=stdout, stderr=verbose)
    captured = {}

    def fake_run(command, stdout=None, stderr=None, cwd=None, timeout=None):
        captured["command"] = command
        return fake_result

    monkeypatch.setattr(tool, "_run_curl", fake_run)

    output = tool.execute(url="https://example.com/api", method="GET", session_id="testing")
    data = json.loads(output)

    assert data["ok"] is True
    assert data["status"] == 200
    assert data["content_type"] == "application/json"
    assert data["session_id"] == "testing"
    assert data["metrics"]["response_code"] == 200
    assert data["latency"]["dns_lookup"] == pytest.approx(0.002)
    assert data["latency"]["ttfb"] == pytest.approx(0.08)
    assert data["diagnostics"]["http_version"] == metrics_dict["http_version"]
    assert data["diagnostics"]["remote_ip"] == metrics_dict["remote_ip"]
    assert data["body_format"] == "json"
    assert data["parsed_json"]["message"] == "ok"
    assert data["target_host"] == "example.com"
    assert data["throttle_delay_sec"] == 0
    assert "--config" in captured["command"]
    assert data["http_headers"]["request"][0]["line"] == "GET /api HTTP/1.1"
    assert data["http_headers"]["response"][1]["name"] == "Content-Type"


def test_http_request_tool_rejects_non_http_scheme():
    tool = HttpRequestTool()
    output = tool.execute(url="ftp://example.com", method="GET")
    assert "Only http and https schemes" in output


def test_http_request_tool_maps_exit_code(monkeypatch):
    tool = HttpRequestTool()
    marker = "__TEST_MARKER__"
    monkeypatch.setattr(tool, "_build_marker", lambda trace_id: marker)
    stdout = marker.encode("utf-8") + json.dumps(_fake_metrics()).encode("utf-8")
    fake_result = SimpleNamespace(returncode=6, stdout=stdout, stderr=b"Could not resolve host")
    monkeypatch.setattr(tool, "_run_curl", lambda *args, **kwargs: fake_result)

    output = tool.execute(url="https://broken.test", method="GET")
    data = json.loads(output)
    assert data["ok"] is False
    assert data["error_type"] == "dns_error"
    assert "resolve host" in data["error"]


def test_http_request_tool_maps_http_status(monkeypatch):
    tool = HttpRequestTool()
    marker = "__TEST_MARKER__"
    monkeypatch.setattr(tool, "_build_marker", lambda trace_id: marker)
    metrics = _fake_metrics()
    metrics["response_code"] = 404
    metrics["http_code"] = 404
    stdout = marker.encode("utf-8") + json.dumps(metrics).encode("utf-8")
    fake_result = SimpleNamespace(returncode=0, stdout=stdout, stderr=b"")
    monkeypatch.setattr(tool, "_run_curl", lambda *args, **kwargs: fake_result)

    output = tool.execute(url="https://example.com/missing", method="GET")
    data = json.loads(output)
    assert data["ok"] is False
    assert data["error_type"] == "resource_not_found"


def test_http_request_tool_detects_html(monkeypatch):
    tool = HttpRequestTool()
    marker = "__TEST_MARKER__"
    monkeypatch.setattr(tool, "_build_marker", lambda trace_id: marker)
    html = b"<!doctype html><html><body>hi</body></html>"
    metrics = _fake_metrics()
    metrics["content_type"] = "text/plain"
    stdout = html + marker.encode("utf-8") + json.dumps(metrics).encode("utf-8")
    fake_result = SimpleNamespace(returncode=0, stdout=stdout, stderr=b"")
    monkeypatch.setattr(tool, "_run_curl", lambda *args, **kwargs: fake_result)

    data = json.loads(tool.execute(url="https://example.com/page", method="GET"))
    assert data["body_format"] == "html"
    assert data["parsed_json"] is None


def test_session_update_persists_and_applies_headers(monkeypatch):
    tool = HttpRequestTool()
    marker = "__TEST_MARKER__"
    monkeypatch.setattr(tool, "_build_marker", lambda trace_id: marker)
    stdout = marker.encode("utf-8") + json.dumps(_fake_metrics()).encode("utf-8")
    verbose = b"> GET / HTTP/1.1\n"
    fake_result = SimpleNamespace(returncode=0, stdout=stdout, stderr=verbose)
    monkeypatch.setattr(tool, "_run_curl", lambda *args, **kwargs: fake_result)

    session_id = "auth-session"
    tool.execute(
        url="https://example.com",
        method="GET",
        session_id=session_id,
        session_update={
            "default_headers": {"X-Test": "alpha"},
            "auth_bearer": "secret-token"
        }
    )

    safe_id = tool._sanitize_session_id(session_id)
    config_path = tool.session_root / safe_id / "session.json"
    config = json.loads(config_path.read_text())
    assert config["default_headers"]["X-Test"] == "alpha"
    assert config["auth_bearer"] == "secret-token"

    captured = {}

    def fake_run(command, *args, **kwargs):
        captured["command"] = command
        return fake_result

    monkeypatch.setattr(tool, "_run_curl", fake_run)
    second_response = tool.execute(url="https://example.com", method="GET", session_id=session_id)
    assert not second_response.startswith("Error")

    header_values = []
    for idx, command_arg in enumerate(captured["command"]):
        if idx > 0 and captured["command"][idx - 1] == "--header":
            header_values.append(command_arg)
    assert "X-Test: alpha" in header_values
    assert "Authorization: Bearer secret-token" in header_values


def test_http_request_tool_blocks_private_ip(monkeypatch):
    tool = HttpRequestTool()
    monkeypatch.setattr(tool, "_run_curl", lambda *args, **kwargs: pytest.fail("curl should not run"))

    output = tool.execute(url="http://127.0.0.1")
    assert output.startswith("Error:")
    assert "SSRF protection" in output


def test_http_request_tool_allows_local_with_override(monkeypatch):
    tool = HttpRequestTool()
    marker = "__TEST_MARKER__"
    monkeypatch.setattr(tool, "_build_marker", lambda trace_id: marker)
    stdout = marker.encode("utf-8") + json.dumps(_fake_metrics()).encode("utf-8")
    fake_result = SimpleNamespace(returncode=0, stdout=stdout, stderr=b"")
    monkeypatch.setattr(tool, "_run_curl", lambda *args, **kwargs: fake_result)

    data = json.loads(
        tool.execute(url="http://127.0.0.1", allow_local_networks=True)
    )
    assert data["error_type"] is None


def test_http_request_tool_json_pointer_extraction(monkeypatch):
    tool = HttpRequestTool()
    marker = "__TEST_MARKER__"
    monkeypatch.setattr(tool, "_build_marker", lambda trace_id: marker)

    body = b'{"outer":{"message":"hello"}}'
    stdout = body + marker.encode("utf-8") + json.dumps(_fake_metrics()).encode("utf-8")
    fake_result = SimpleNamespace(returncode=0, stdout=stdout, stderr=b"")
    monkeypatch.setattr(tool, "_run_curl", lambda *args, **kwargs: fake_result)

    data = json.loads(
        tool.execute(
            url="https://example.com/api",
            parse_mode="json",
            json_pointer="/outer/message",
        )
    )
    assert data["json_pointer_value"] == "hello"


def test_http_request_tool_body_form_sets_encoding(monkeypatch):
    tool = HttpRequestTool()
    marker = "__TEST_MARKER__"
    monkeypatch.setattr(tool, "_build_marker", lambda trace_id: marker)
    stdout = marker.encode("utf-8") + json.dumps(_fake_metrics()).encode("utf-8")
    fake_result = SimpleNamespace(returncode=0, stdout=stdout, stderr=b"")
    captured = {}

    def fake_run(command, *args, **kwargs):
        captured["command"] = command
        return fake_result

    monkeypatch.setattr(tool, "_run_curl", fake_run)
    tool.execute(
        url="https://example.com/form",
        method="POST",
        body_form={"q": "curl", "page": 1},
    )

    command = captured["command"]
    assert "--data" in command
    assert any("Content-Type: application/x-www-form-urlencoded" in arg for arg in command)


def test_http_request_tool_injects_proxy(monkeypatch):
    tool = HttpRequestTool()
    marker = "__TEST_MARKER__"
    monkeypatch.setattr(tool, "_build_marker", lambda trace_id: marker)
    stdout = marker.encode("utf-8") + json.dumps(_fake_metrics()).encode("utf-8")
    fake_result = SimpleNamespace(returncode=0, stdout=stdout, stderr=b"")
    captured = {}
    monkeypatch.setattr(
        tool,
        "_run_curl",
        lambda command, *args, **kwargs: (captured.__setitem__("command", command) or fake_result),
    )

    tool.execute(
        url="https://example.com",
        proxy="http://proxy.local:8080",
        accept_compression=True,
    )

    command = captured["command"]
    assert "--proxy" in command
    proxy_index = command.index("--proxy")
    assert command[proxy_index + 1] == "http://proxy.local:8080"
    assert "--compressed" in command
