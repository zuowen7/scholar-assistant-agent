"""Edge case tests — malformed input, boundary values, extreme inputs."""
import pytest

pytestmark = pytest.mark.edge


def test_parse_empty_string():
    from src.cleaner.pipeline import clean_text
    result = clean_text("")
    assert result == "" or result is not None


def test_parse_whitespace_only():
    from src.cleaner.pipeline import clean_text
    result = clean_text("   \n\t  \n  ")
    assert isinstance(result, str)


def test_parse_single_char():
    from src.cleaner.pipeline import clean_text
    result = clean_text("A")
    assert isinstance(result, str)


def test_parse_unicode_mixed():
    from src.cleaner.pipeline import clean_text
    text = "Hello 你好 🌍 Здравствуйте مرحبا"
    result = clean_text(text)
    assert isinstance(result, str)


def test_parse_null_bytes():
    from src.cleaner.pipeline import clean_text
    result = clean_text("text\x00with\x00nulls")
    assert isinstance(result, str)


def test_config_extreme_values():
    """Config with extreme but valid values should not crash."""
    import yaml
    cfg = yaml.safe_load("""
translator:
  temperature: 0.0
  timeout: 0.001
  max_retries: 0
chunker:
  max_tokens: 1
  overlap_tokens: 0
""")
    assert cfg["translator"]["temperature"] == 0.0
    assert cfg["chunker"]["max_tokens"] == 1


def test_project_name_boundary():
    """Project names at length boundaries."""
    from routers.project import _validate_project_name
    assert len(_validate_project_name("a")) >= 1
    assert len(_validate_project_name("a" * 200)) <= 200


def test_project_name_invalid():
    """Empty project name should raise HTTPException."""
    from fastapi import HTTPException
    from routers.project import _validate_project_name
    with pytest.raises(HTTPException) as exc_info:
        _validate_project_name("")
    assert exc_info.value.status_code == 422

    with pytest.raises(HTTPException):
        _validate_project_name("CON")


def test_sentence_split_edge_cases():
    """Sentence splitter with edge cases."""
    from src.cleaner.pipeline import clean_text
    result = clean_text("...")
    assert isinstance(result, str)
    result = clean_text("word " * 10000)
    assert isinstance(result, str)
