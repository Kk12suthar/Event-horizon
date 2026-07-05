# EventHorizon Data MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io) server that exposes
the EventHorizon folder-scoped PostgreSQL data layer as MCP tools. It reuses the
hardened query layer in `tools/postgres.py`, so every operation is **read-only**
and **folder-scoped**.

## Tools

| Tool | Description |
|------|-------------|
| `data_list_tables` | List the tables available in a folder. |
| `data_describe_tables` | Columns, types, row estimates, and sample rows for every table in a folder. |
| `data_run_query` | Run a single folder-scoped, read-only `SELECT` query. |
| `data_profile_nulls` | Count NULL values per column for a table (data-quality check). |

Every tool requires a `folder_id` (the EventHorizon folder UUID). Only SELECT
statements are permitted; mutating SQL, multiple statements, system-catalog
access, and schema-qualified names are rejected.

## Requirements

- The same PostgreSQL environment variables the agent server uses
  (`POSTGRES_HOST`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DBNAME`,
  `POSTGRES_UPLOAD_SCHEMA`, `AGENT_FOLDER_SCHEMA_PREFIX`). These are loaded from
  the repo-root `.env` automatically.
- `pip install -r requirements.txt` (includes `mcp`).

## Trusted identity

Folder access is enforced by `require_folder_access`, which needs the calling
user's id. Because an LLM must never choose *who* it is, the user id is supplied
out-of-band via the `EVENTHORIZON_AGENT_USER_ID` environment variable. When the
EventHorizon agent spawns this server it injects the authenticated user id; the
tools then run their access checks against that real user. Standalone clients
(Claude Desktop, the Inspector) may set the same variable to scope access.

## Use from the EventHorizon agent (LangGraph)

The agent does not call the Postgres layer directly. Its `mcp_agent` graph node
spawns this server over **stdio** (`graph/mcp_client.py`), lists the tools, and
exposes them to the model as function-calling tools. The model decides whether
and which tools to call; the agent forces the `folder_id` to the request's
folder and injects `EVENTHORIZON_AGENT_USER_ID`, so the model can never reach
across folder boundaries or impersonate another user. If the MCP server or the
model is unavailable, the agent degrades to a built-in deterministic path.

## Running

```bash
# stdio (default) - for local clients such as Claude Desktop / Claude Code
python -m mcp_server.server

# streamable HTTP - for a remote/network server (listens on :8000/mcp)
set MCP_TRANSPORT=http
python -m mcp_server.server
```

## Testing with the MCP Inspector

```bash
npx -y @modelcontextprotocol/inspector
# then run the server with MCP_TRANSPORT=http and connect to http://localhost:8000/mcp
```

## Registering with clients

### Kiro / Claude Desktop (stdio)

A ready-to-use config lives at `.kiro/settings/mcp.json`:

```json
{
  "mcpServers": {
    "eventhorizon-data": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "c:\\Users\\kixlo\\Desktop\\EventHorizon\\agent-server",
      "env": { "MCP_TRANSPORT": "stdio" },
      "disabled": false,
      "autoApprove": ["data_list_tables", "data_describe_tables"]
    }
  }
}
```

### Claude Code

```bash
# stdio
claude mcp add eventhorizon-data -- python -m mcp_server.server

# or HTTP (after starting the server with MCP_TRANSPORT=http)
claude mcp add --transport http eventhorizon-data http://localhost:8000/mcp
```
