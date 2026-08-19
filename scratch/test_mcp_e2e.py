import asyncio
from tools.registry import load_registry

async def test_invoke():
    registry = load_registry()
    
    mcp_tools = [name for name in registry.names() if "github" in name]
    print(f"MCP Tools available: {mcp_tools[:5]}")
    
    # Try searching for a public repository
    tool_name = "github_search_repositories"
    if tool_name not in registry.names():
        print(f"Tool {tool_name} not found")
        return
        
    tool = registry.get(tool_name)
    print(f"Invoking {tool_name}...")
    
    try:
        result = await tool.ainvoke({"query": "modelcontextprotocol language:typescript"})
        print("Success! Result sample:")
        print(str(result)[:500])
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_invoke())
