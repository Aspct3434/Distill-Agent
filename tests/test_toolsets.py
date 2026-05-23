"""Tests for src/toolsets.py — toolset routing and filtering."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(_SRC))

from toolsets import (  # noqa: E402
    TOOLSET_NAMES,
    TOOLSETS,
    filter_tools_by_toolset,
)

# ---------------------------------------------------------------------------
# Toolset name coverage
# ---------------------------------------------------------------------------


class TestToolsetNames:
    EXPECTED = {"all", "research", "coding", "web", "data", "ops"}

    def test_expected_names_present(self):
        assert self.EXPECTED <= TOOLSET_NAMES

    def test_all_names_have_toolset_entry(self):
        missing = TOOLSET_NAMES - set(TOOLSETS)
        assert not missing, f"TOOLSET_NAMES entries with no TOOLSETS entry: {missing}"

    def test_toolset_names_is_frozenset(self):
        assert isinstance(TOOLSET_NAMES, frozenset)


# ---------------------------------------------------------------------------
# Always-available tools
# ---------------------------------------------------------------------------


class TestAlwaysAvailableTools:
    ALWAYS_REQUIRED = {"set_task_contract", "update_plan"}

    @pytest.mark.parametrize("name", sorted(TOOLSET_NAMES))
    def test_control_tools_in_every_toolset(self, name: str):
        toolset = TOOLSETS[name]
        missing = self.ALWAYS_REQUIRED - toolset
        assert not missing, (
            f"Toolset {name!r} is missing always-required tools: {missing}. "
            "The agent needs these to set its contract and update its plan."
        )


# ---------------------------------------------------------------------------
# Toolset isolation
# ---------------------------------------------------------------------------


class TestToolsetIsolation:
    def test_research_has_no_exec_tools(self):
        assert "execute_terminal_command" not in TOOLSETS["research"]
        assert "execute_background_service" not in TOOLSETS["research"]

    def test_research_has_no_file_write_tools(self):
        assert "write_text_file" not in TOOLSETS["research"]
        assert "write_file" not in TOOLSETS["research"]

    def test_research_has_no_data_write_tools(self):
        assert "create_table" not in TOOLSETS["research"]
        assert "write_query" not in TOOLSETS["research"]

    def test_research_has_web_tools(self):
        assert "web_search" in TOOLSETS["research"]
        assert "web_fetch" in TOOLSETS["research"]
        assert "browser_navigate" in TOOLSETS["research"]

    def test_coding_has_exec_tools(self):
        assert "execute_terminal_command" in TOOLSETS["coding"]
        assert "execute_background_service" in TOOLSETS["coding"]

    def test_coding_has_file_write_tools(self):
        assert "write_text_file" in TOOLSETS["coding"]

    def test_data_has_no_browser_tools(self):
        assert "browser_navigate" not in TOOLSETS["data"]

    def test_ops_has_no_browser_tools(self):
        assert "browser_navigate" not in TOOLSETS["ops"]

    def test_all_is_superset_of_every_toolset(self):
        all_tools = TOOLSETS["all"]
        for name, toolset in TOOLSETS.items():
            if name == "all":
                continue
            assert toolset <= all_tools, (
                f"Toolset {name!r} has tools not in 'all': {toolset - all_tools}"
            )

    def test_web_has_browser_tools(self):
        assert "browser_navigate" in TOOLSETS["web"]
        assert "browser_get_text" in TOOLSETS["web"]

    def test_web_has_no_exec_tools(self):
        assert "execute_terminal_command" not in TOOLSETS["web"]
        assert "execute_background_service" not in TOOLSETS["web"]

    def test_ops_has_exec_tools(self):
        assert "execute_terminal_command" in TOOLSETS["ops"]
        assert "execute_background_service" in TOOLSETS["ops"]

    def test_data_has_sqlite_write_tools(self):
        assert "create_table" in TOOLSETS["data"]
        assert "write_query" in TOOLSETS["data"]

    def test_data_has_exec_tools(self):
        assert "execute_terminal_command" in TOOLSETS["data"]


# ---------------------------------------------------------------------------
# filter_tools_by_toolset
# ---------------------------------------------------------------------------

_FAKE_TOOLS = [
    {"name": "web_search"},
    {"name": "web_fetch"},
    {"name": "browser_navigate"},
    {"name": "set_task_contract"},
    {"name": "update_plan"},
    {"name": "execute_terminal_command"},
    {"name": "execute_background_service"},
    {"name": "write_text_file"},
    {"name": "read_query"},
    {"name": "create_table"},
    {"name": "delegate_task"},
    {"name": "get_system_environment"},
]


class TestFilterToolsByToolset:
    def test_all_returns_all_known_tools(self):
        result = filter_tools_by_toolset(_FAKE_TOOLS, "all")
        expected_names = {t["name"] for t in _FAKE_TOOLS if t["name"] in TOOLSETS["all"]}
        result_names = {t["name"] for t in result}
        assert result_names == expected_names

    def test_research_excludes_exec_tools(self):
        result = filter_tools_by_toolset(_FAKE_TOOLS, "research")
        names = {t["name"] for t in result}
        assert "execute_terminal_command" not in names
        assert "execute_background_service" not in names

    def test_research_includes_web_tools(self):
        result = filter_tools_by_toolset(_FAKE_TOOLS, "research")
        names = {t["name"] for t in result}
        assert "web_search" in names
        assert "web_fetch" in names

    def test_research_includes_control_tools(self):
        result = filter_tools_by_toolset(_FAKE_TOOLS, "research")
        names = {t["name"] for t in result}
        assert "set_task_contract" in names
        assert "update_plan" in names

    def test_unknown_name_falls_back_to_all(self):
        result = filter_tools_by_toolset(_FAKE_TOOLS, "nonexistent_toolset")
        all_result = filter_tools_by_toolset(_FAKE_TOOLS, "all")
        assert {t["name"] for t in result} == {t["name"] for t in all_result}

    def test_preserves_original_tool_objects(self):
        result = filter_tools_by_toolset(_FAKE_TOOLS, "research")
        for tool in result:
            assert tool in _FAKE_TOOLS, "filter must return references, not copies"

    def test_empty_input_returns_empty(self):
        result = filter_tools_by_toolset([], "coding")
        assert result == []

    def test_tools_without_name_key_are_excluded(self):
        tools = [{"description": "no name here"}, {"name": "web_search"}]
        result = filter_tools_by_toolset(tools, "research")
        assert len(result) == 1
        assert result[0]["name"] == "web_search"

    def test_coding_has_exec_and_file_write(self):
        result = filter_tools_by_toolset(_FAKE_TOOLS, "coding")
        names = {t["name"] for t in result}
        assert "execute_terminal_command" in names
        assert "write_text_file" in names

    def test_data_has_create_table_but_not_browser(self):
        result = filter_tools_by_toolset(_FAKE_TOOLS, "data")
        names = {t["name"] for t in result}
        assert "create_table" in names
        assert "browser_navigate" not in names

    def test_ops_has_exec_but_not_browser(self):
        result = filter_tools_by_toolset(_FAKE_TOOLS, "ops")
        names = {t["name"] for t in result}
        assert "execute_terminal_command" in names
        assert "browser_navigate" not in names

    @pytest.mark.parametrize("toolset_name", sorted(TOOLSET_NAMES))
    def test_result_is_subset_of_input(self, toolset_name: str):
        result = filter_tools_by_toolset(_FAKE_TOOLS, toolset_name)
        for tool in result:
            assert tool in _FAKE_TOOLS
