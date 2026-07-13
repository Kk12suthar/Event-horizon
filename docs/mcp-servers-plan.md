# EventHorizon MCP Servers — Complete Design Plan

> **⚠️ STRUCTURE SUPERSEDED — read `mcp-implementation-plan.md` for how to actually build this.**
>
> A code review of `agent-server/` found the platform already has ONE shared tool
> registry (`tools/data_tools.py`), ONE MCP server (`mcp_server/server.py`), and ONE
> LangGraph agent routing three surfaces (`chat`/`dashboard`/`report`). The "three
> separate MCP servers" framing below is **conceptual only**. Implement the three
> tool sets as **surface-gated tools in the existing single server/registry**, per
> the corrected plan.
>
> **Still valid and reusable from this doc:** the data-quality rules (6 dimensions,
> 30+ checks), the per-stage tool lists, the LLM system prompts, and the access
> boundaries. Treat "MCP Server 1/2/3" as "the Prepare/Visualize/Report **tool set +
> surface**", not as separate processes.

## Architecture Overview

Three isolated tool sets (surface-gated within one server), each serving a stage of the pipeline:

```
┌─────────────┐       ┌──────────────┐       ┌─────────────┐
│   PREPARE   │──────▶│  VISUALIZE   │──────▶│   REPORT    │
│  MCP Server │       │  MCP Server  │       │  MCP Server │
└─────────────┘       └──────────────┘       └─────────────┘
       │                      │                      │
  Raw uploaded           Transform table         Charts + analysis
  tables only            only (read-only)        results only
```

**Access Boundary Rule**: Each server can ONLY access the output of the previous stage. No server can reach back to a prior stage's raw data.

---

## Data Quality Rules (Enforced by Prepare Server)

These rules are checked automatically before a transform table is marked as complete. The LLM is instructed to validate against ALL of these before finalizing.

### Dimension 1: Uniqueness (No Duplicates)

| # | Rule | Description | Auto-fix Action |
|---|------|-------------|-----------------|
| 1.1 | Exact row duplicates | Identical values across ALL columns | Remove duplicates, keep first |
| 1.2 | Key column duplicates | Duplicate values in primary/business key columns | Flag for user review |
| 1.3 | Near-duplicates | Rows differing only by whitespace, casing, or trivial chars | Normalize then deduplicate |
| 1.4 | Cross-table duplicates | Same entity appearing in multiple source tables being joined | Merge with precedence rules |

### Dimension 2: Completeness (No Missing Data)

| # | Rule | Description | Auto-fix Action |
|---|------|-------------|-----------------|
| 2.1 | Null check on required columns | Columns marked as required must have zero nulls | Flag; impute only if safe |
| 2.2 | Empty string detection | Strings that are "" or whitespace-only treated as missing | Convert to null, apply 2.1 |
| 2.3 | Column completeness ratio | Each column must have ≥ 80% non-null values (configurable) | Report; suggest drop if < 20% |
| 2.4 | Row completeness | Each row must have ≥ 50% of its columns populated | Flag sparse rows |
| 2.5 | Mandatory relationship fields | Foreign key / join columns must never be null | Reject or segregate |

### Dimension 3: Consistency (Uniform Formats)

| # | Rule | Description | Auto-fix Action |
|---|------|-------------|-----------------|
| 3.1 | Date format consistency | All dates in a column use the same format (ISO 8601 preferred) | Parse and re-format to ISO |
| 3.2 | Number format consistency | No mixed decimals (1,000 vs 1.000 locale issues) | Normalize to standard decimal |
| 3.3 | Category consistency | Same category spelled differently (e.g., "US", "U.S.", "United States") | Map to canonical values |
| 3.4 | Unit consistency | Same metric in different units (kg vs lbs, USD vs $) | Convert to single unit |
| 3.5 | Boolean consistency | Mixed representations (true/false, 1/0, yes/no, Y/N) | Normalize to true/false |
| 3.6 | Case consistency | Same column has mixed casing ("new york", "New York", "NEW YORK") | Normalize to title/lower case |

### Dimension 4: Validity (Correct Types & Ranges)

| # | Rule | Description | Auto-fix Action |
|---|------|-------------|-----------------|
| 4.1 | Type conformance | Each column's values match its declared type | Cast or flag errors |
| 4.2 | Range validation | Numeric values within expected min/max bounds | Flag outliers |
| 4.3 | Pattern validation | Emails, phones, URLs match expected regex patterns | Flag invalid |
| 4.4 | Enum validation | Categorical values only contain allowed values | Flag unknowns |
| 4.5 | Date range validation | No future dates where inappropriate, no dates before reasonable minimum | Flag invalid |
| 4.6 | Negative value check | Columns like "quantity", "age", "price" should not be negative | Flag or abs() |
| 4.7 | String length bounds | Text columns within expected min/max character length | Truncate or flag |

### Dimension 5: Accuracy (Correct Values)

| # | Rule | Description | Auto-fix Action |
|---|------|-------------|-----------------|
| 5.1 | Statistical outlier detection | Values beyond 3σ from column mean (numeric) | Flag for review |
| 5.2 | Cross-column logic | age < 0 or age > 150, start_date > end_date | Flag contradictions |
| 5.3 | Referential integrity | FK values exist in referenced table | Flag orphans |
| 5.4 | Aggregate sanity | Sum of parts equals total, percentages sum to 100 | Flag mismatches |
| 5.5 | Temporal ordering | Sequential events in correct chronological order | Flag inversions |

### Dimension 6: Timeliness (Fresh & Relevant)

| # | Rule | Description | Auto-fix Action |
|---|------|-------------|-----------------|
| 6.1 | Stale data detection | Records older than a threshold (configurable per dataset) | Flag; suggest filter |
| 6.2 | Missing recent data | Expected time series has gaps in recent periods | Report gap |
| 6.3 | Timestamp freshness | Last-modified/created timestamps are reasonable | Flag suspicious |

---

## MCP Server 1: PREPARE (Data Transformation)

### Purpose
Transform raw uploaded tables into a single clean, validated, analysis-ready table.

### Access Boundary
- **CAN access**: Raw uploaded tables (source = 'uploaded') for the current folder
- **CANNOT access**: Transform tables from other folders, charts, reports, or any Visualize/Report data
- **PRODUCES**: One transform table (source = 'agent_created') that unlocks Visualize mode

### Tools

#### Profiling & Discovery

| Tool | Description | Annotations |
|------|-------------|-------------|
| `prepare_list_tables` | List all uploaded tables in the folder with row/column counts | readOnly |
| `prepare_get_schema` | Get column names, types, sample values (5 rows) for a table | readOnly |
| `prepare_profile_column` | Statistical profile: nulls, distinct count, min/max, mean, std, top values | readOnly |
| `prepare_detect_quality_issues` | Run all quality rules against a table, return issue report | readOnly |
| `prepare_preview_data` | Get first N rows of a table (default 20) | readOnly |
| `prepare_get_row_count` | Get exact row count for a table | readOnly |

#### Cleaning Operations

| Tool | Description | Annotations |
|------|-------------|-------------|
| `prepare_remove_duplicates` | Remove exact duplicate rows or by key columns | destructive |
| `prepare_handle_nulls` | Strategy per column: drop rows, fill with mean/median/mode/constant, forward-fill | destructive |
| `prepare_standardize_column` | Normalize casing, trim whitespace, map category synonyms | destructive |
| `prepare_fix_types` | Cast columns to correct types (string→date, string→number, etc.) | destructive |
| `prepare_remove_outliers` | Remove/cap values beyond N standard deviations or IQR | destructive |
| `prepare_filter_rows` | Remove rows matching a condition (e.g., age < 0) | destructive |
| `prepare_drop_columns` | Remove columns that are irrelevant or too sparse | destructive |
| `prepare_rename_columns` | Rename columns for clarity (snake_case, remove special chars) | destructive |

#### Transformation Operations

| Tool | Description | Annotations |
|------|-------------|-------------|
| `prepare_join_tables` | Join two tables on specified columns (inner, left, right, full) | destructive |
| `prepare_union_tables` | Stack tables vertically (same schema) | destructive |
| `prepare_add_computed_column` | Create a derived column from an expression (e.g., revenue = price × qty) | destructive |
| `prepare_aggregate` | Group-by aggregation (sum, count, avg, min, max) | destructive |
| `prepare_pivot` | Pivot a column's values into separate columns | destructive |
| `prepare_unpivot` | Melt wide columns back to long format | destructive |
| `prepare_sort` | Sort by one or more columns | destructive |
| `prepare_split_column` | Split a column on delimiter into multiple columns | destructive |
| `prepare_merge_columns` | Concatenate multiple columns into one | destructive |
| `prepare_normalize_numeric` | Min-max or z-score normalization on numeric columns | destructive |
| `prepare_bin_column` | Bucket continuous values into discrete bins | destructive |
| `prepare_encode_categorical` | One-hot or label encode categorical columns | destructive |

#### Validation & Finalization

| Tool | Description | Annotations |
|------|-------------|-------------|
| `prepare_validate_transform` | Run ALL quality rules on the current transform; return pass/fail per rule | readOnly |
| `prepare_save_transform` | Finalize and save the transform table (marks it as 'agent_created') | destructive |
| `prepare_get_transform_summary` | Summary of all operations performed, before/after row counts, quality score | readOnly |

### LLM Instructions (System Prompt for Prepare Agent)

```
You are the Data Preparation Agent. Your job is to transform raw uploaded tables into a single clean, analysis-ready table.

WORKFLOW (follow this order):
1. PROFILE: Always start by listing tables and profiling their schemas and quality issues.
2. PLAN: Tell the user what issues you found and propose a cleaning plan.
3. CLEAN: Execute cleaning in this order: deduplicate → standardize → fix types → handle nulls → validate.
4. TRANSFORM: Apply joins, computed columns, aggregations as needed.
5. VALIDATE: Run prepare_validate_transform. ALL rules must pass before saving.
6. SAVE: Only call prepare_save_transform when validation passes.

DATA QUALITY RULES (enforce ALL before saving):
- Zero exact duplicate rows
- Zero nulls in key/required columns
- All columns have consistent types (no mixed types)
- All dates in ISO 8601 format
- All categorical values normalized (no synonym variants)
- No statistical outliers beyond 3σ without user acknowledgment
- Cross-column logic is consistent (no start_date > end_date, no negative ages/prices)
- Column names are clean (snake_case, no special characters, descriptive)

NEVER:
- Save a transform table that has validation failures
- Skip profiling — always inspect before modifying
- Make assumptions about data meaning without asking the user
- Drop columns or rows without informing the user first

ALWAYS:
- Show the user what you found before making changes
- Explain why each transformation is needed
- Report before/after statistics (row count, null count, duplicate count)
- Suggest but don't force — if the user says to keep outliers, keep them
```

---

## MCP Server 2: VISUALIZE (Analysis & Charts)

### Purpose
Perform statistical analysis on the transform table and generate chart specifications.

### Access Boundary
- **CAN access**: ONLY the transform table (source = 'agent_created') for the current folder
- **CANNOT access**: Raw uploaded tables, other folders' data, report drafts
- **PRODUCES**: Charts (ChartSpec artifacts) and analysis insights

### Tools

#### Data Access (Read-Only on Transform Table)

| Tool | Description | Annotations |
|------|-------------|-------------|
| `viz_get_schema` | Get transform table schema (columns, types, row count) | readOnly |
| `viz_query_data` | Query the transform table with filters, sorting, limit/offset | readOnly |
| `viz_get_column_stats` | Statistical summary for a column (mean, median, std, quartiles, distribution) | readOnly |
| `viz_get_correlation` | Pearson/Spearman correlation between two numeric columns | readOnly |
| `viz_get_value_counts` | Frequency counts for a categorical column (top N) | readOnly |
| `viz_get_time_series` | Extract time-indexed data for trend analysis | readOnly |
| `viz_get_group_summary` | Group-by summary stats (count, sum, avg per group) | readOnly |

#### Analysis Operations

| Tool | Description | Annotations |
|------|-------------|-------------|
| `viz_compute_aggregation` | Run multi-column aggregation (pivot-table style) | readOnly |
| `viz_detect_trends` | Identify trends, seasonality, growth rates in time series | readOnly |
| `viz_compare_groups` | Compare metrics across groups (A vs B analysis) | readOnly |
| `viz_find_top_n` | Identify top/bottom N rows by a metric | readOnly |
| `viz_calculate_percentages` | Compute percentage breakdowns (share of total) | readOnly |
| `viz_compute_moving_average` | Rolling window calculations (7-day, 30-day, etc.) | readOnly |
| `viz_detect_anomalies` | Statistical anomaly detection in the analysis data | readOnly |

#### Chart Generation

| Tool | Description | Annotations |
|------|-------------|-------------|
| `viz_create_chart` | Generate a ChartSpec from data analysis (type, axes, data mapping) | idempotent |
| `viz_update_chart` | Modify an existing chart (change type, axes, filters, title) | destructive |
| `viz_delete_chart` | Remove a chart from the dashboard | destructive |
| `viz_list_charts` | List all charts currently in the dashboard | readOnly |
| `viz_suggest_charts` | Auto-suggest chart types based on data shape and column types | readOnly |

### Supported Chart Types

| Type | Best For | Required Fields |
|------|----------|-----------------|
| `line` | Trends over time | xField (date/time), yFields (numeric) |
| `bar` | Category comparison | xField (categorical), yFields (numeric) |
| `area` | Volume over time | xField (date/time), yFields (numeric) |
| `pie` | Part-of-whole | xField (categorical), yFields (single numeric) |
| `donut` | Part-of-whole (cleaner) | xField (categorical), yFields (single numeric) |
| `scatter` | Correlation between two variables | xField (numeric), yFields (numeric) |
| `radar` | Multi-metric comparison | xField (categorical), yFields (multiple numeric) |
| `heatmap` | Density/distribution | xField, yField (both categorical), valueField |
| `stacked_bar` | Category + sub-category breakdown | xField (categorical), yFields (multiple numeric) |
| `grouped_bar` | Side-by-side category comparison | xField (categorical), yFields (multiple numeric) |

### LLM Instructions (System Prompt for Visualize Agent)

```
You are the Data Visualization Agent. Your job is to analyze the prepared transform table and create insightful charts.

ACCESS RULE:
- You can ONLY access the transform table. You have NO access to raw uploaded tables.
- If the transform table doesn't exist yet, tell the user to complete the Prepare step first.

WORKFLOW:
1. UNDERSTAND: Start by examining the schema and getting column stats to understand what data is available.
2. ANALYZE: Run appropriate analysis operations based on the user's question.
3. VISUALIZE: Create charts that clearly communicate the findings.

CHART DESIGN PRINCIPLES:
- Choose chart type based on the data relationship:
  • Trends over time → line or area chart
  • Category comparison → bar chart
  • Part of whole → pie/donut (max 7 segments)
  • Correlation → scatter plot
  • Distribution → histogram or heatmap
  • Multi-metric → radar chart
- Always include a descriptive title
- Limit pie/donut charts to ≤ 7 categories (group the rest as "Other")
- Use readable axis labels (not raw column names)
- For time series, ensure chronological ordering on x-axis
- When comparing groups, sort by value descending for impact

NEVER:
- Generate a chart without first querying the data to verify it makes sense
- Use a pie chart for more than 7 categories
- Create a line chart for non-sequential data
- Assume column meanings — inspect the data first
- Modify or write to the transform table (you have read-only access)

ALWAYS:
- Explain what the chart shows and why you chose that visualization
- Provide the key insight/takeaway alongside the chart
- If the user's request doesn't match the available data, suggest alternatives
- Use viz_suggest_charts when unsure what visualization fits best
```

---

## MCP Server 3: REPORT (Document Generation)

### Purpose
Generate structured reports and documents from analysis results and charts.

### Access Boundary
- **CAN access**: Transform table (read-only), charts created in Visualize, analysis summaries
- **CANNOT access**: Raw uploaded tables, individual data rows beyond summaries
- **PRODUCES**: Report documents (markdown, PDF-ready structured content)

### Tools

#### Context Access

| Tool | Description | Annotations |
|------|-------------|-------------|
| `report_get_transform_summary` | Get summary stats of the transform table (row count, column names, key metrics) | readOnly |
| `report_list_charts` | List all charts with their titles, types, and what they show | readOnly |
| `report_get_chart_insight` | Get the key insight/takeaway for a specific chart | readOnly |
| `report_get_data_summary` | High-level data summary (date range, record count, key dimensions) | readOnly |
| `report_query_aggregates` | Query pre-computed aggregates (totals, averages, growth rates) | readOnly |

#### Report Generation

| Tool | Description | Annotations |
|------|-------------|-------------|
| `report_create_section` | Create a report section with title, body text, and optional chart references | destructive |
| `report_update_section` | Edit an existing report section | destructive |
| `report_delete_section` | Remove a section from the report | destructive |
| `report_reorder_sections` | Change the order of report sections | destructive |
| `report_list_sections` | List current report sections in order | readOnly |
| `report_generate_narrative` | Auto-generate narrative text from chart insights and data summaries | readOnly |
| `report_finalize` | Mark the report as complete and ready for export | destructive |

#### Export

| Tool | Description | Annotations |
|------|-------------|-------------|
| `report_export_markdown` | Export the full report as markdown | readOnly |
| `report_export_pdf` | Trigger PDF generation of the report | idempotent |
| `report_get_preview` | Get a rendered preview of the current report state | readOnly |

### LLM Instructions (System Prompt for Report Agent)

```
You are the Report Generation Agent. Your job is to create clear, professional data reports from analysis results and charts.

ACCESS RULE:
- You can access: transform table summary stats, charts, pre-computed aggregates
- You CANNOT access: raw uploaded data or perform new analysis
- If no charts or analysis exist, tell the user to complete the Visualize step first

WORKFLOW:
1. GATHER: Review available charts, insights, and data summaries
2. STRUCTURE: Propose a report outline to the user
3. WRITE: Generate sections with clear narrative and chart references
4. REVIEW: Show the draft and refine based on feedback
5. FINALIZE: Mark complete when the user approves

WRITING PRINCIPLES:
- Lead with the key insight/finding — don't bury the conclusion
- Every chart referenced should have accompanying narrative explaining "so what?"
- Use concrete numbers: "Revenue grew 23% QoQ" not "Revenue grew significantly"
- Keep sections focused: one main point per section
- Use plain business language — no jargon unless the domain requires it
- Reports should be actionable: end with recommendations or next steps

REPORT STRUCTURE (adapt based on content):
- The user defines the structure. Don't force a template.
- If the user doesn't specify, suggest sections based on available charts and data.
- Keep it flexible: some reports are 3 sections, some are 15.

NEVER:
- Fabricate data or statistics not present in the available summaries
- Reference charts that don't exist
- Generate a report without first checking what charts/analysis are available
- Add filler content — every sentence should add value
- Force a rigid template on the user

ALWAYS:
- Ask the user what kind of report they want (executive summary? deep dive? specific topic?)
- Reference specific chart IDs so the frontend can embed them inline
- Provide a preview before finalizing
- Let the user iterate — reports are collaborative
```

---

## Pipeline Flow & Gating Rules

```
UPLOADED TABLES ──▶ [PREPARE MCP Server] ──▶ TRANSFORM TABLE
                                                    │
                                                    ▼ (unlocks Visualize mode)
                                            [VISUALIZE MCP Server]
                                                    │
                                                    ▼ produces charts + insights
                                            [REPORT MCP Server]
                                                    │
                                                    ▼ produces final report
```

### Gating Rules (enforced by frontend + backend)

| Gate | Condition | What Unlocks |
|------|-----------|--------------|
| Prepare → Visualize | `prepare_save_transform` called successfully AND all quality rules pass | Visualize mode becomes available |
| Visualize → Report | At least one chart exists OR user explicitly requests a report | Report mode becomes available |
| Save transform | ALL data quality rules pass `prepare_validate_transform` | Transform table marked as 'agent_created' |

### Session Isolation

| Mode | Session | Stream Endpoint | Chat History |
|------|---------|-----------------|--------------|
| Prepare | Folder-level | `/agent/transform/stream` | Isolated to Prepare |
| Visualize | Folder-level | `/agent/dashboard/stream` | Isolated to Visualize |
| Report | Folder-level | `/agent/report/stream` | Isolated to Report |

Each mode maintains its own chat thread (already implemented in frontend). The backend routes to the appropriate agent which has access only to its designated MCP server tools.

---

## Implementation Notes

### Technology Stack
- **Language**: Python (FastMCP) — matches existing agent-server
- **Schema validation**: Pydantic models for tool inputs
- **Database access**: Tools query the existing PostgreSQL/MySQL backend via the data access API
- **Transport**: Stdio (agent-server spawns MCP servers as subprocesses) or streamable HTTP

### Security Boundaries
- Each MCP server connects to the database with row-level security scoped to the folder
- Prepare server: read/write on source tables, write on transform table
- Visualize server: read-only on transform table, write on charts collection
- Report server: read-only on transform table + charts, write on reports collection

### Error Handling
- All tools return structured error responses with actionable messages
- Quality rule failures return the specific rule ID, affected rows, and suggested fix
- Timeout: long operations (joins on large tables) have configurable timeouts with progress events
