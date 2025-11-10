import json
from datetime import datetime, timezone

from filesystem_context import get_fs_context_store
from tools import FilesystemSnapshotTool, _SESSION_STATE


def test_filesystem_snapshot_tool_returns_persisted_data():
    session_id = "snap-tool-test"
    _SESSION_STATE.reset(session_id)
    store = get_fs_context_store()
    store.record_snapshot(
        session_id,
        {
            "shell_cwd": "/tmp/fs-snap",
            "working_dir": "/tmp/fs-snap/workdir",
            "workspace_hint": "/tmp/fs-snap/workdir/workspace",
            "sandbox_root": "ai-terminal-wd",
            "command": "ls Downloads/",
            "command_preview": "ls Downloads/",
            "exit_code": 0,
            "metadata": {"test": True},
        },
    )
    store.record_file_event(
        session_id,
        {
            "operation": "write",
            "requested_path": "workspace/report.txt",
            "relative_path": "workspace/report.txt",
            "absolute_path": "/tmp/fs-snap/workdir/workspace/report.txt",
            "location": "workspace",
            "source": "unit-test",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "interactive_hint": "/tmp/fs-snap/workdir/workspace/report.txt",
        },
    )

    tool = FilesystemSnapshotTool()
    payload = json.loads(tool.execute(limit=5))

    assert payload["session_id"] == session_id
    assert payload["snapshot"]["shell_cwd"] == "/tmp/fs-snap"
    assert payload["snapshot"]["command"] == "ls Downloads/"
    assert payload["recent_events"], "Expected at least one persisted file event"
    event = payload["recent_events"][-1]
    assert event["requested_path"] == "workspace/report.txt"
