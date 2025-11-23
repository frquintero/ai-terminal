from command_parser import parse_command, analyze_command


def test_python_heredoc_non_interactive():
    command = """python3 - <<'PY'
print("hi")
PY"""
    interactive, reason = parse_command(command)
    assert not interactive, f"heredoc python should be non-interactive (reason={reason})"


def test_python_stdin_pipeline_non_interactive():
    command = "printf 'print(42)\\n' | python3 -"
    interactive, reason = parse_command(command)
    assert not interactive, f"stdin pipeline should be non-interactive (reason={reason})"


def test_bare_python_still_interactive():
    interactive, reason = parse_command("python3")
    assert interactive, "bare python without stdin should stay interactive"
    assert "Bare Python" in reason


def test_assignment_only_allowed():
    interactive, reason = parse_command("FOO=bar BAR=1")
    assert not interactive
    assert "Assignment-only" in reason


def test_analyze_command_returns_context():
    analysis = analyze_command("VAR=1 timeout 5 python3 script.py")
    assert not analysis.is_interactive
    assert analysis.primary_context is not None
    assert analysis.primary_context.executable.endswith("python3")
