"""
Shared command-pattern definitions for routerless orchestration.

These patterns originated in router.rules but now live inside the orchestrator
package so they can be reused by the new dual-agent architecture without the
legacy Router dependency.
"""

from __future__ import annotations

import re
from typing import List, Pattern

__all__ = [
    "SHELL_COMMAND_PATTERNS",
    "INTERACTIVE_COMMAND_PATTERNS",
    "CHAT_QUERY_PATTERNS",
    "SHELL_PATTERNS_COMPILED",
    "INTERACTIVE_PATTERNS_COMPILED",
    "CHAT_PATTERNS_COMPILED",
]

# Shell command patterns (fast-path detection)
SHELL_COMMAND_PATTERNS: List[str] = [
    # File operations
    r"^ls\b",
    r"^ll\b",
    r"^dir\b",
    r"^pwd\b",
    r"^cd\b",
    r"^cat\b",
    r"^less\b",
    r"^more\b",
    r"^head\b",
    r"^tail\b",
    r"^grep\b",
    r"^find\b",
    r"^locate\b",
    r"^which\b",
    r"^whereis\b",
    # File manipulation
    r"^cp\b",
    r"^mv\b",
    r"^rm\b",
    r"^mkdir\b",
    r"^rmdir\b",
    r"^touch\b",
    r"^chmod\b",
    r"^chown\b",
    # Text processing
    r"^sed\b",
    r"^awk\b",
    r"^cut\b",
    r"^sort\b",
    r"^uniq\b",
    r"^wc\b",
    r"^diff\b",
    r"^patch\b",
    # System info
    r"^ps\b",
    r"^top\b",
    r"^htop\b",
    r"^df\b",
    r"^du\b",
    r"^free\b",
    r"^uname\b",
    r"^hostname\b",
    r"^uptime\b",
    r"^whoami\b",
    r"^id\b",
    # Package management
    r"^apt\b",
    r"^apt-get\b",
    r"^yum\b",
    r"^dnf\b",
    r"^pacman\b",
    r"^brew\b",
    r"^pip\b",
    r"^npm\b",
    r"^yarn\b",
    # Version control
    r"^git\b",
    r"^svn\b",
    r"^hg\b",
    # Containers
    r"^docker\b",
    r"^docker-compose\b",
    r"^kubectl\b",
    r"^podman\b",
    # Build tools
    r"^make\b",
    r"^cmake\b",
    r"^cargo\b",
    r"^go\b",
    r"^mvn\b",
    r"^gradle\b",
    # Network tools
    r"^curl\b",
    r"^wget\b",
    r"^ping\b",
    r"^ssh\b",
    r"^scp\b",
    r"^rsync\b",
    r"^netstat\b",
    r"^ifconfig\b",
    r"^ip\b",
    # Archive/compression
    r"^tar\b",
    r"^gzip\b",
    r"^gunzip\b",
    r"^zip\b",
    r"^unzip\b",
    r"^bzip2\b",
    r"^xz\b",
    # Editors / REPLs
    r"^vim\b",
    r"^vi\b",
    r"^nano\b",
    r"^nvim\b",
    r"^emacs\b",
    r"^python\b",
    r"^python3\b",
    r"^node\b",
    r"^irb\b",
    r"^ruby\b",
    r"^mysql\b",
    r"^psql\b",
    r"^mongo\b",
    # Shells / multiplexers
    r"^bash\b",
    r"^zsh\b",
    r"^sh\b",
    r"^tmux\b",
    r"^screen\b",
    # Misc utilities
    r"^man\b",
    r"^echo\b",
    r"^printf\b",
    r"^date\b",
    r"^cal\b",
    r"^bc\b",
    r"^seq\b",
    r"^yes\b",
    r"^true\b",
    r"^false\b",
    r"^sleep\b",
    r"^time\b",
    r"^timeout\b",
    r"^jq\b",
    r"^jo\b",
    r"^tree\b",
    r"^watch\b",
    r"^xargs\b",
    r"^env\b",
    r"^export\b",
    r"^alias\b",
    r"^history\b",
]

# Interactive commands (must go through run_interactive)
INTERACTIVE_COMMAND_PATTERNS: List[str] = [
    r"^vim\b(?!\s+-c)",
    r"^vi\b",
    r"^nano\b",
    r"^emacs\b(?!\s+--batch)",
    r"^nvim\b(?!\s+-c)",
    r"^less\b",
    r"^more\b",
    r"^man\b",
    r"^top\b",
    r"^htop\b",
    r"^python\b",
    r"^python3\b",
    r"^node\b",
    r"^irb\b",
    r"^ruby\b",
    r"^mysql\b",
    r"^psql\b",
    r"^mongo\b",
    r"^bash\b",
    r"^zsh\b",
    r"^sh\b",
    r"^tmux\b",
    r"^screen\b",
    r"^ssh\b",
]

# Simple chat queries
CHAT_QUERY_PATTERNS: List[str] = [
    r"^what\s+(is|are|was|were)\b",
    r"^who\s+(is|are|was|were)\b",
    r"^when\s+(is|are|was|were|did|does)\b",
    r"^where\s+(is|are|was|were)\b",
    r"^why\s+(is|are|was|were|do|does|did)\b",
    r"^how\s+(is|are|was|were|do|does|did)\b",
    r"^explain\b",
    r"^define\b",
    r"^describe\b",
    r"^tell\s+me\s+about\b",
    r"^can\s+you\s+explain\b",
    r"^can\s+you\s+tell\s+me\b",
]

SHELL_PATTERNS_COMPILED: List[Pattern[str]] = [
    re.compile(p, re.IGNORECASE) for p in SHELL_COMMAND_PATTERNS
]
INTERACTIVE_PATTERNS_COMPILED: List[Pattern[str]] = [
    re.compile(p, re.IGNORECASE) for p in INTERACTIVE_COMMAND_PATTERNS
]
CHAT_PATTERNS_COMPILED: List[Pattern[str]] = [
    re.compile(p, re.IGNORECASE) for p in CHAT_QUERY_PATTERNS
]
