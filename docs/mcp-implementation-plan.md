# EventHorizon MCP Servers — Corrected Implementation Plan

> This plan supersedes the greenfield structure in `mcp-implementation-plan.md` (v1).
> It is written against the **actual** agent-server architecture after a full code review.

## Ground Truth: What Already Exists

| Component | File | Role |
|-----------|------|------|
| Shared tool registry | `tools/data_tools.py` | Single source of truth. `ToolSpec` dataclass + `DATA_TOOLS` list (8 read-only tools) + `run_tool()` + `openai_tool_schemas()` |
| Hardened DB layer | `tools/postgres.py` | **SELECT-only**, folder-scoped, statement timeout, row caps |
| MCP surface (external) | `mcp_server/server.py` | FastMCP server exposing the registry to external MCP clients (Claude Desktop, Inspector) over stdio/HTTP |
| In-process provider (agent) | `tools/inprocess.py` | `InProcessToolProvider` — same tool surface as MCP but dispatched directly (no subprocess) for latency |
| LangGraph agent | `graph/builder.py` | One graph: `input_guard → context_loader → intent_router → data_agent → tool_executor → finalizer` |
| MCP subprocess bridge | `graph/mcp_client.py` | Spawns the MCP server over stdio (alternate path; agent currently uses in-process) |
| Surfaces (endpoints) | `main.py` | `/agent/chat/stream` (surface=`chat`), `/agent/dashboard/stream` (surface=`dashboard`), `/report/chat/stream` (surface=`report`) |
| Report writer | `reports/writer.py` | Builds PDF/markdown report files |

### Critical Findings

1. **Everything is read-only.** No tool creates or mutates a table. `postgres.py` rejects any non-SELECT SQL.
2. **No transform-table creation exists.** The frontend pipeline gates Visualize/Publish on a table with `source='agent_created'`, but nothing in the agent-server produces one. **This is the core gap to build.**
3. **No per-surface tool gating.** `data_agent` gives every surface the same 8 read-only tools. `surface` only affects `thread_id` today.
4. **One graph, three surfaces.** The right isolation unit is the `surface` field, not separate servers.

---

## Corrected Approach

**Do NOT build 3 separate greenfield MCP servers.** Instead, extend the existing single-registry / single-server / single-graph design with **surface-scoped tool sets**. This preserves the security model (forced `folder_id`, injected identity, "MCP and agent never drift").

### Design Principles (unchanged from v1, still valid)
- Data quality rules (6 dimensions, 30+ checks) — see `mcp-servers-plan.md`
- ChartSpec model & responsive dashboard — see `visualize-chart-plan.md`
- Access boundaries: Prepare → transform table → Visualize → charts → Report

### What Changes Structurally

```
tools/
├── postgres.py            # EXTEND: add guarded write path (execute_ddl_dml)
├── data_tools.py          # EXTEND: registry gains `surfaces` field per ToolSpec
├── prepare_tools.py       # NEW: transform/clean/validate tools (write-capable)
├── visualize_tools.py     # NEW: analysis + chart-spec tools (read transform only)
├── report_tools.py        # NEW: report authoring tools
└── inprocess.py           # EXTEND: filter tools by surface

mcp_server/
└── server.py              # EXTEND: register new tools, tag by surface

graph/
└── builder.py             # EXTEND: pass surface to provider; surface-aware prompts
```

---

## Step 1: Add `surfaces` to the Registry (`data_tools.py`)

Extend `ToolSpec` so every tool declares which surfaces may use it:

```python
@dataclass(frozen=True)
class ToolSpec:
    name: str
    title: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., dict[str, Any]]
    annotations: dict[str, Any] = field(default_factory=dict)
    # NEW: which surfaces expose this tool. Empty = all surfaces (back-compat).
    surfaces: frozenset[str] = field(default_factory=frozenset)
```

The 8 existing read-only tools get `surfaces=frozenset()` (available everywhere — they're safe reads). New write/analysis/report tools declare specific surfaces.

Add a filtered schema helper:

```python
def openai_tool_schemas(surface: str | None = None) -> list[dict[str, Any]]:
    tools = DATA_TOOLS
    if surface:
        tools = [t for t in tools if not t.surfaces or surface in t.surfaces]
    return [{"type": "function", "function": {...}} for t in tools]
```

---

## Step 2: Guarded Write Path (`postgres.py`)

Add ONE narrowly-scoped write function used only by Prepare tools. It must:
- Only allow `CREATE TABLE <folder_schema>.<name> AS SELECT ...` and `DROP TABLE` of agent-created tables
- Enforce the folder schema prefix (`AGENT_FOLDER_SCHEMA_PREFIX`) so writes can't escape the folder
- Reject any statement touching uploaded/source tables destructively
- Run inside a transaction with the same statement timeout

```python
def create_transform_table(folder_id, user_id, select_sql, *, name="transform") -> dict:
    """CREATE TABLE AS from a validated SELECT, scoped to the folder's agent schema.
    Marks the new table source='agent_created' in the folder registry."""
```

This is the single most security-sensitive addition — it needs explicit review and tests before merge.

---

## Step 3: Prepare Tools (`tools/prepare_tools.py`, surface=`chat`)

All tagged `surfaces=frozenset({"chat"})`. Built on `create_transform_table` + read helpers.

| Tool | Type | Notes |
|------|------|-------|
| `prepare_detect_quality_issues` | read | Runs the 30+ rules, returns issue report |
| `prepare_plan_transform` | read | Proposes a cleaning plan (no writes) |
| `prepare_build_transform` | **write** | Executes a validated SELECT into a transform table (dedupe, cast, join, compute via SQL) |
| `prepare_validate_transform` | read | Re-checks all quality rules on the built transform |
| `prepare_get_transform_summary` | read | Before/after row counts, quality score |

Quality-rule implementations live in a new `tools/quality_rules.py` (pure SQL/pandas checks). The transform is expressed as SQL (`CREATE TABLE AS SELECT`) so it reuses the hardened Postgres path — no separate pandas engine or new DB layer.

---

## Step 4: Visualize Tools (`tools/visualize_tools.py`, surface=`dashboard`)

All tagged `surfaces=frozenset({"dashboard"})`. **Read-only, scoped to the transform table only.**

A shared helper resolves the folder's single `source='agent_created'` table and refuses if none exists:

```python
def _require_transform(folder_id, user_id) -> str:
    t = get_transform_table(folder_id, user_id)
    if not t: raise ToolError("No transform table yet. Complete Prepare first.")
    return t
```

| Tool | Notes |
|------|-------|
| `viz_get_schema` | Transform table schema |
| `viz_column_stats` | Reuses existing `data_column_stats` scoped to transform |
| `viz_aggregate` | Reuses existing `data_aggregate` scoped to transform |
| `viz_correlation` | New: Pearson/Spearman between two numeric cols |
| `viz_time_series` | New: time-indexed extraction for trends |
| `viz_suggest_charts` | New: recommend chart types from column shapes |
| `viz_create_chart` | New: emit a **ChartSpec artifact** (see `visualize-chart-plan.md`) |

`viz_create_chart` does not render; it returns a `ChartSpec` that the graph emits as an `artifact` SSE event. The frontend (`useAgentChat` → `appState.addChart`) renders it live. This matches the chart plan already saved.

---

## Step 5: Report Tools (`tools/report_tools.py`, surface=`report`)

All tagged `surfaces=frozenset({"report"})`. Reads transform summary + charts; authors sections.

| Tool | Notes |
|------|-------|
| `report_list_charts` | Charts available to embed |
| `report_get_data_summary` | High-level summary from transform |
| `report_create_section` | Add a titled section (may reference chart IDs) |
| `report_generate_narrative` | Draft narrative from chart insights |
| `report_finalize` | Hand off to existing `reports/writer.py` for PDF/markdown |

This layers on top of the existing `/report/chat/stream` + `reports/writer.py` rather than replacing them.

---

## Step 6: Surface-Aware Graph (`graph/builder.py`)

Two small changes:

1. Pass the surface into the provider so the LLM only sees allowed tools:
   ```python
   provider = InProcessToolProvider(user_id, folder_id, surface=state.get("surface"))
   ```
   (`InProcessToolProvider.__init__` calls `openai_tool_schemas(surface)`.)

2. Surface-specific system prompts (the LLM instructions from `mcp-servers-plan.md`):
   - `chat` → Prepare agent prompt (enforce quality rules, save only on pass)
   - `dashboard` → Visualize agent prompt (transform-only, chart design rules)
   - `report` → Report agent prompt (no fabrication, reference real charts)

No new graph nodes needed — the existing `data_agent` tool loop works for all three; only its toolset and prompt change per surface.

---

## Step 7: MCP Server Registration (`mcp_server/server.py`)

The external MCP server registers the new tools too, tagged by surface in their titles/annotations. External clients can call any tool (they're a power-user surface), but the write tools keep the same folder-schema guardrails. No structural change — just more `@mcp.tool` wrappers delegating to `run_tool`.

---

## Build Order & Verification

1. `postgres.create_transform_table` + tests (security-critical, do first)
2. `quality_rules.py` + unit tests on sample data
3. `prepare_tools.py` → register → gate to `chat` → manual stream test
4. `visualize_tools.py` + ChartSpec artifact → verify frontend renders
5. `report_tools.py` → verify PDF output via existing writer
6. Surface gating in `inprocess.py` + `builder.py` → confirm each mode sees only its tools
7. Update `mcp_server/server.py` + run MCP Inspector

Each step: `python -m py_compile`, run existing `agent-server/tests/`, and a manual SSE smoke test per surface.

---

## Open Questions to Resolve Before Coding

1. **Where do `agent_created` tables get registered** so the backend/frontend see them? Need to confirm the folder→table registry mechanism (backend `router/` + `dataModels/`).
2. **Transform table cardinality**: one per folder (overwrite) or versioned? Plan assumes one (overwrite on rebuild).
3. **Chart persistence**: are ChartSpecs stored server-side or only client-side state? The chart plan assumes client-side `appState.charts`; confirm if reports need them persisted.
