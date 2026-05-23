"""Tests for web / browser tool schemas and HTML helpers.

Schema tests are always run — they need no network or browser.
Browser integration tests are skipped when Playwright is not installed.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(_SRC))

from tools import (  # noqa: E402
    _BROWSER_TOOL_SCHEMAS,
    _PLAYWRIGHT_AVAILABLE,
    WEB_FETCH_TOOL,
    WEB_SEARCH_TOOL,
    _decode_entities,
    _html_to_text,
    _parse_ddg_html,
)

# ---------------------------------------------------------------------------
# web_fetch schema
# ---------------------------------------------------------------------------


class TestWebFetchToolSchema:
    def test_name(self):
        assert WEB_FETCH_TOOL["name"] == "web_fetch"

    def test_server(self):
        assert WEB_FETCH_TOOL["server"] == "__builtin__"

    def test_description_non_empty(self):
        assert len(WEB_FETCH_TOOL.get("description", "")) > 20

    def test_url_is_required(self):
        required = WEB_FETCH_TOOL["inputSchema"].get("required", [])
        assert "url" in required

    def test_url_property_is_string(self):
        props = WEB_FETCH_TOOL["inputSchema"]["properties"]
        assert "url" in props
        assert props["url"]["type"] == "string"

    def test_max_chars_property_is_integer(self):
        props = WEB_FETCH_TOOL["inputSchema"]["properties"]
        assert "max_chars" in props
        assert props["max_chars"]["type"] == "integer"

    def test_no_additional_properties(self):
        assert WEB_FETCH_TOOL["inputSchema"].get("additionalProperties") is False


# ---------------------------------------------------------------------------
# web_search schema
# ---------------------------------------------------------------------------


class TestWebSearchToolSchema:
    def test_name(self):
        assert WEB_SEARCH_TOOL["name"] == "web_search"

    def test_server(self):
        assert WEB_SEARCH_TOOL["server"] == "__builtin__"

    def test_description_non_empty(self):
        assert len(WEB_SEARCH_TOOL.get("description", "")) > 20

    def test_query_is_required(self):
        required = WEB_SEARCH_TOOL["inputSchema"].get("required", [])
        assert "query" in required

    def test_query_property_is_string(self):
        props = WEB_SEARCH_TOOL["inputSchema"]["properties"]
        assert "query" in props
        assert props["query"]["type"] == "string"

    def test_max_results_property_is_integer(self):
        props = WEB_SEARCH_TOOL["inputSchema"]["properties"]
        assert "max_results" in props
        assert props["max_results"]["type"] == "integer"

    def test_no_additional_properties(self):
        assert WEB_SEARCH_TOOL["inputSchema"].get("additionalProperties") is False


# ---------------------------------------------------------------------------
# Browser tool schemas
# ---------------------------------------------------------------------------


class TestBrowserToolSchemas:
    EXPECTED_NAMES = {
        "browser_navigate",
        "browser_get_text",
        "browser_screenshot",
        "browser_click",
        "browser_fill",
        "browser_evaluate",
    }

    def test_exactly_six_browser_schemas(self):
        assert len(_BROWSER_TOOL_SCHEMAS) == 6

    def test_all_expected_names_present(self):
        names = {s["name"] for s in _BROWSER_TOOL_SCHEMAS}
        assert names == self.EXPECTED_NAMES

    def test_all_have_builtin_server(self):
        for schema in _BROWSER_TOOL_SCHEMAS:
            assert schema["server"] == "__builtin__", (
                f"{schema['name']} must have server='__builtin__'"
            )

    def test_all_have_non_empty_description(self):
        for schema in _BROWSER_TOOL_SCHEMAS:
            assert len(schema.get("description", "")) > 10, (
                f"{schema['name']} description is too short or missing"
            )

    def test_navigate_requires_url(self):
        nav = next(s for s in _BROWSER_TOOL_SCHEMAS if s["name"] == "browser_navigate")
        assert "url" in nav["inputSchema"].get("required", [])

    def test_click_requires_selector(self):
        click = next(s for s in _BROWSER_TOOL_SCHEMAS if s["name"] == "browser_click")
        assert "selector" in click["inputSchema"].get("required", [])

    def test_fill_requires_selector_and_value(self):
        fill = next(s for s in _BROWSER_TOOL_SCHEMAS if s["name"] == "browser_fill")
        required = fill["inputSchema"].get("required", [])
        assert "selector" in required
        assert "value" in required

    def test_evaluate_requires_expression(self):
        ev = next(s for s in _BROWSER_TOOL_SCHEMAS if s["name"] == "browser_evaluate")
        assert "expression" in ev["inputSchema"].get("required", [])

    def test_all_have_input_schema(self):
        for schema in _BROWSER_TOOL_SCHEMAS:
            assert "inputSchema" in schema, f"{schema['name']} missing inputSchema"

    def test_all_input_schemas_are_object_type(self):
        for schema in _BROWSER_TOOL_SCHEMAS:
            assert schema["inputSchema"].get("type") == "object", (
                f"{schema['name']} inputSchema type must be 'object'"
            )


# ---------------------------------------------------------------------------
# _html_to_text
# ---------------------------------------------------------------------------


class TestHtmlToText:
    def test_strips_script_block(self):
        html = "<html><script>alert('xss')</script><p>Safe</p></html>"
        result = _html_to_text(html)
        assert "alert" not in result
        assert "Safe" in result

    def test_strips_style_block(self):
        html = "<html><style>body { color: red; }</style><p>Content</p></html>"
        result = _html_to_text(html)
        assert "color" not in result
        assert "Content" in result

    def test_strips_noscript_block(self):
        html = "<noscript>Please enable JS</noscript><p>Main content</p>"
        result = _html_to_text(html)
        assert "Please enable JS" not in result
        assert "Main content" in result

    def test_strips_head_block(self):
        html = "<html><head><title>Page Title</title></head><body>Body</body></html>"
        result = _html_to_text(html)
        assert "Page Title" not in result
        assert "Body" in result

    def test_block_elements_become_newlines(self):
        html = "<p>Para 1</p><p>Para 2</p>"
        result = _html_to_text(html)
        assert "\n" in result
        assert "Para 1" in result
        assert "Para 2" in result

    def test_headings_become_newlines(self):
        html = "<h1>Heading</h1><p>Body text</p>"
        result = _html_to_text(html)
        assert "Heading" in result
        assert "\n" in result

    def test_nbsp_becomes_space(self):
        html = "<p>Hello&nbsp;World</p>"
        result = _html_to_text(html)
        assert "&nbsp;" not in result
        assert "Hello World" in result

    def test_amp_entity_decoded(self):
        html = "<p>Tom &amp; Jerry</p>"
        result = _html_to_text(html)
        assert "&amp;" not in result
        assert "&" in result

    def test_lt_gt_entities_decoded(self):
        html = "<p>&lt;div&gt;</p>"
        result = _html_to_text(html)
        assert "&lt;" not in result
        assert "<div>" in result

    def test_decimal_entity_decoded(self):
        html = "<p>&#34;hello&#34;</p>"
        result = _html_to_text(html)
        assert '"hello"' in result

    def test_hex_entity_decoded(self):
        html = "<p>&#x27;tick&#x27;</p>"
        result = _html_to_text(html)
        assert "'" in result

    def test_multiple_spaces_collapsed(self):
        html = "<p>Too   many   spaces</p>"
        result = _html_to_text(html)
        assert "  " not in result

    def test_empty_input_returns_empty(self):
        assert _html_to_text("") == ""

    def test_plain_text_passthrough(self):
        result = _html_to_text("No tags here at all")
        assert "No tags here at all" in result

    def test_no_trailing_leading_whitespace(self):
        html = "   <p>Hello</p>   "
        result = _html_to_text(html)
        assert result == result.strip()


# ---------------------------------------------------------------------------
# _decode_entities
# ---------------------------------------------------------------------------


class TestDecodeEntities:
    def test_amp(self):
        assert _decode_entities("Tom &amp; Jerry") == "Tom & Jerry"

    def test_lt_gt(self):
        assert _decode_entities("&lt;div&gt;") == "<div>"

    def test_quot(self):
        assert _decode_entities("&quot;hello&quot;") == '"hello"'

    def test_apos(self):
        assert _decode_entities("it&apos;s") == "it's"

    def test_decimal_entity(self):
        assert _decode_entities("&#65;") == "A"

    def test_hex_entity(self):
        assert _decode_entities("&#x41;") == "A"

    def test_nbsp(self):
        assert _decode_entities("hello&nbsp;world") == "hello world"

    def test_no_entities(self):
        text = "plain text"
        assert _decode_entities(text) == text

    def test_empty_string(self):
        assert _decode_entities("") == ""


# ---------------------------------------------------------------------------
# _parse_ddg_html
# ---------------------------------------------------------------------------

_SAMPLE_DDG_HTML = """\
<html><body>
<a class="result__a" href="https://example.com/page1">First Result</a>
<span class="result__snippet">This is snippet one.</span>
<a class="result__a" href="https://example.com/page2">Second &amp; Third</a>
<span class="result__snippet">Snippet two with &amp; entity.</span>
</body></html>
"""


class TestParseDdgHtml:
    def test_extracts_two_results(self):
        results = _parse_ddg_html(_SAMPLE_DDG_HTML)
        assert len(results) == 2

    def test_each_result_has_required_keys(self):
        for r in _parse_ddg_html(_SAMPLE_DDG_HTML):
            assert "title" in r
            assert "url" in r
            assert "snippet" in r

    def test_first_result_url(self):
        results = _parse_ddg_html(_SAMPLE_DDG_HTML)
        assert results[0]["url"] == "https://example.com/page1"

    def test_first_result_title(self):
        results = _parse_ddg_html(_SAMPLE_DDG_HTML)
        assert results[0]["title"] == "First Result"

    def test_first_result_snippet(self):
        results = _parse_ddg_html(_SAMPLE_DDG_HTML)
        assert "snippet one" in results[0]["snippet"]

    def test_second_title_decodes_entities(self):
        results = _parse_ddg_html(_SAMPLE_DDG_HTML)
        assert "&amp;" not in results[1]["title"]
        assert "&" in results[1]["title"]

    def test_second_snippet_decodes_entities(self):
        results = _parse_ddg_html(_SAMPLE_DDG_HTML)
        assert "&amp;" not in results[1]["snippet"]
        assert "&" in results[1]["snippet"]

    def test_max_results_limits_output(self):
        results = _parse_ddg_html(_SAMPLE_DDG_HTML, max_results=1)
        assert len(results) <= 1

    def test_empty_html_returns_empty_list(self):
        assert _parse_ddg_html("") == []

    def test_html_without_results_returns_empty_list(self):
        assert _parse_ddg_html("<html><body><p>No results here</p></body></html>") == []


# ---------------------------------------------------------------------------
# _PLAYWRIGHT_AVAILABLE flag
# ---------------------------------------------------------------------------


class TestPlaywrightAvailability:
    def test_flag_is_bool(self):
        assert isinstance(_PLAYWRIGHT_AVAILABLE, bool)

    @pytest.mark.skipif(not _PLAYWRIGHT_AVAILABLE, reason="playwright not installed")
    def test_playwright_importable_when_flag_true(self):
        import playwright  # noqa: F401
