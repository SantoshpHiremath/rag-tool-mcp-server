# RAG Tool Agent — MCP Server

Exposes the two tools behind the
[rag-tool-agent-demo](https://github.com/SantoshpHiremath/rag-tool-agent-demo)
project (retrieval-grounded Q&A over FordA dataset notes, and a safe
arithmetic calculator) as a proper [Model Context
Protocol](https://modelcontextprotocol.io) server, so any MCP-compatible
client — Claude Desktop, an MCP-aware agent harness, or a custom host —
can call them directly instead of only through that project's own CLI or
through the Flask HTTP wrapper in
[`rag-tool-api-docker`](../rag-tool-api-docker/).

Built to close a specific, named gap: several current AI-engineer/agentic
application postings explicitly ask for hands-on experience with MCP (and
related agent-to-agent/agent-to-UI protocols). This is a small, real,
tested implementation, not a claim of protocol experience without
evidence behind it.

## Why it's structured this way

The original agent does its own routing internally — a hand-rolled
if/else that decides "calculator" vs. "retrieval" vs. "direct answer" for
each incoming question. MCP inverts that: the **client** (the LLM/agent
host) does the routing, by reading each tool's name, description, and
JSON-schema parameters and deciding which one to call. So this server
doesn't reimplement the original routing logic — it exposes the two
underlying capabilities as standalone, independently-callable MCP tools
and lets any MCP client route to them itself. That's the actual point of
the protocol: tools become host-agnostic instead of hardwired into one
agent's dispatch logic.

- **`search_notes(query: str) -> str`** — retrieval-style lookup over a
  small inlined notes corpus about the FordA dataset, returned with the
  same `[Grounded in N retrieved chunk(s) from ...]` provenance suffix
  the original agent uses, so a client can tell a grounded answer from an
  ungrounded one. Uses a small keyword-overlap ranker rather than
  re-deriving the original project's FAISS/embeddings index — the point
  of this project is the MCP exposure layer, not duplicating that work.
- **`calculate(expression: str) -> str`** — arithmetic tool, restricted
  to `+ - * / ()` and numeric literals via an `ast`-based safe evaluator
  (not a bare `eval()` on arbitrary input). Verified to reject both
  non-arithmetic input and injection attempts like
  `__import__('os').system(...)`.
- Built with the official `mcp` Python SDK (`FastMCP`), the same SDK
  Anthropic publishes for building MCP servers.

## Running it

```bash
pip install -r requirements.txt
python server.py
```

Runs over stdio — the standard local transport MCP clients like Claude
Desktop use to launch and talk to a server as a subprocess. To point
Claude Desktop at it, add to its MCP server config:

```json
{
  "mcpServers": {
    "rag-tool-agent": {
      "command": "python",
      "args": ["/absolute/path/to/server.py"]
    }
  }
}
```

## Running the tests

```bash
pytest tests/ -v
```

11 tests, all passing — call the tool functions directly (no MCP
transport needed for unit-level coverage of the tool logic itself):
grounded retrieval answers, the grounding-count contract, arithmetic
correctness (including a division example matching the original agent's
own documented example), rejection of non-arithmetic and injection input,
division-by-zero handling, and tool self-registration with descriptions.

## Verified as a real MCP server, not just as functions

Beyond the unit tests, this was verified end-to-end using the real
`mcp` client SDK (`ClientSession` + `stdio_client`) — spawning `server.py`
as an actual subprocess, completing the MCP `initialize` handshake,
calling `list_tools()`, and calling both tools over the real protocol:

```
TOOLS: ['search_notes', 'calculate']
calculate -> 1320 / (3601 + 1320) = 0.2682381629750051
search_notes -> The FordA dataset is a univariate time-series
  classification dataset... [Grounded in 3 retrieved chunk(s) from
  forda_dataset_notes.md]
calculate(injection) -> Error: could not evaluate "__import__('os')" ...
```

That confirms the server speaks real MCP (handshake, tool discovery, tool
invocation) and not just that the underlying Python functions work in
isolation.

## Relationship to the other two projects

- [`rag-tool-agent-demo`](https://github.com/SantoshpHiremath/rag-tool-agent-demo) —
  the original CLI agent: LangChain, FAISS, Ollama, LCEL retrieval chain,
  calculator tool, LLM-driven routing.
- [`rag-tool-api-docker`](../rag-tool-api-docker/) — that agent wrapped as
  a Flask HTTP API, containerized (Docker, multi-stage build, non-root
  user, health check), verified with real HTTP requests against a running
  container.
- **This project** — the same underlying capabilities (retrieval,
  calculator) exposed over MCP instead of HTTP, so they're callable by
  any MCP host rather than only by a REST client.
