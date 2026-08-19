"""tools/mcp_loader.py — dynamic loading of MCP servers.

Connects to stdio MCP servers and maps them to LangChain BaseTools.
"""
from __future__ import annotations

import logging
import os
import asyncio
from langchain_core.tools import BaseTool

log = logging.getLogger("don.tools.mcp")


def load_github_mcp_tools() -> list[BaseTool]:
    """Load tools from the official GitHub MCP server.

    Returns:
        List of initialized LangChain tools wrapping the MCP calls.
    """
    try:
        from langchain_mcp_adapters.tools import load_mcp_tools
    except ImportError:
        log.warning("langchain-mcp-adapters not installed. Skipping GitHub MCP.")
        return []

    # Requires Node.js and npx in PATH, plus GITHUB_TOKEN.
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        log.warning("GITHUB_TOKEN not set. GitHub MCP tools may fail if they require auth.")

    connection_config = {
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env": {
            "GITHUB_PERSONAL_ACCESS_TOKEN": token,
            "PATH": os.environ.get("PATH", ""),
        },
    }

    log.info("Bootstrapping GitHub MCP server tools...")
    try:
        import threading
        
        # We must run load_mcp_tools synchronously, but if the current thread
        # already has a running event loop, loop.run_until_complete() will crash.
        # So we run it in a dedicated thread with a fresh event loop.
        tools_result: list[BaseTool] = []
        err_result: list[Exception] = []

        def _bootstrap_thread():
            try:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                res = new_loop.run_until_complete(
                    load_mcp_tools(
                        None, 
                        connection=connection_config, 
                        server_name="github",
                        tool_name_prefix=True
                    )
                )
                tools_result.extend(res)
            except Exception as e:
                err_result.append(e)
            finally:
                new_loop.close()

        t = threading.Thread(target=_bootstrap_thread)
        t.start()
        t.join()

        if err_result:
            raise err_result[0]
            
        log.info("Loaded %d GitHub MCP tools.", len(tools_result))
        return tools_result
    except Exception as exc:  # noqa: BLE001
        log.error("Failed to load GitHub MCP tools: %s", exc)
        return []
