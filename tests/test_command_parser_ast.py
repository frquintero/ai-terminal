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
    assert "Python requires -c" in reason


def test_assignment_only_allowed():
    interactive, reason = parse_command("FOO=bar BAR=1")
    assert not interactive
    assert "Assignment-only" in reason


def test_analyze_command_returns_context():
    analysis = analyze_command("VAR=1 timeout 5 python3 script.py")
    assert not analysis.is_interactive
    assert analysis.primary_context is not None
    assert analysis.primary_context.executable.endswith("python3")


def test_shell_requires_script_or_flag():
    interactive, reason = parse_command("bash")
    assert interactive
    assert "Shell requires -c" in reason


def test_shell_with_dash_c_allowed():
    interactive, reason = parse_command("bash -c 'echo hi'")
    assert not interactive
    assert "-c" in reason


def test_node_eval_allows_non_interactive():
    interactive, reason = parse_command("node --eval '1+1'")
    assert not interactive
    assert "--eval" in reason


def test_node_interactive_flag_blocks():
    interactive, reason = parse_command("node -i")
    assert interactive
    assert "flag -i" in reason


def test_ruby_extensionless_script_allowed():
    interactive, reason = parse_command("ruby scripts/run_task")
    assert not interactive
    assert "script" in reason


def test_man_allows_cat_pager():
    interactive, reason = parse_command("MANPAGER=cat man printf")
    assert not interactive
    assert "pager forced" in reason


def test_perl_dash_e_allowed():
    interactive, reason = parse_command("perl -e 'print 1'")
    assert not interactive
    assert "perl" in reason


def test_php_script_allowed():
    interactive, reason = parse_command("php app/artisan")
    assert not interactive
    assert "script" in reason


def test_mysql_without_execute_blocks():
    interactive, reason = parse_command("mysql")
    assert interactive
    assert "mysql requires" in reason


def test_mysql_with_execute_allowed():
    interactive, reason = parse_command('mysql -e "select 1;"')
    assert not interactive
    assert "-e" in reason


def test_psql_dash_c_allowed():
    interactive, reason = parse_command("psql -c 'select 1;'")
    assert not interactive
    assert "-c" in reason


def test_redis_cli_eval_allowed():
    interactive, reason = parse_command("redis-cli --eval script.lua key1 key2")
    assert not interactive
    assert "--eval" in reason


def test_mongo_eval_allowed():
    interactive, reason = parse_command("mongo --eval 'db.stats()'")
    assert not interactive
    assert "--eval" in reason


def test_sqlite_blocks_without_sql():
    interactive, reason = parse_command("sqlite3 my.db")
    assert interactive
    assert "sqlite3 requires" in reason


def test_sqlite_allows_inline_sql():
    interactive, reason = parse_command("sqlite3 my.db 'select 1;'")
    assert not interactive
    assert "inline SQL" in reason


def test_sqlite_allows_stdin_pipeline():
    command = "printf 'select 1;\\n' | sqlite3 my.db"
    interactive, reason = parse_command(command)
    assert not interactive
    assert "stdin" in reason


def test_sqlite_cmd_without_batch_blocks():
    interactive, reason = parse_command("sqlite3 my.db -cmd '.mode box'")
    assert interactive
    assert "sqlite3 requires" in reason
