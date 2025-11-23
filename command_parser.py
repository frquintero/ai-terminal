"""
Robust command parser for interactive command detection.

Replaces brittle option tables with minimal, stable wrapper handlers.
Philosophy: Fail-safe by blocking when ambiguous.
"""

import os
from collections import deque
from dataclasses import dataclass, field
from typing import Tuple, List, Set, Dict, Optional


# ============================================================================
# Helper Functions
# ============================================================================

def is_assignment(token: str) -> bool:
    """Check if token is environment variable assignment (NAME=value or NAME+=value)"""
    if '=' not in token:
        return False
    name, _ = token.split('=', 1)
    if name.endswith('+'):
        name = name[:-1]
    if not name:
        return False
    first = name[0]
    if not (first.isalpha() or first == '_'):
        return False
    for char in name[1:]:
        if not (char.isalnum() or char == '_'):
            return False
    return True


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
    return bool(normalized and normalized in NONINTERACTIVE_PAGERS)


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
        verdict = POLICY_ENGINE.evaluate(context)
        last_reason = verdict.reason
        if verdict.blocked:
            return CommandAnalysis(True, verdict.reason, context, contexts)

    if contexts:
        primary = contexts[-1]
        return CommandAnalysis(False, last_reason or f"'{primary.executable}' allowed by policy", primary, contexts)

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
# Policy-Driven Interactive Command Detection
# ============================================================================
@dataclass(frozen=True)
class ExecutablePolicy:
    allow_flags: Tuple[str, ...] = tuple()
    allow_flag_prefixes: Tuple[str, ...] = tuple()
    allow_short_flags: Tuple[str, ...] = tuple()
    block_flags: Tuple[str, ...] = tuple()
    block_flag_prefixes: Tuple[str, ...] = tuple()
    block_short_flags: Tuple[str, ...] = tuple()
    script_extensions: Tuple[str, ...] = tuple()
    allow_extensionless_scripts: bool = False
    allow_any_script_token: bool = False
    allow_stdin: bool = False
    allow_dash_stdin: bool = False
    default_block_reason: str = ""


@dataclass(frozen=True)
class PolicyVerdict:
    blocked: bool
    reason: str


def _first_non_option_arg(args: List[str]) -> Optional[str]:
    """Return first positional argument after option parsing rules."""
    idx = 0
    while idx < len(args):
        token = args[idx]
        if token == '--':
            idx += 1
            break
        if token.startswith('-') and token != '-':
            idx += 1
            continue
        return token
    if idx < len(args):
        return args[idx]
    return None


def _token_contains_short_flag(token: str, flag: str) -> bool:
    return token.startswith('-') and not token.startswith('--') and flag in token[1:]


def _matches_extension(token: str, extensions: Tuple[str, ...]) -> bool:
    if not extensions:
        return False
    _, ext = os.path.splitext(token)
    return ext in extensions


def _sqlite_positional_args(args: List[str]) -> List[str]:
    """
    Return sqlite3 positional arguments while accounting for options that consume values.
    """
    positional: List[str] = []
    idx = 0
    options_with_counts = {
        '-cmd': 1, '--cmd': 1,
        '-init': 1, '--init': 1,
        '-separator': 1, '--separator': 1,
        '-newline': 1, '--newline': 1,
        '-nullvalue': 1, '--nullvalue': 1,
        '-lookaside': 2, '--lookaside': 2,
        '-pagecache': 2, '--pagecache': 2,
        '-maxsize': 1, '--maxsize': 1,
        '-mmap': 1, '--mmap': 1,
        '-vfs': 1, '--vfs': 1,
    }

    def _matches_long_with_value(token: str) -> Optional[str]:
        if not token.startswith('--'):
            return None
        if '=' not in token:
            return None
        candidate = token.split('=', 1)[0]
        return candidate if candidate in options_with_counts else None

    while idx < len(args):
        token = args[idx]
        if token == '--':
            idx += 1
            positional.extend(args[idx:])
            break

        matched_long = _matches_long_with_value(token)
        if matched_long:
            idx += 1
            continue

        if token in options_with_counts:
            consume = options_with_counts[token]
            idx += 1 + consume
            continue

        if token.startswith('-') and token != '-':
            idx += 1
            continue

        positional.append(token)
        idx += 1

    return positional


class PolicyEngine:
    """Deterministic command policy evaluator."""

    def __init__(self) -> None:
        self._always_block = {
            'vim', 'vi', 'nvim', 'emacs',
            'nano', 'ed', 'joe',
            'less', 'more',
            'top', 'htop', 'iotop',
            'tmux', 'screen',
            'ssh', 'telnet',
            'irb',
        }
        self._man_allowed_pagers = NONINTERACTIVE_PAGERS
        self._policies: Dict[str, ExecutablePolicy] = {}
        self._special_handlers = {
            'man': self._handle_man,
            'sqlite3': self._handle_sqlite3,
        }
        self._install_policies()

    def _set_policy(self, names: Tuple[str, ...], policy: ExecutablePolicy) -> None:
        for name in names:
            self._policies[name] = policy

    def _install_policies(self) -> None:
        python_policy = ExecutablePolicy(
            allow_flags=('-c', '-m'),
            allow_short_flags=(),
            block_flags=('-i',),
            block_short_flags=('i',),
            script_extensions=('.py', '.pyw'),
            allow_extensionless_scripts=True,
            allow_stdin=True,
            allow_dash_stdin=True,
            default_block_reason="Python requires -c/-m/script/stdin for non-interactive execution"
        )
        self._set_policy(
            ('python', 'python2', 'python3', 'ipython', 'pypy', 'pypy3'),
            python_policy
        )

        node_policy = ExecutablePolicy(
            allow_flags=('-e', '--eval', '-p', '--print'),
            allow_flag_prefixes=('--eval=', '--print='),
            allow_short_flags=('e', 'p'),
            block_flags=('--interactive',),
            block_short_flags=('i',),
            script_extensions=('.js', '.mjs', '.cjs', '.jsx', '.ts', '.tsx'),
            allow_extensionless_scripts=True,
            allow_stdin=True,
            allow_dash_stdin=True,
            default_block_reason="Node.js requires -e/-p/script/stdin for non-interactive execution"
        )
        self._set_policy(('node', 'nodejs'), node_policy)

        ruby_policy = ExecutablePolicy(
            allow_flags=('-e',),
            allow_short_flags=('e',),
            script_extensions=('.rb',),
            allow_extensionless_scripts=True,
            allow_stdin=True,
            allow_dash_stdin=True,
            default_block_reason="Ruby requires -e/script/stdin for non-interactive execution"
        )
        self._set_policy(('ruby',), ruby_policy)

        shell_policy = ExecutablePolicy(
            allow_flags=('-c',),
            script_extensions=('.sh', '.bash', '.zsh', '.ksh'),
            allow_extensionless_scripts=True,
            allow_any_script_token=True,
            allow_stdin=True,
            allow_dash_stdin=True,
            default_block_reason="Shell requires -c/script/stdin for non-interactive execution"
        )
        self._set_policy(
            ('bash', 'sh', 'zsh', 'fish', 'dash', 'ksh'),
            shell_policy
        )

        perl_policy = ExecutablePolicy(
            allow_flags=('-e', '-E'),
            allow_short_flags=('e', 'E'),
            script_extensions=('.pl', '.pm', '.perl'),
            allow_extensionless_scripts=True,
            allow_stdin=True,
            allow_dash_stdin=True,
            default_block_reason="Perl requires -e/script/stdin for non-interactive execution"
        )
        self._set_policy(('perl', 'perl5'), perl_policy)

        php_policy = ExecutablePolicy(
            allow_flags=('-r',),
            allow_short_flags=('r',),
            script_extensions=('.php', '.phtml', '.phpt'),
            allow_extensionless_scripts=True,
            allow_stdin=True,
            allow_dash_stdin=True,
            default_block_reason="PHP requires -r/script/stdin for non-interactive execution"
        )
        self._set_policy(('php', 'php8', 'php7', 'php-cli'), php_policy)

        lua_policy = ExecutablePolicy(
            allow_flags=('-e',),
            allow_short_flags=('e',),
            script_extensions=('.lua',),
            allow_extensionless_scripts=True,
            allow_stdin=True,
            allow_dash_stdin=True,
            default_block_reason="Lua requires -e/script/stdin for non-interactive execution"
        )
        self._set_policy(('lua', 'lua5.1', 'lua5.2', 'lua5.3', 'lua5.4', 'luajit'), lua_policy)

        mysql_policy = ExecutablePolicy(
            allow_flags=('-e', '--execute', '--init-command'),
            allow_flag_prefixes=('--execute=', '--init-command='),
            allow_stdin=True,
            allow_dash_stdin=True,
            default_block_reason="mysql requires -e/--execute or stdin for non-interactive execution"
        )
        self._set_policy(('mysql',), mysql_policy)

        psql_policy = ExecutablePolicy(
            allow_flags=('-c', '--command', '-f', '--file'),
            allow_flag_prefixes=('--command=', '--file='),
            allow_short_flags=('c', 'f'),
            allow_stdin=True,
            allow_dash_stdin=True,
            default_block_reason="psql requires -c/-f/STDIN for non-interactive execution"
        )
        self._set_policy(('psql',), psql_policy)

        redis_policy = ExecutablePolicy(
            allow_flags=('--eval', '--pipe'),
            allow_flag_prefixes=('--eval=',),
            allow_short_flags=('x',),
            script_extensions=('.lua',),
            allow_stdin=True,
            allow_dash_stdin=True,
            default_block_reason="redis-cli requires --eval/-x/STDIN for non-interactive execution"
        )
        self._set_policy(('redis-cli',), redis_policy)

        mongo_policy = ExecutablePolicy(
            allow_flags=('--eval',),
            allow_flag_prefixes=('--eval=',),
            script_extensions=('.js',),
            allow_stdin=True,
            allow_dash_stdin=True,
            default_block_reason="mongo requires --eval/script/STDIN for non-interactive execution"
        )
        self._set_policy(('mongo', 'mongosh'), mongo_policy)

    def evaluate(self, context: CommandContext) -> PolicyVerdict:
        cmd = basename(context.executable)
        if cmd in self._always_block:
            return PolicyVerdict(True, f"'{cmd}' is restricted to run_interactive")

        handler = self._special_handlers.get(cmd)
        if handler:
            return handler(context)

        policy = self._policies.get(cmd)
        if policy:
            return self._evaluate_policy(cmd, context, policy)

        return PolicyVerdict(False, f"'{cmd}' allowed (no interactive policy)")

    def _handle_man(self, context: CommandContext) -> PolicyVerdict:
        pager = _extract_man_pager(context.args, context.env_vars)
        if pager:
            normalized = pager.strip().lower()
            if normalized in self._man_allowed_pagers:
                return PolicyVerdict(False, f"'man' pager forced to '{normalized}'")
        return PolicyVerdict(True, "'man' requires a pager (run_interactive only)")

    def _handle_sqlite3(self, context: CommandContext) -> PolicyVerdict:
        args = context.args
        if any(flag in args for flag in ('-batch', '--batch')):
            return PolicyVerdict(False, "'sqlite3' allowed via -batch flag")
        if context.stdin_bound:
            return PolicyVerdict(False, "'sqlite3' allowed (stdin already bound)")

        positional = _sqlite_positional_args(args)
        if len(positional) >= 2:
            return PolicyVerdict(False, "'sqlite3' allowed via inline SQL argument")

        return PolicyVerdict(True, "sqlite3 requires SQL input (-batch/SQL arg/stdin)")

    def _evaluate_policy(
        self,
        cmd: str,
        context: CommandContext,
        policy: ExecutablePolicy
    ) -> PolicyVerdict:
        args = context.args
        matched_block = self._match_flag(args, policy.block_flags, policy.block_flag_prefixes, policy.block_short_flags)
        if matched_block:
            return PolicyVerdict(True, f"'{cmd}' blocked because flag {matched_block} forces interactivity")

        matched_allow = self._match_flag(args, policy.allow_flags, policy.allow_flag_prefixes, policy.allow_short_flags)
        if matched_allow:
            return PolicyVerdict(False, f"'{cmd}' allowed via flag {matched_allow}")

        script_token = _first_non_option_arg(args)
        if script_token:
            if script_token == '-' and policy.allow_dash_stdin and context.stdin_bound:
                return PolicyVerdict(False, f"'{cmd}' reading script from stdin via '-'")
            if script_token != '-':
                if policy.allow_any_script_token:
                    return PolicyVerdict(False, f"'{cmd}' script argument '{script_token}'")
                if _matches_extension(script_token, policy.script_extensions):
                    return PolicyVerdict(False, f"'{cmd}' script '{script_token}'")
                if policy.allow_extensionless_scripts:
                    base = basename(script_token).lstrip('.')
                    if base and '.' not in base:
                        return PolicyVerdict(False, f"'{cmd}' script '{script_token}' (extensionless)")

        if context.stdin_bound and policy.allow_stdin:
            return PolicyVerdict(False, f"'{cmd}' allowed (stdin already bound)")

        if policy.default_block_reason:
            return PolicyVerdict(True, f"{policy.default_block_reason} (command: '{cmd}')")

        return PolicyVerdict(False, f"'{cmd}' allowed by default")

    def _match_flag(
        self,
        args: List[str],
        flags: Tuple[str, ...],
        prefixes: Tuple[str, ...] = tuple(),
        short_flags: Tuple[str, ...] = tuple()
    ) -> Optional[str]:
        if not args:
            return None
        stop_scanning = False
        for token in args:
            if token == '--':
                stop_scanning = True
                continue
            if stop_scanning:
                continue
            if token in flags:
                return token
            for prefix in prefixes:
                if token.startswith(prefix):
                    return prefix
            for short_flag in short_flags:
                if _token_contains_short_flag(token, short_flag):
                    return f"-{short_flag}"
        return None


POLICY_ENGINE = PolicyEngine()


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
