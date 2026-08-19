import os
from mcp import StdioServerParameters
from mcp.client.stdio import sync_stdio_client
from mcp.client.session import SyncClientSession
from langchain_mcp_adapters.tools import load_mcp_tools

def test():
    server_params = StdioServerParameters(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-github"],
        env={"GITHUB_PERSONAL_ACCESS_TOKEN": "dummy", "PATH": os.environ.get("PATH", "")}
    )
    # The sync clients
    with sync_stdio_client(server_params) as (read, write):
        with SyncClientSession(read, write) as session:
            session.initialize()
            try:
                tools = load_mcp_tools(session)
                print("Loaded sync tools:", len(tools))
            except Exception as e:
                print("Error:", e)

if __name__ == "__main__":
    test()
