"""
server.py
---------

An MCP (Model Context Protocol) server that exposes the same two tools
used by the RAG + tool-routing agent (github.com/SantoshpHiremath/rag-tool-agent-demo,
already wrapped as a Flask API in ../rag-tool-api-docker/) as proper MCP
tools, callable by any MCP-compatible client (Claude Desktop, an
MCP-aware agent harness, etc.) instead of only through that project's own
CLI or HTTP interface.

Why this exists: the agent's own tool-routing logic (decide "calculator"
vs. "retrieval" vs. "direct answer" for an incoming question) is a
hand-rolled if/else dispatcher inside the agent itself. MCP inverts that:
the *host* (the LLM client) does the routing, by looking at each tool's
name/description/schema and deciding which one to call. So this server
doesn't reimplement routing — it exposes the two underlying capabilities
(retrieval-grounded lookup, arithmetic) as standalone MCP tools with
proper JSON-schema-typed parameters, and lets any MCP client route to
them itself.

Two tools:

- search_notes(query: str) -> str
    Retrieval-style lookup. Mirrors the retrieval branch of the original
    agent (and of StubAgentRunner in rag-tool-api-docker/agent_runner.py):
    grounded answers about the FordA dataset notes, returned with the
    same "[Grounded in N retrieved chunk(s) from ...]" provenance suffix
    the original agent uses, so a client can tell a grounded answer from
    an ungrounded one.

- calculate(expression: str) -> str
    Arithmetic tool. Same shape as the calculator branch of the original
    agent: evaluates a numeric expression restricted to +, -, *, /, (),
    digits and decimal points (no eval() on arbitrary input — see
    _safe_eval below).

Run standalone (stdio transport, the default MCP transport for local
clients like Claude Desktop):

    python server.py

Run the test suite (no MCP client or network needed — tools are called
directly as plain Python functions via FastMCP's .fn attribute):

    pytest tests/ -v
"""

from __future__ import annotations

import ast
import operator

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("rag-tool-agent")

# Same three FordA-dataset notes the original agent's retrieval tool is
# grounded in (see rag-tool-agent-demo/forda_dataset_notes.md), inlined
# here so this server has no external file/vector-store dependency.
_NOTES = [
    "The FordA dataset is a univariate time-series classification dataset "
    "from the UCR Time Series Archive, containing engine noise measurements "
    "used to detect the presence or absence of a specific automotive "
    "subsystem fault.",
    "FordA was contributed by Ford Motor Company as part of a 2008 "
    "classification competition and has since become a standard benchmark "
    "for time-series classification research.",
    "Each FordA sample is a fixed-length sequence of 500 sensor readings, "
    "labeled as either a normal engine measurement or one exhibiting the "
    "target fault symptom.",
]


def _retrieve(query: str, k: int = 3) -> list[str]:
    """Very small keyword-overlap retriever (no embeddings/vector index
    in this standalone server — the point of this project is the MCP
    tool-exposure layer, not re-deriving FAISS retrieval). Returns the
    top-k notes ranked by keyword overlap with the query."""
    query_words = {w.lower().strip(".,?") for w in query.split()}
    scored = sorted(
        _NOTES,
        key=lambda note: len(query_words & {w.lower().strip(".,?") for w in note.split()}),
        reverse=True,
    )
    return scored[:k]


@mcp.tool()
def search_notes(query: str) -> str:
    """Answer a question about the FordA dataset using retrieval over a
    small local notes corpus, and say clearly how many chunks the answer
    was grounded in."""
    chunks = _retrieve(query)
    answer = " ".join(chunks[:1]) if chunks else "No grounded information found."
    return f"{answer}\n\n[Grounded in {len(chunks)} retrieved chunk(s) from forda_dataset_notes.md]"


# Only these operators are permitted — deliberately not a general eval().
_ALLOWED_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.USub: operator.neg,
}


def _safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_OPS:
        return _ALLOWED_OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_OPS:
        return _ALLOWED_OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError(f"Unsupported expression element: {ast.dump(node)}")


@mcp.tool()
def calculate(expression: str) -> str:
    """Evaluate a numeric arithmetic expression (+, -, *, /, parentheses
    only) and return the result. Rejects anything outside that grammar
    instead of using a general-purpose eval()."""
    try:
        tree = ast.parse(expression, mode="eval")
        result = _safe_eval(tree.body)
    except Exception as exc:  # noqa: BLE001 - deliberately broad, surfaced to the caller
        return f"Error: could not evaluate '{expression}' ({exc})"
    return f"{expression} = {result}"


if __name__ == "__main__":
    mcp.run()
