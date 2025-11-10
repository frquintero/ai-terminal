import importlib
import os
import sys
from pathlib import Path
from unittest.mock import patch

from tests.fake_shell import FakeShellIntegration

_TEST_DIR = Path(__file__).parent
os.environ.setdefault("FS_CONTEXT_DB_PATH", str(_TEST_DIR / ".fs_context_test.db"))
os.environ.setdefault("FS_CONTEXT_JSONL_DIR", str(_TEST_DIR / ".fs_context_jsonl"))
os.environ.setdefault("HISTORY_DB_PATH", str(_TEST_DIR / ".history_test.db"))


def _load_tools_with_fake_shell():
    with patch("shell_integration.ShellIntegration", FakeShellIntegration):
        if "tools" in sys.modules:
            importlib.reload(sys.modules["tools"])
        else:
            import tools  # noqa: F401


_load_tools_with_fake_shell()
