import os
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.session import ClientSession
from langchain_mcp_adapters.tools import load_mcp_tools
import asyncio

async def test():
    server_params = StdioServerParameters(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-github"],
        env={"GITHUB_PERSONAL_ACCESS_TOKEN": os.environ.get("GITHUB_TOKEN", "dummy"), "PATH": os.environ.get("PATH", "")}
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await load_mcp_tools(session)
            print("Loaded", len(tools), "tools")
            t = tools[0]
            print("Has _run:", hasattr(t, '_run'))
            print("Has _arun:", hasattr(t, '_arun'))
            print("Is _run implemented:", t._run != NotImplemented)
            
if __name__ == "__main__":
    asyncio.run(test())
