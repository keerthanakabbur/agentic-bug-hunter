"""
mcp_client.py
-------------
Connects to FastMCP server (transport="sse") at http://localhost:8003/sse

ROOT CAUSE OF TIMEOUT BUG:
  The old _run() created a new loop, ran the coroutine, then called loop.close().
  The NEXT call found a closed loop, tried to create another one, but Flask's
  threading model caused it to hang indefinitely — hence "timeout / still analysing".

FIX:
  A single background thread owns a permanent asyncio event loop that NEVER closes.
  Every call submits a coroutine to that loop via asyncio.run_coroutine_threadsafe()
  and blocks the calling thread until the result is ready. No loops are ever closed.
  Works correctly across all Flask worker threads.
"""

import sys
import asyncio
import json
import threading
from typing import Any

# ── Windows asyncio fix ───────────────────────────────────────────────────────
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

MCP_SSE_URL = "http://localhost:8003/sse"

# ── Permanent background event loop ──────────────────────────────────────────
# One loop, one thread, lives for the entire process lifetime.
_loop = asyncio.new_event_loop()

def _start_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

_loop_thread = threading.Thread(target=_start_loop, args=(_loop,), daemon=True)
_loop_thread.start()


# ── Submit async work to the permanent loop ───────────────────────────────────
def _run(coro, timeout: float = 30.0) -> Any:
    """
    Submit a coroutine to the permanent event loop from any thread.
    Blocks the calling thread until done or timeout.
    """
    future = asyncio.run_coroutine_threadsafe(coro, _loop)
    return future.result(timeout=timeout)   # raises concurrent.futures.TimeoutError on timeout


# ── Core async tool caller ────────────────────────────────────────────────────
async def _call_tool(tool_name: str, arguments: dict) -> Any:
    from fastmcp.client import Client, SSETransport
    transport = SSETransport(MCP_SSE_URL)
    async with Client(transport) as client:
        return await client.call_tool(tool_name, arguments)


# ── Parse FastMCP CallToolResult → plain Python ──────────────────────────────
def _parse_result(result) -> Any:
    if result is None:
        return None
    # FastMCP wraps results in a list of content blocks
    if isinstance(result, list):
        # Each block has .text attribute
        for block in result:
            text = getattr(block, "text", None)
            if text is not None:
                try:
                    return json.loads(text)
                except (json.JSONDecodeError, TypeError):
                    return text
        return result
    # Direct .content attribute (older FastMCP versions)
    if hasattr(result, "content"):
        try:
            block = result.content[0]
            text = getattr(block, "text", "")
            try:
                return json.loads(text)
            except Exception:
                return text
        except Exception:
            pass
    # .data shortcut
    if hasattr(result, "data"):
        return result.data
    # Primitives
    if isinstance(result, (str, int, float, bool)):
        return result
    return result


# ── Public API ────────────────────────────────────────────────────────────────

def search_documents(query: str) -> list:
    """
    Search the MCP documentation server.
    Returns list of {"text": str, "score": float} dicts, or [] on error.
    """
    try:
        raw    = _run(_call_tool("search_documents", {"query": query}), timeout=30.0)
        parsed = _parse_result(raw)
        return parsed if isinstance(parsed, list) else []
    except Exception as e:
        print(f"[MCP] search_documents('{query[:40]}') failed: {e}")
        return []


def add(a: int, b: int) -> Any:
    """Connectivity check tool."""
    try:
        raw = _run(_call_tool("add", {"a": a, "b": b}), timeout=10.0)
        return _parse_result(raw)
    except Exception as e:
        print(f"[MCP] add failed: {e}")
        return None


# ── Quick self-test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Testing MCP connection...")
    r = add(3, 4)
    print(f"add(3,4) = {r}  {'✅' if r == 7 else '❌'}")
    docs = search_documents("RDI_BEGIN lifecycle")
    print(f"search_documents → {len(docs)} results")
    if docs:
        print(f"top score: {docs[0]['score']:.4f}")
        print(f"preview  : {docs[0]['text'][:100]}")
    # Call AGAIN to prove the loop is still alive
    docs2 = search_documents("vecEditMode VTT VECD")
    print(f"second call → {len(docs2)} results  {'✅ loop still alive' if docs2 else '❌'}")
