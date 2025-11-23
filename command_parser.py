"""
Robust command parser for interactive command detection.

Replaces brittle option tables with minimal, stable wrapper handlers.
Philosophy: Fail-safe by blocking when ambiguous.
"""

import os
import re
from collections import deque
from dataclasses import dataclass, field
from typing import Tuple, List, Set, Dict, Optional


# ============================================================================
# Helper Functions
# ============================================================================

def is_assignment(token: str) -> bool:
    """Check if token is environment variable assignment (NAME=value or NAME+=value)"""
    return bool(re.match(r'^[A-Za-z_][A-Za-z0-9_]*\+?=', token))


def basename(token: str) -> str:
    """Extract basename from path"""
    return os.path.basename(token)


NONINTERACTIVE_PAGERS = {
    "cat",
    "/bin/cat",
    "cat -n",
    "cat -v",
}


def _is_noninteractive_pager(pager: str) -> bool:
    normalized = pager.strip().lower()
    if not normalized:
        return False
    if normalized in NONINTERACTIVE_PAGERS:
        return True
    if normalized.startswith("cat "):
        return True
    if normalized.startswith("/bin/cat"):
        return True
    return False


def _extract_man_pager(args: List[str], env_vars: Dict[str, str]) -> str:
    """Return pager override from args/env if present."""
    i = 0
    while i < len(args):
        token = args[i]
        if token == '-P' and i + 1 < len(args):
            return args[i + 1]
        if token.startswith('-P') and len(token) > 2:
            return token[2:]
        if token == '--pager' and i + 1 < len(args):
            return args[i + 1]
        if token.startswith('--pager='):
            return token.split('=', 1)[1]
        i += 1
    for key in ('MANPAGER', 'PAGER'):
        if key in env_vars:
            return env_vars[key]
    return ""


def parse_env_assignments(env_tokens: List[str]) -> Dict[str, str]:
    """
    Convert NAME=VALUE tokens into dict.
    Supports NAME+=VALUE by stripping '+='.
    """
    env = {}
    for token in env_tokens:
        if '=' not in token:
            continue
        name, value = token.split('=', 1)
        name = name.rstrip('+')
        env[name] = value
    return env


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
# Shell Parsing & Context Models
# ============================================================================


class CommandParseError(Exception):
    """Raised when a command string cannot be parsed safely."""


@dataclass
class LexToken:
    kind: str
    value: str


@dataclass
class SimpleCommand:
    words: List[str] = field(default_factory=list)
    stdin_redir: bool = False
    stdout_redir: bool = False
    stderr_redir: bool = False
    pipeline_in: bool = False
    pipeline_out: bool = False

    def has_content(self) -> bool:
        return bool(self.words or self.stdin_redir or self.stdout_redir or self.stderr_redir)


@dataclass
class CommandContext:
    executable: str
    args: List[str]
    env_vars: Dict[str, str]
    wrappers: List[str]
    stdin_bound: bool
    stdout_redirected: bool
    stderr_redirected: bool
    pipeline_position: str


@dataclass
class CommandAnalysis:
    is_interactive: bool
    reason: str
    primary_context: Optional[CommandContext]
    contexts: List[CommandContext]


class ShellLexer:
    """Lightweight lexer that understands shell quoting, operators, and heredocs."""

    CONTROL_OPS = {'&&', '||', ';', '&'}
    PIPE_OPS = {'|', '|&'}

    def __init__(self, text: str):
        self.text = text
        self.length = len(text)
        self.pos = 0
        self.heredocs = deque()

    def eof(self) -> bool:
        return self.pos >= self.length

    def peek_char(self) -> str:
        if self.pos >= self.length:
            return ''
        return self.text[self.pos]

    def _peek_ahead(self, offset: int) -> str:
        idx = self.pos + offset
        if idx >= self.length:
            return ''
        return self.text[idx]

    def _advance(self, count: int = 1) -> None:
        self.pos = min(self.length, self.pos + count)

    def _skip_comment(self) -> None:
        while self.pos < self.length and self.text[self.pos] != '\n':
            self.pos += 1

    def _consume_line_continuation(self) -> bool:
        if self.peek_char() == '\\' and self._peek_ahead(1) == '\n':
            self._advance(2)
            return True
        return False

    def _consume_pending_heredocs(self) -> None:
        while self.heredocs:
            delimiter, strip_tabs = self.heredocs.popleft()
            while True:
                if self.pos >= self.length:
                    return
                newline = self.text.find('\n', self.pos)
                if newline == -1:
                    line = self.text[self.pos:]
                    self.pos = self.length
                else:
                    line = self.text[self.pos:newline]
                    self.pos = newline + 1
                candidate = line.lstrip('\t') if strip_tabs else line
                if candidate == delimiter:
                    break

    def skip_whitespace(self) -> None:
        while self.pos < self.length:
            if self._consume_line_continuation():
                continue
            ch = self.peek_char()
            if ch in ' \t\r':
                self._advance(1)
                continue
            if ch == '#':
                prev = self.text[self.pos - 1] if self.pos > 0 else ' '
                if prev in ' \t\r\n':
                    self._skip_comment()
                    continue
            if ch == '\n':
                self._advance(1)
                if self.heredocs:
                    self._consume_pending_heredocs()
                continue
            break

    def read_word(self) -> str:
        self.skip_whitespace()
        buf: List[str] = []
        while self.pos < self.length:
            ch = self.peek_char()
            if ch in ' \t\r\n':
                break
            if ch in '|&;<>':
                break
            if ch == '\\':
                self._advance(1)
                if self.pos < self.length:
                    buf.append(self.text[self.pos])
                    self._advance(1)
                continue
            if ch == "'":
                buf.append(self._consume_single_quote())
                continue
            if ch == '"':
                buf.append(self._consume_double_quote())
                continue
            if ch == '$' and self._peek_ahead(1) == '(':
                buf.append(self._consume_command_substitution())
                continue
            buf.append(ch)
            self._advance(1)
        return ''.join(buf)

    def _consume_single_quote(self) -> str:
        # Skip opening quote
        self._advance(1)
        start = self.pos
        while self.pos < self.length and self.text[self.pos] != "'":
            self.pos += 1
        if self.pos >= self.length:
            raise CommandParseError("Unterminated single quote")
        segment = self.text[start:self.pos]
        self._advance(1)  # closing quote
        return segment

    def _consume_double_quote(self) -> str:
        self._advance(1)
        buf: List[str] = []
        while self.pos < self.length:
            ch = self.peek_char()
            if ch == '"':
                self._advance(1)
                break
            if ch == '\\':
                self._advance(1)
                if self.pos < self.length:
                    buf.append(self.text[self.pos])
                    self._advance(1)
                continue
            if ch == '$' and self._peek_ahead(1) == '(':
                buf.append(self._consume_command_substitution())
                continue
            buf.append(ch)
            self._advance(1)
        else:
            raise CommandParseError("Unterminated double quote")
        return ''.join(buf)

    def _consume_command_substitution(self) -> str:
        # Assumes starting at $(
        self._advance(2)
        depth = 1
        buf = ['$(']
        while self.pos < self.length and depth > 0:
            ch = self.peek_char()
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
            elif ch == "'":
                buf.append("'" + self._consume_single_quote() + "'")
                continue
            elif ch == '"':
                buf.append('"' + self._consume_double_quote() + '"')
                continue
            buf.append(ch)
            self._advance(1)
        if depth != 0:
            raise CommandParseError("Unterminated command substitution")
        buf.append(')')
        return ''.join(buf)

    def _read_operator(self) -> str:
        ch = self.peek_char()
        if ch == '|':
            second = self._peek_ahead(1)
            if second == '|':
                self._advance(2)
                return '||'
            if second == '&':
                self._advance(2)
                return '|&'
            self._advance(1)
            return '|'
        if ch == '&':
            if self._peek_ahead(1) == '&':
                self._advance(2)
                return '&&'
            self._advance(1)
            return '&'
        if ch == ';':
            self._advance(1)
            return ';'
        if ch == '<':
            second = self._peek_ahead(1)
            third = self._peek_ahead(2)
            if second == '<' and third == '<':
                self._advance(3)
                return '<<<'
            if second == '<' and third == '-':
                self._advance(3)
                return '<<-'
            if second == '<':
                self._advance(2)
                return '<<'
            if second == '&':
                self._advance(2)
                return '<&'
            self._advance(1)
            return '<'
        if ch == '>':
            second = self._peek_ahead(1)
            if second == '>':
                self._advance(2)
                return '>>'
            if second == '&':
                self._advance(2)
                return '>&'
            self._advance(1)
            return '>'
        self._advance(1)
        return ch

    def _classify_operator(self, value: str) -> str:
        if value in self.PIPE_OPS:
            return 'pipeline'
        if value in self.CONTROL_OPS:
            return 'control'
        if value.startswith('<'):
            return 'redir_in'
        if value.startswith('>') or '>' in value:
            return 'redir_out'
        return 'operator'

    def next_token(self) -> Optional[LexToken]:
        self.skip_whitespace()
        if self.eof():
            return None
        ch = self.peek_char()
        if ch in '|&;<>':
            value = self._read_operator()
            kind = self._classify_operator(value)
            return LexToken(kind, value)
        word = self.read_word()
        return LexToken('word', word)

    def register_heredoc(self, delimiter: str, strip_tabs: bool) -> None:
        self.heredocs.append((delimiter, strip_tabs))


def _finalize_pipeline(pipeline: List[SimpleCommand], sink: List[SimpleCommand]) -> None:
    if not pipeline:
        return
    for idx, cmd in enumerate(pipeline):
        cmd.pipeline_in = idx > 0
        cmd.pipeline_out = idx < len(pipeline) - 1
    sink.extend(pipeline)
    pipeline.clear()


def _parse_simple_commands(command: str) -> List[SimpleCommand]:
    lexer = ShellLexer(command)
    commands: List[SimpleCommand] = []
    pipeline: List[SimpleCommand] = []
    current = SimpleCommand()
    pending_fd: Optional[str] = None

    while True:
        token = lexer.next_token()
        if token is None:
            if pending_fd:
                raise CommandParseError("Dangling file descriptor before end of command")
            if current.has_content():
                pipeline.append(current)
            _finalize_pipeline(pipeline, commands)
            break

        if token.kind == 'word':
            next_char = lexer.peek_char()
            if token.value.isdigit() and next_char in ('<', '>'):
                pending_fd = token.value
                continue
            current.words.append(token.value)
            continue

        if token.kind in {'pipeline', 'control'}:
            if pending_fd:
                raise CommandParseError(f"Dangling file descriptor before '{token.value}'")
            if not current.has_content():
                raise CommandParseError(f"Missing command before '{token.value}'")
            pipeline.append(current)
            if token.kind == 'pipeline':
                current = SimpleCommand()
                continue
            _finalize_pipeline(pipeline, commands)
            current = SimpleCommand()
            continue

        if token.kind in {'redir_in', 'redir_out'}:
            operator = token.value
            if pending_fd:
                operator = f"{pending_fd}{operator}"
                pending_fd = None
            target = lexer.read_word()
            if not target:
                raise CommandParseError(f"Missing redirection target for '{operator}'")
            if operator.startswith('<'):
                current.stdin_redir = True
                if operator in ('<<', '<<-'):
                    lexer.register_heredoc(target, strip_tabs=(operator == '<<-'))
            if '>' in operator or operator.startswith('>'):
                current.stdout_redir = True
                if operator.startswith('2') or operator.endswith('&2') or '>&' in operator:
                    current.stderr_redir = True
            continue

        # Treat unsupported operators as literal words to remain permissive.
        current.words.append(token.value)

    return commands


def _build_context_from_simple(simple: SimpleCommand) -> Tuple[Optional[CommandContext], Optional[str]]:
    tokens = list(simple.words)
    if not tokens:
        return None, None

    env_tokens = []
    idx = 0
    while idx < len(tokens) and is_assignment(tokens[idx]):
        env_tokens.append(tokens[idx])
        idx += 1
    env_vars = parse_env_assignments(env_tokens)

    if idx >= len(tokens):
        return None, "Assignment-only command (allowed)"

    working_tokens = tokens[idx:]
    wrappers = []
    token_idx = 0
    while token_idx < len(working_tokens):
        cmd_base = basename(working_tokens[token_idx])
        handler = WRAPPER_HANDLERS.get(cmd_base)
        if not handler:
            break
        wrappers.append(cmd_base)
        token_idx, is_ambiguous, flags = handler(working_tokens, token_idx + 1)
        if is_ambiguous:
            raise CommandParseError(f"Ambiguous parsing for wrapper '{cmd_base}' (blocking)")
        if cmd_base == 'sudo' and ('i' in flags or 's' in flags):
            raise CommandParseError("sudo with -i/-s (interactive shell)")
        if token_idx >= len(working_tokens):
            raise CommandParseError(f"No command after wrapper '{cmd_base}' (blocking)")

    if token_idx >= len(working_tokens):
        return None, "Assignment-only command (allowed)"

    cmd_tokens = working_tokens[token_idx:]
    executable = cmd_tokens[0]
    args = cmd_tokens[1:]

    if simple.pipeline_in and simple.pipeline_out:
        pipeline_position = 'middle'
    elif simple.pipeline_in:
        pipeline_position = 'last'
    elif simple.pipeline_out:
        pipeline_position = 'first'
    else:
        pipeline_position = 'solo'

    context = CommandContext(
        executable=executable,
        args=args,
        env_vars=env_vars,
        wrappers=wrappers,
        stdin_bound=simple.stdin_redir or simple.pipeline_in,
        stdout_redirected=simple.stdout_redir or simple.pipeline_out,
        stderr_redirected=simple.stderr_redir,
        pipeline_position=pipeline_position
    )
    return context, None


def analyze_command(command: str) -> CommandAnalysis:
    if not command or not command.strip():
        return CommandAnalysis(True, "Empty command (blocking by default)", None, [])

    try:
        simple_commands = _parse_simple_commands(command)
    except CommandParseError as exc:
        return CommandAnalysis(True, f"Malformed command: {exc}", None, [])

    contexts: List[CommandContext] = []
    last_reason: Optional[str] = None

    for simple in simple_commands:
        context, reason = _build_context_from_simple(simple)
        if context is None:
            if reason:
                last_reason = reason
            continue

        contexts.append(context)
        is_interactive, reason_text = is_interactive_command(
            context.executable,
            context.args,
            context.env_vars,
            stdin_bound=context.stdin_bound
        )
        if is_interactive:
            return CommandAnalysis(True, reason_text, context, contexts)

    if contexts:
        primary = contexts[-1]
        return CommandAnalysis(False, f"'{primary.executable}' not in interactive set", primary, contexts)

    fallback_reason = last_reason or "Assignment-only command (allowed)"
    return CommandAnalysis(False, fallback_reason, None, [])


def tokenize_command_words(command: str) -> List[str]:
    """
    Tokenize a shell command into words (excluding redirections and operators).
    Falls back to naive splitting if parsing fails.
    """
    try:
        simple_commands = _parse_simple_commands(command)
    except CommandParseError:
        return command.split()

    tokens: List[str] = []
    for simple in simple_commands:
        tokens.extend(simple.words)
    return tokens


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


def parse_env_assignments(env_tokens: List[str]) -> Dict[str, str]:
    """
    Convert NAME=VALUE tokens into dict.
    Supports NAME+=VALUE by stripping '+='.
    """
    env = {}
    for token in env_tokens:
        if '=' not in token:
            continue
        name, value = token.split('=', 1)
        name = name.rstrip('+')
        env[name] = value
    return env


def is_interactive_command(
    cmd: str,
    args: List[str],
    env_vars: Dict[str, str] = None,
    stdin_bound: bool = False
) -> Tuple[bool, str]:
    """
    Determine if command is interactive based on command name and arguments.
    
    Returns: (is_interactive, reason)
    """
    env_vars = env_vars or {}
    cmd_base = basename(cmd)
    
    # Context-aware overrides for commands typically interactive
    if cmd_base in ALWAYS_INTERACTIVE:
        if cmd_base == 'man':
            pager = _extract_man_pager(args, env_vars)
            if pager and _is_noninteractive_pager(pager):
                # Allow if pager forced to cat-like program
                pass
            else:
                return True, f"'{cmd_base}' uses a pager by default"
        else:
            return True, f"'{cmd_base}' is an editor/pager/monitor"
    
    # Shells - interactive unless -c is present
    if cmd_base in SHELLS:
        if '-c' in args:
            return False, f"Shell '{cmd_base}' with -c (non-interactive)"
        return True, f"Shell '{cmd_base}' without -c"
    
    # Python - interactive unless -c/-m, script, or stdin already bound
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
        
        if stdin_bound:
            return False, "Python reading from stdin (non-interactive)"

        # Bare python → likely REPL
        return True, f"Bare Python (likely REPL)"
    
    # Node.js - interactive unless -e/-p, script, or stdin piping present
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
        
        if stdin_bound:
            return False, "Node reading from stdin (non-interactive)"

        # Bare node → likely REPL
        return True, f"Bare Node (likely REPL)"
    
    # Ruby - interactive unless -e, script, or stdin piping present
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
        
        if stdin_bound:
            return False, "Ruby reading from stdin (non-interactive)"

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
    analysis = analyze_command(cmd_str)
    return analysis.is_interactive, analysis.reason
