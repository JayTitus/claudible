"""Tests for the speech filter."""

from claudible.hooks.filter import extract_speakable


def test_pure_code_block_returns_none():
    text = "```python\nprint('hello')\n```"
    assert extract_speakable(text) is None


def test_conversational_answer():
    text = "Yes, you can do that by passing the --verbose flag to the CLI."
    result = extract_speakable(text)
    assert result is not None
    assert "verbose" in result


def test_question_from_claude():
    text = "Would you like me to create that file?"
    result = extract_speakable(text)
    assert result is not None
    assert result.endswith("?")


def test_mixed_code_and_prose():
    text = """Here's how to fix it:

```python
def hello():
    print("world")
```

Let me know if that works for you."""
    result = extract_speakable(text)
    assert result is not None
    assert "fix it" in result
    assert "Let me know" in result
    assert "print" not in result


def test_command_output_skipped():
    text = """$ git status
On branch main
nothing to commit, working tree clean"""
    assert extract_speakable(text) is None


def test_file_listing_skipped():
    text = """/home/user/project/src/main.py
/home/user/project/src/utils.py
/home/user/project/README.md"""
    assert extract_speakable(text) is None


def test_table_skipped():
    text = """| Name | Value |
|------|-------|
| foo  | bar   |"""
    assert extract_speakable(text) is None


def test_short_status_skipped():
    text = "Done."
    assert extract_speakable(text) is None


def test_short_question_kept():
    text = "Should I proceed?"
    result = extract_speakable(text)
    assert result is not None


def test_prose_with_file_paths_mixed():
    text = """I've updated the configuration file. The changes look good and the tests pass.

Do you want me to commit this?"""
    result = extract_speakable(text)
    assert result is not None
    assert "commit" in result
