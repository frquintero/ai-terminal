"""
Robust command parser for interactive command detection.

Replaces brittle option tables with minimal, stable wrapper handlers.
Philosophy: Fail-safe by blocking when ambiguous.
"""

import os
import re
import shlex
from typing import Tuple, List, Set


# ============================================================================
# Helper Functions
# ============================================================================

def is_assignment(token: str) -> bool:
    """Check if token is environment variable assignment (NAME=value or NAME+=value)"""
    return bool(re.match(r'^[A-Za-z_][A-Za-z0-9_]*\+?=', token))


def basename(token: str) -> str:
    """Extract basename from path"""
    return os.path.basename(token)


# ============================================================================
# Option Scanner Utility
# ============================================================================

def scan_options(
    tokens: List[str], 
    start_idx: int,
    short_args: Set[str] = None,
    long_args: Set[str] = None
) -> Tuple[int, Set[str]]:
    """
    Scan through options starting at start_idx, returning index after options and collected flags.
    
    Args:
        tokens: Command tokens
        start_idx: Where to start scanning
        short_args: Set of single-char options that take arguments (e.g., {'u', 'g'})
        long_args: Set of long option names that take arguments (e.g., {'user', 'group'})
    
    Returns:
        (next_index, flags_seen)
    """
    short_args = short_args or set()
    long_args = long_args or set()
    flags = set()
    i = start_idx
    
    while i < len(tokens):
        token = tokens[i]
        
        # Stop at --
        if token == '--':
            i += 1
            break
        
        # Non-option token
        if not token.startswith('-'):
            break
        
        # Long option
        if token.startswith('--'):
            opt_name = token[2:]
            
            # Handle --opt=value
            if '=' in opt_name:
                opt_name = opt_name.split('=', 1)[0]
                flags.add(opt_name)
                i += 1
            # Handle --opt value (if takes argument)
            elif opt_name in long_args:
                flags.add(opt_name)
                i += 1
                # Skip argument if present
                if i < len(tokens):
                    i += 1
            # No-argument long option
            else:
                flags.add(opt_name)
                i += 1
        
        # Short option(s)
        else:
            opt_chars = token[1:]  # Remove leading -
            
            # Check if last char takes an argument
            if opt_chars and opt_chars[-1] in short_args:
                for c in opt_chars:
                    flags.add(c)
                i += 1
                # Skip argument if present
                if i < len(tokens):
                    i += 1
            else:
                # All flags, no arguments
                for c in opt_chars:
                    flags.add(c)
                i += 1
    
    return i, flags


# ============================================================================
# Wrapper Handlers
# ============================================================================

def handle_env(tokens: List[str], start_idx: int) -> Tuple[int, bool, Set[str]]:
    """
    Handle env wrapper.
    
    Returns: (next_index, is_ambiguous, flags_seen)
    """
    # env special case: -S/--split-string embeds command in string → ambiguous
    short_args = {'u', 'C', 'S'}  # -u VAR, -C DIR, -S STRING
    long_args = {'unset', 'chdir', 'split-string'}
    
    idx, flags = scan_options(tokens, start_idx, short_args, long_args)
    
    # Check for ambiguous -S or --split-string
    if 'S' in flags or 'split-string' in flags:
        return idx, True, flags
    
    # After options, skip NAME=VALUE assignments (specific to env)
    while idx < len(tokens) and is_assignment(tokens[idx]):
        idx += 1
    
    return idx, False, flags


def handle_sudo(tokens: List[str], start_idx: int) -> Tuple[int, bool, Set[str]]:
    """
    Handle sudo wrapper.
    
    Returns: (next_index, is_ambiguous, flags_seen)
    """
    short_args = {'u', 'g', 'p', 'a', 'C', 'r', 't'}  # Options that take arguments
    long_args = {'user', 'group', 'prompt', 'chdir', 'command', 'role', 'type'}
    
    idx, flags = scan_options(tokens, start_idx, short_args, long_args)
    
    # sudo can be followed by environment assignments before command
    while idx < len(tokens) and is_assignment(tokens[idx]):
        idx += 1
    
    return idx, False, flags


def handle_timeout(tokens: List[str], start_idx: int) -> Tuple[int, bool, Set[str]]:
    """
    Handle timeout wrapper.
    
    Returns: (next_index, is_ambiguous, flags_seen)
    """
    short_args = {'k', 's'}  # -k DURATION, -s SIGNAL
    long_args = {'kill-after', 'signal'}
    
    idx, flags = scan_options(tokens, start_idx, short_args, long_args)
    
    # After options, consume duration (positional argument)
    if idx < len(tokens) and not tokens[idx].startswith('-'):
        idx += 1
    
    return idx, False, flags


def handle_time(tokens: List[str], start_idx: int) -> Tuple[int, bool, Set[str]]:
    """
    Handle time wrapper (GNU time, not shell builtin).
    
    Returns: (next_index, is_ambiguous, flags_seen)
    """
    short_args = {'o', 'a'}  # -o FILE, -a FILE
    long_args = {'output', 'append', 'format', 'portability'}
    
    idx, flags = scan_options(tokens, start_idx, short_args, long_args)
    
    return idx, False, flags


def handle_nice(tokens: List[str], start_idx: int) -> Tuple[int, bool, Set[str]]:
    """
    Handle nice wrapper.
    
    Returns: (next_index, is_ambiguous, flags_seen)
    """
    short_args = {'n'}  # -n ADJUSTMENT
    long_args = {'adjustment'}
    
    idx, flags = scan_options(tokens, start_idx, short_args, long_args)
    
    return idx, False, flags


def handle_nohup(tokens: List[str], start_idx: int) -> Tuple[int, bool, Set[str]]:
    """
    Handle nohup wrapper (no options that take arguments).
    
    Returns: (next_index, is_ambiguous, flags_seen)
    """
    idx, flags = scan_options(tokens, start_idx, set(), set())
    
    return idx, False, flags


# ============================================================================
# Wrapper Registry
# ============================================================================

WRAPPER_HANDLERS = {
    'env': handle_env,
    'sudo': handle_sudo,
    'timeout': handle_timeout,
    'time': handle_time,
    'nice': handle_nice,
    'nohup': handle_nohup,
    'strace': handle_nohup,  # strace can use nohup's simple handler
    'gdb': handle_nohup,
    'valgrind': handle_nohup,
}


# ============================================================================
# Interactive Command Detection
# ============================================================================

# Commands that are always interactive (editors, pagers, monitors)
ALWAYS_INTERACTIVE = {
    'vim', 'vi', 'nvim', 'emacs',
    'nano', 'ed', 'joe',
    'less', 'more', 'man',
    'top', 'htop', 'iotop',
    'tmux', 'screen',
    'ssh', 'telnet',
    'mysql', 'psql', 'mongo', 'redis-cli',
    'irb',  # Ruby REPL (no script mode)
}

# Shells (check for -c flag)
SHELLS = {'bash', 'sh', 'zsh', 'fish', 'dash', 'ksh'}

# Python interpreters (check for -c, -m, or script)
PYTHONS = {'python', 'python2', 'python3', 'ipython', 'pypy', 'pypy3'}

# Node.js interpreters (check for -e, -p, or script)
NODES = {'node', 'nodejs'}

# Ruby interpreters (check for -e or script)
RUBIES = {'ruby', 'irb'}


def is_interactive_command(cmd: str, args: List[str]) -> Tuple[bool, str]:
    """
    Determine if command is interactive based on command name and arguments.
    
    Returns: (is_interactive, reason)
    """
    cmd_base = basename(cmd)
    
    # Always interactive commands
    if cmd_base in ALWAYS_INTERACTIVE:
        return True, f"'{cmd_base}' is an editor/pager/monitor"
    
    # Shells - interactive unless -c is present
    if cmd_base in SHELLS:
        if '-c' in args:
            return False, f"Shell '{cmd_base}' with -c (non-interactive)"
        return True, f"Shell '{cmd_base}' without -c"
    
    # Python - interactive unless -c/-m or script present
    if cmd_base in PYTHONS:
        # Check for interactive flag
        if '-i' in args:
            return True, f"Python with -i flag"
        
        # Check for non-interactive modes
        if '-c' in args or '-m' in args:
            return False, f"Python with -c/-m (non-interactive)"
        
        # Check for script argument
        for arg in args:
            if not arg.startswith('-') and arg.endswith('.py'):
                return False, f"Python with script ({arg})"
        
        # Bare python → likely REPL
        return True, f"Bare Python (likely REPL)"
    
    # Node.js - interactive unless -e/-p or script present
    if cmd_base in NODES:
        # Check for interactive flag
        if '-i' in args or '--interactive' in args:
            return True, f"Node with -i/--interactive flag"
        
        # Check for non-interactive modes
        if '-e' in args or '--eval' in args or '-p' in args or '--print' in args:
            return False, f"Node with -e/-p (non-interactive)"
        
        # Check for script argument (common extensions + extensionless)
        for arg in args:
            if not arg.startswith('-'):
                # Accept .js, .mjs, .cjs, .jsx, .ts, .tsx, or extensionless
                # For extensionless: check basename without leading dot
                arg_base = basename(arg)
                arg_name = arg_base.lstrip('.')  # Remove leading dots for hidden files
                if (arg.endswith(('.js', '.mjs', '.cjs', '.jsx', '.ts', '.tsx')) or 
                    '.' not in arg_name):
                    return False, f"Node with script ({arg})"
        
        # Bare node → likely REPL
        return True, f"Bare Node (likely REPL)"
    
    # Ruby - interactive unless -e or script present
    if cmd_base in RUBIES:
        # irb is always interactive
        if cmd_base == 'irb':
            return True, f"irb is always interactive"
        
        # Check for non-interactive modes
        if '-e' in args:
            return False, f"Ruby with -e (non-interactive)"
        
        # Check for script argument (common extensions + extensionless)
        for arg in args:
            if not arg.startswith('-'):
                # Accept .rb or extensionless scripts
                # For extensionless: check basename without leading dot
                arg_base = basename(arg)
                arg_name = arg_base.lstrip('.')  # Remove leading dots for hidden files
                if arg.endswith('.rb') or '.' not in arg_name:
                    return False, f"Ruby with script ({arg})"
        
        # Bare ruby → likely REPL
        return True, f"Bare Ruby (likely REPL)"
    
    # Default: not in interactive set
    return False, f"'{cmd_base}' not in interactive set"


# ============================================================================
# Main Parser
# ============================================================================

def parse_command(cmd_str: str) -> Tuple[bool, str]:
    """
    Parse command and determine if it's interactive.
    
    Returns: (is_interactive, reason)
    
    Philosophy: Fail-safe by blocking when ambiguous or uncertain.
    """
    try:
        tokens = shlex.split(cmd_str, posix=True)
    except ValueError as e:
        # Malformed command (unclosed quotes, etc.)
        return True, f"Malformed command: {e}"
    
    if not tokens:
        return True, "Empty command (blocking by default)"
    
    # Skip leading environment assignments
    i = 0
    while i < len(tokens) and is_assignment(tokens[i]):
        i += 1
    
    if i >= len(tokens):
        return False, "Assignment-only command (allowed)"
    
    # Peel known wrappers
    wrappers_seen = []
    while i < len(tokens):
        cmd_base = basename(tokens[i])
        
        if cmd_base not in WRAPPER_HANDLERS:
            break
        
        wrappers_seen.append(cmd_base)
        handler = WRAPPER_HANDLERS[cmd_base]
        
        i, is_ambiguous, flags = handler(tokens, i + 1)
        
        # Fail-safe: block on ambiguity
        if is_ambiguous:
            return True, f"Ambiguous parsing for wrapper '{cmd_base}' (blocking)"
        
        # Check for special wrapper flags that spawn interactive shells
        if cmd_base == 'sudo' and ('i' in flags or 's' in flags):
            return True, f"sudo with -i/-s (interactive shell)"
        
        if i >= len(tokens):
            return True, f"No command after wrapper '{cmd_base}' (blocking)"
    
    if i >= len(tokens):
        return True, "No executable found after wrappers (blocking by default)"
    
    # Extract command and remaining arguments
    cmd = tokens[i]
    args = tokens[i+1:]
    
    # Detect interactive command
    return is_interactive_command(cmd, args)
