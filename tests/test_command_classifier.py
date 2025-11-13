from orchestrator.command_classifier import (
    ClassificationResult,
    QueryRoute,
    classify_query,
    is_interactive_command,
    is_shell_command,
    is_simple_chat_query,
)


def test_shell_detection():
    assert is_shell_command("ls -la")
    assert not is_shell_command("Explain git rebase")


def test_interactive_detection():
    assert is_interactive_command("vim file.txt")
    assert not is_interactive_command("vim -c ':wq'")


def test_chat_detection():
    assert is_simple_chat_query("What is Python?")
    assert not is_simple_chat_query("grep TODO -r src")


def test_classification_prefers_shell_then_chat():
    result = classify_query("ls")
    assert result.route == QueryRoute.SHELL
    assert isinstance(result, ClassificationResult)

    result = classify_query("What is AI?")
    assert result.route == QueryRoute.CHAT

    result = classify_query("Please audit src/")
    assert result.route == QueryRoute.PLANNER
