import importlib
import sys
from unittest.mock import patch

from tests.fake_shell import FakeShellIntegration


def _load_tools_with_fake_shell():
    with patch("shell_integration.ShellIntegration", FakeShellIntegration):
        if "tools" in sys.modules:
            importlib.reload(sys.modules["tools"])
        else:
            import tools  # noqa: F401


_load_tools_with_fake_shell()
