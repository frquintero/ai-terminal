import pytest

from orchestrator.output_parser import OutputParser, OutputParserError


def test_parse_mixed_types_preserves_raw_block():
    parser = OutputParser()
    stdout = "main.py\napp.py\ncount: 42\npi=3.14\n"
    raw_stdout = "RAW\n" + stdout
    output_format = {
        "files": "list",
        "count": "int",
        "pi": "float",
        "text": "str",
        "raw_block": "raw",
        "table_block": "table"
    }

    parsed, rendered = parser.parse(output_format, stdout, raw_stdout)

    assert parsed["files"] == ["main.py", "app.py", "count: 42", "pi=3.14"]
    assert parsed["count"] == 42
    assert parsed["pi"] == pytest.approx(3.14)
    assert parsed["text"].startswith("main.py")
    assert parsed["raw_block"].startswith("RAW")
    assert parsed["table_block"].startswith("RAW")
    assert rendered["files"] == "main.py, app.py, count: 42, pi=3.14"
    assert rendered["count"] == "42"
    assert rendered["raw_block"].startswith("RAW")


def test_parse_json_payload():
    parser = OutputParser()
    parsed, rendered = parser.parse({"data": "json"}, '{"files": ["a.py", "b.py"]}')

    assert parsed["data"]["files"] == ["a.py", "b.py"]
    assert rendered["data"].startswith("{")


def test_parse_int_failure_raises():
    parser = OutputParser()
    with pytest.raises(OutputParserError):
        parser.parse({"count": "int"}, "no numbers present")
