from ui_formatter import (
    UIFormatter,
    infer_language_from_path,
    is_markdown_file,
    truncate_text,
    try_pretty_json,
)


def test_try_pretty_json_handles_small_payload():
    pretty = try_pretty_json('{"city":"Tokyo","temp":18}')
    assert pretty is not None
    assert '"city": "Tokyo"' in pretty


def test_try_pretty_json_rejects_invalid():
    assert try_pretty_json("not-json") is None
    assert try_pretty_json(" " * 10) is None


def test_truncate_text_limits_lines_and_chars():
    payload = "\n".join(str(i) for i in range(10))
    truncated, was_truncated = truncate_text(payload, max_chars=5, max_lines=3)
    assert was_truncated is True
    assert truncated.count("\n") <= 2
    assert truncated.startswith("0")


def test_infer_language_from_path_respects_extension():
    assert infer_language_from_path("src/app.py") == "python"
    assert infer_language_from_path("notes.txt") is None
    assert infer_language_from_path(None) is None


def test_is_markdown_file_case_insensitive():
    assert is_markdown_file("README.MD") is True
    assert is_markdown_file("notes.txt") is False


def test_render_output_placeholder_inlines_scalars():
    formatter = UIFormatter()
    execution_result = {
        "output_values": {"count": "42"},
        "output_value_types": {"count": "int"},
        "output_value_sources": {}
    }
    rendered_blocks = set()

    inline_value, blocks = formatter._render_output_placeholder(
        key="count",
        execution_result=execution_result,
        rendered_blocks=rendered_blocks
    )

    assert inline_value == "42"
    assert blocks == []
    assert rendered_blocks == set()


def test_render_output_placeholder_emits_output_block_for_lists():
    formatter = UIFormatter()
    execution_result = {
        "output_values": {"files": "alpha.txt, beta.txt"},
        "output_value_types": {"files": "list"},
        "output_value_sources": {
            "files": {
                "tool_name": "run_command",
                "command": "find . -name '*.txt'",
                "stdout": "alpha.txt\nbeta.txt\n",
                "raw_stdout": "alpha.txt\nbeta.txt\n",
                "tool_args": {}
            }
        }
    }
    rendered_blocks = set()

    inline_value, blocks = formatter._render_output_placeholder(
        key="files",
        execution_result=execution_result,
        rendered_blocks=rendered_blocks
    )

    assert inline_value is None
    assert len(blocks) == 1
    assert "```output" in blocks[0].markup
    assert "alpha.txt" in blocks[0].markup
    assert "beta.txt" in blocks[0].markup
    assert "files" in rendered_blocks


def test_render_output_placeholder_skips_block_for_no_output():
    formatter = UIFormatter()
    fallback = "Tool run_command (command: find . -name '*.bat') completed with no output."
    execution_result = {
        "output_values": {"bat_files": fallback},
        "output_value_types": {"bat_files": "list"},
        "output_value_sources": {
            "bat_files": {"no_output": True}
        }
    }
    rendered_blocks = set()

    inline_value, blocks = formatter._render_output_placeholder(
        key="bat_files",
        execution_result=execution_result,
        rendered_blocks=rendered_blocks
    )

    assert inline_value == fallback
    assert blocks == []


def test_render_output_placeholder_fences_multiline_str_stdout():
    formatter = UIFormatter()
    execution_result = {
        "output_values": {"log": "first line\nsecond line\n"},
        "output_value_types": {"log": "str"},
        "output_value_sources": {
            "log": {
                "tool_name": "run_command",
                "command": "echo -e 'first line\\nsecond line'",
                "stdout": "first line\nsecond line\n",
                "raw_stdout": "first line\nsecond line\n",
                "tool_args": {}
            }
        }
    }
    rendered_blocks = set()

    inline_value, blocks = formatter._render_output_placeholder(
        key="log",
        execution_result=execution_result,
        rendered_blocks=rendered_blocks
    )

    assert inline_value is None
    assert len(blocks) == 1
    assert "```output" in blocks[0].markup
    assert "first line" in blocks[0].markup
    assert "second line" in blocks[0].markup
    assert "log" in rendered_blocks
