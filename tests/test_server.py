"""
Tests for server.py's two MCP tools.

FastMCP tools are plain Python functions wrapped by the @mcp.tool()
decorator; the original, uncorrected function is reachable via `.fn`, so
these tests call the real tool logic directly with no MCP client, no
transport, and no network involved — the same "test the real logic
through its real interface" approach used in rag-tool-api's own
test suite.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import search_notes, calculate  # noqa: E402


class TestSearchNotes:
    def test_forda_query_returns_grounded_answer(self):
        result = search_notes(query="What is the FordA dataset?")
        assert "FordA" in result
        assert "Grounded in" in result
        assert "retrieved chunk(s)" in result

    def test_grounding_count_matches_notes_corpus_size(self):
        result = search_notes(query="engine fault classification")
        assert "Grounded in 3 retrieved chunk(s)" in result

    def test_unrelated_query_still_returns_a_grounded_response(self):
        # Small keyword-overlap retriever always returns its top-k notes,
        # even on a poor-overlap query — matches the "always grounded,
        # never hallucinated" contract of the original retrieval tool.
        result = search_notes(query="pizza")
        assert "Grounded in" in result


class TestCalculate:
    def test_addition(self):
        assert calculate(expression="2 + 2") == "2 + 2 = 4"

    def test_division_matches_original_agent_example(self):
        result = calculate(expression="1320 / (3601 + 1320)")
        assert result.startswith("1320 / (3601 + 1320) = 0.2682")

    def test_multiplication_and_subtraction(self):
        assert calculate(expression="10 * 3 - 5") == "10 * 3 - 5 = 25"

    def test_negative_number(self):
        assert calculate(expression="-4 + 10") == "-4 + 10 = 6"

    def test_rejects_non_arithmetic_input(self):
        result = calculate(expression="import os")
        assert result.startswith("Error:")

    def test_rejects_function_call_injection(self):
        # Guards against exactly the kind of thing a bare eval() would
        # allow: __import__, os.system, etc.
        result = calculate(expression="__import__('os').system('echo hi')")
        assert result.startswith("Error:")

    def test_division_by_zero_reports_error_not_crash(self):
        result = calculate(expression="1 / 0")
        assert result.startswith("Error:")


class TestToolRegistration:
    def test_both_tools_registered_with_descriptions(self):
        from server import mcp
        import asyncio

        tools = asyncio.run(mcp.list_tools())
        names = {t.name for t in tools}
        assert names == {"search_notes", "calculate"}
        for t in tools:
            assert t.description  # every tool must be self-describing for MCP clients
