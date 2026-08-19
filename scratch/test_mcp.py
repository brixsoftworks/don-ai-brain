from tools.registry import load_registry

if __name__ == "__main__":
    registry = load_registry()
    print(f"Total tools loaded: {len(registry.names())}")
    
    mcp_tools = [name for name in registry.names() if "github" in name or "pull_request" in name or "issue" in name]
    print(f"GitHub/MCP tools found: {len(mcp_tools)}")
    if mcp_tools:
        print(f"Sample: {mcp_tools[:5]}")
