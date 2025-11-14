from ui_formatter import (
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
