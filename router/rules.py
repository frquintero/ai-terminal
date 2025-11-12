"""
Rule-based query classification for Router

Fast regex patterns to detect:
- SHELL: Direct shell commands (ls, git, docker, etc.)
- CHAT: Simple informational queries (what is, explain, define)
- Conservative fallback to PLANNER for ambiguous cases
"""

import re
from enum import Enum
from typing import Dict, List, Optional, Tuple


class Route(str, Enum):
    """Query routing destinations"""
    CHAT = "CHAT"       # Simple Q&A → Agent C
    CACHED = "CACHED"   # Previously executed → Tool + Agent C narrator
    SHELL = "SHELL"     # Shell command → Direct execution + Agent C narrator  
    PLANNER = "PLANNER" # Complex task → Agent A/B loop + Agent C summarizer


# Shell command patterns (common commands that should execute immediately)
# Philosophy: "Shell-First" - 50%+ of interactions are shell commands
SHELL_COMMAND_PATTERNS = [
    # File operations
    r'^ls\b',
    r'^ll\b',
    r'^dir\b',
    r'^pwd\b',
    r'^cd\b',
    r'^cat\b',
    r'^less\b',
    r'^more\b',
    r'^head\b',
    r'^tail\b',
    r'^grep\b',
    r'^find\b',
    r'^locate\b',
    r'^which\b',
    r'^whereis\b',
    
    # File manipulation
    r'^cp\b',
    r'^mv\b',
    r'^rm\b',
    r'^mkdir\b',
    r'^rmdir\b',
    r'^touch\b',
    r'^chmod\b',
    r'^chown\b',
    
    # Text processing
    r'^sed\b',
    r'^awk\b',
    r'^cut\b',
    r'^sort\b',
    r'^uniq\b',
    r'^wc\b',
    r'^diff\b',
    r'^patch\b',
    
    # System info
    r'^ps\b',
    r'^top\b',
    r'^htop\b',
    r'^df\b',
    r'^du\b',
    r'^free\b',
    r'^uname\b',
    r'^hostname\b',
    r'^uptime\b',
    r'^whoami\b',
    r'^id\b',
    
    # Package management
    r'^apt\b',
    r'^apt-get\b',
    r'^yum\b',
    r'^dnf\b',
    r'^pacman\b',
    r'^brew\b',
    r'^pip\b',
    r'^npm\b',
    r'^yarn\b',
    
    # Version control
    r'^git\b',
    r'^svn\b',
    r'^hg\b',
    
    # Docker/containers
    r'^docker\b',
    r'^docker-compose\b',
    r'^kubectl\b',
    r'^podman\b',
    
    # Build tools
    r'^make\b',
    r'^cmake\b',
    r'^cargo\b',
    r'^go\b',
    r'^mvn\b',
    r'^gradle\b',
    
    # Network tools
    r'^curl\b',
    r'^wget\b',
    r'^ping\b',
    r'^ssh\b',
    r'^scp\b',
    r'^rsync\b',
    r'^netstat\b',
    r'^ifconfig\b',
    r'^ip\b',
    
    # Archive/compression
    r'^tar\b',
    r'^gzip\b',
    r'^gunzip\b',
    r'^zip\b',
    r'^unzip\b',
    r'^bzip2\b',
    r'^xz\b',
    
    # Editors (both interactive and non-interactive batch modes)
    r'^vim\b',              # vim (interactive and batch)
    r'^vi\b',               # vi
    r'^nano\b',             # nano
    r'^nvim\b',             # neovim
    r'^emacs\b',            # emacs (will be detected as interactive unless with --batch flag)
    
    # File viewers (interactive paging)
    # Note: less/more are already in the list above
    
    # Database/shell REPLs (interactive)
    r'^python\b',           # Python REPL
    r'^python3\b',          # Python 3 REPL
    r'^node\b',             # Node.js REPL
    r'^irb\b',              # Ruby IRB
    r'^ruby\b',             # Ruby interactive
    r'^mysql\b',            # MySQL interactive
    r'^psql\b',             # PostgreSQL interactive
    r'^mongo\b',            # MongoDB interactive
    
    # Shells (interactive)
    r'^bash\b',             # Bash interactive
    r'^zsh\b',              # Zsh interactive
    r'^sh\b',               # Shell interactive
    
    # Terminal multiplexers
    r'^tmux\b',             # Tmux
    r'^screen\b',           # Screen
    
    # SSH/Remote (interactive)
    r'^ssh\b',              # SSH with terminal
    r'^man\b',              # Man pages
    
    # Common shell builtins/utilities
    r'^echo\b',
    r'^printf\b',
    r'^date\b',
    r'^cal\b',
    r'^bc\b',
    r'^seq\b',
    r'^yes\b',
    r'^true\b',
    r'^false\b',
    r'^sleep\b',
    r'^time\b',
    r'^timeout\b',
    
    # Misc utilities
    r'^jq\b',
    r'^jo\b',
    r'^tree\b',
    r'^watch\b',
    r'^xargs\b',
    r'^env\b',
    r'^export\b',
    r'^alias\b',
    r'^history\b',
    ]

# Compile patterns once at module load
_SHELL_PATTERNS_COMPILED = [re.compile(p, re.IGNORECASE) for p in SHELL_COMMAND_PATTERNS]


# Interactive command patterns (require TTY - vim, nano, top, etc.)
# These commands need full terminal control and should use run_interactive tool
INTERACTIVE_COMMAND_PATTERNS = [
    # Text editors (interactive)
    r'^vim\b(?!\s+-c)',        # vim (but not vim -c)
    r'^vi\b',                   # vi
    r'^nano\b',                 # nano
    r'^emacs\b(?!\s+--batch)',  # emacs (but not emacs --batch)
    r'^nvim\b(?!\s+-c)',        # neovim (but not nvim -c)
    
    # File viewers (interactive - paging)
    r'^less\b',                 # less (interactive pager)
    r'^more\b',                 # more (interactive pager)
    r'^man\b',                  # man pages
    
    # System monitoring (interactive)
    r'^top\b',                  # top
    r'^htop\b',                 # htop
    
    # Database/shell REPLs (interactive)
    r'^python\b',               # Python REPL
    r'^python3\b',              # Python 3 REPL
    r'^node\b',                 # Node.js REPL
    r'^irb\b',                  # Ruby IRB
    r'^ruby\b',                 # Ruby interactive
    r'^mysql\b',                # MySQL interactive
    r'^psql\b',                 # PostgreSQL interactive
    r'^mongo\b',                # MongoDB interactive
    
    # Shells (interactive)
    r'^bash\b',                 # Bash interactive
    r'^zsh\b',                  # Zsh interactive
    r'^sh\b',                   # Shell interactive
    
    # Terminal multiplexers
    r'^tmux\b',                 # Tmux
    r'^screen\b',               # Screen
    
    # SSH/Remote (interactive)
    r'^ssh\b',                  # SSH with terminal
]

_INTERACTIVE_PATTERNS_COMPILED = [re.compile(p, re.IGNORECASE) for p in INTERACTIVE_COMMAND_PATTERNS]


# Chat query patterns (simple informational questions)
CHAT_QUERY_PATTERNS = [
    r'^what\s+(is|are|was|were)\b',
    r'^who\s+(is|are|was|were)\b',
    r'^when\s+(is|are|was|were|did|does)\b',
    r'^where\s+(is|are|was|were)\b',
    r'^why\s+(is|are|was|were|do|does|did)\b',
    r'^how\s+(is|are|was|were|do|does|did)\b',
    r'^explain\b',
    r'^define\b',
    r'^describe\b',
    r'^tell\s+me\s+about\b',
    r'^can\s+you\s+explain\b',
    r'^can\s+you\s+tell\s+me\b',
]

_CHAT_PATTERNS_COMPILED = [re.compile(p, re.IGNORECASE) for p in CHAT_QUERY_PATTERNS]


class RuleEngine:
    """
    Fast regex-based query classifier.
    
    Classification order (highest to lowest precedence):
    1. SHELL - Direct shell commands
    2. CHAT - Simple informational queries
    3. PLANNER - Fallback for everything else (conservative)
    
    Note: CACHED route handled separately by IntentionCache lookup
    """
    
    def __init__(self):
        """Initialize rule engine with compiled patterns"""
        self.shell_patterns = _SHELL_PATTERNS_COMPILED
        self.chat_patterns = _CHAT_PATTERNS_COMPILED
        self.interactive_patterns = _INTERACTIVE_PATTERNS_COMPILED
    
    def classify(self, query: str) -> Tuple[Optional[Route], Optional[str]]:
        """
        Classify query using regex rules.
        
        Args:
            query: User query text
        
        Returns:
            (route, matched_rule) tuple
            - route: Route enum if matched, None if no match
            - matched_rule: Pattern that matched (for logging/debugging)
        
        Classification logic:
        - Check SHELL patterns first (highest priority)
        - Then CHAT patterns
        - Return None if no match (caller should fallback to PLANNER)
        """
        query_stripped = query.strip()
        
        # Priority 1: Shell commands
        for pattern in self.shell_patterns:
            if pattern.match(query_stripped):
                return Route.SHELL, pattern.pattern
        
        # Priority 2: Chat queries
        for pattern in self.chat_patterns:
            if pattern.search(query_stripped):
                return Route.CHAT, pattern.pattern
        
        # No match - return None (caller falls back to PLANNER)
        return None, None
    
    def is_interactive_command(self, query: str) -> bool:
        """
        Detect if query is an interactive command that requires TTY.
        
        Args:
            query: User query text
        
        Returns:
            True if matches interactive command pattern
        """
        query_stripped = query.strip()
        for pattern in self.interactive_patterns:
            if pattern.match(query_stripped):
                return True
        return False
    
    def get_stats(self) -> Dict[str, int]:
        """Get rule statistics for debugging"""
        return {
            "shell_patterns": len(self.shell_patterns),
            "chat_patterns": len(self.chat_patterns),
            "interactive_patterns": len(self.interactive_patterns),
        }
