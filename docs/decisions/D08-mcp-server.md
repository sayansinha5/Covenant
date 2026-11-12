# D8 — A separate stdio MCP server

**Status:** accepted

**Decision.** The MCP server (`mcp` SDK, FastMCP, stdio) is its own Compose service that calls
Covenant's REST API with an organization API key. It holds no business rules: mandate checks,
approvals and funding all happen in the API, exactly as for the web app.
