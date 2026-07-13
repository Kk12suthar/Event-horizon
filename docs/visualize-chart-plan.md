# Visualize Panel — Chart UI & Functionality Plan

## Core Concept

The right artifact panel in Visualize mode becomes a **dynamic chart dashboard**. Charts are created via the chat (user requests or LLM auto-generates them), stored in app state, and rendered responsively based on how many exist.

---

## 1. Chart Data Model

```typescript
interface ChartSpec {
  id: string;
  title: string;
  type: 'line' | 'bar' | 'area' | 'pie' | 'donut' | 'scatter' | 'radar';
  /** Column from the transformed table used as the X axis / category */
  xField: string;
  /** One or more columns used as the Y axis / values */
  yFields: string[];
  /** Table ID this chart pulls data from */
  sourceTableId: string;
  /** Optional: filters, sorting, grouping applied before charting */
  transforms?: ChartTransform[];
  /** Optional: color overrides, legend position, etc. */
  options?: ChartOptions;
  /** When it was created/last updated */
  createdAt: string;
}
```

The LLM produces a `ChartSpec` JSON. The frontend renders it with real data from the table. No pre-rendered images — the charts are live and interactive.

---

## 2. How Charts Get Created

| Trigger | Flow |
|---------|------|
| **User asks in chat** ("show revenue by region as a bar chart") | LLM calls a tool → returns a `ChartSpec` → frontend renders it in the panel |
| **LLM auto-suggests** (after a transform completes) | Completion event includes chart specs as artifacts → appended to chart list |
| **User edits** (future: click chart → edit axis/type) | Local update to the `ChartSpec`, no LLM round-trip needed |

The agent-server's Visualize agent will have a **`create_chart` tool** that outputs the ChartSpec JSON. The SSE stream carries it as an `artifact` event:

```json
{ "type": "artifact", "artifact_type": "chart", "data": { ...ChartSpec } }
```

The `useAgentChat` hook (in the `onEvent` handler) detects `artifact_type === 'chart'` and pushes it into `appState.addChart(spec)`.

---

## 3. Responsive Layout (1–3+ charts)

| Count | Layout |
|-------|--------|
| **1 chart** | Full-width, full-height of the panel. Maximum visibility. |
| **2 charts** | Stacked vertically, 50/50 split. |
| **3 charts** | Top row: 2 charts side-by-side. Bottom: 1 full-width. |
| **4+ charts** | 2-column grid, scrollable. Each card has a fixed min-height (~220px). |

The layout uses CSS grid with `auto-fill` / `minmax` so it's purely count-driven — no manual config.

---

## 4. Chart Rendering Stack

**Library: Recharts** (already commonly used in React/Vite projects, lightweight, composable)

- `<ResponsiveContainer>` wraps every chart for fluid sizing
- Each chart type maps to its Recharts component (`LineChart`, `BarChart`, `AreaChart`, `PieChart`, etc.)
- Data is fetched from the table rows in `appState.tables` using `sourceTableId` + `xField` / `yFields`
- Charts update live when the underlying table data changes (e.g., after re-running a transform)

---

## 5. Component Architecture

```
ArtifactPanel (mode='visualize')
└── ChartDashboard
    ├── ChartGrid (responsive layout wrapper)
    │   ├── ChartCard (title, type icon, overflow menu)
    │   │   └── DynamicChart (renders the correct Recharts component by type)
    │   ├── ChartCard ...
    │   └── ChartCard ...
    └── EmptyChartState ("Ask for a chart in the chat")
```

### ChartCard features:
- Title bar with chart type icon
- Overflow menu: delete, change type, expand (full-panel view)
- Hover: shows axis labels, tooltips
- Click a data point: optional drill-down (future)

### DynamicChart switch:
```typescript
function DynamicChart({ spec, data }: { spec: ChartSpec; data: Row[] }) {
  switch (spec.type) {
    case 'line':   return <LineChart ... />;
    case 'bar':    return <BarChart ... />;
    case 'area':   return <AreaChart ... />;
    case 'pie':    return <PieChart ... />;
    // etc.
  }
}
```

---

## 6. Data Flow

```
User chat query
    → Visualize agent (agent-server, has access to table schema + data)
    → Agent decides chart type, picks columns
    → Returns ChartSpec via tool/artifact event
    → Frontend receives via SSE
    → appState.charts updated
    → ChartDashboard re-renders with live table data
```

The chart does NOT embed data in the spec — it references the table by ID and pulls live rows. If the table gets re-transformed, charts auto-update.

---

## 7. What the Backend (MCP/Agent) Needs to Provide (future)

| Piece | Role |
|-------|------|
| **`create_chart` tool** | LLM tool that outputs a `ChartSpec` JSON given a user request + table schema |
| **Table schema context** | The Visualize agent needs access to column names, types, and sample rows to pick the right chart |
| **`update_chart` tool** | Modify an existing chart (change type, axis, filters) |
| **`delete_chart` tool** | Remove a chart from the dashboard |

These will be MCP tools registered on the agent-server. For now, the frontend is the only piece being built — it will render any valid `ChartSpec` it receives.

---

## 8. Empty / Loading States

- **No charts yet**: "Ask for a visualization in the chat. Try: *Show monthly revenue as a line chart*" + example chips
- **Chart loading**: Skeleton with a gentle pulse (same style as table loading)
- **Chart error** (bad data/missing column): Subtle error card with the reason and a "Retry" action

---

## 9. Implementation Checklist (UI only, no backend yet)

1. `ChartSpec` type definition in `types/index.ts`
2. `ChartDashboard` component (layout grid + empty state)
3. `ChartCard` component (title, menu, container)
4. `DynamicChart` component (Recharts switch by type)
5. `useAgentChat` updated to detect `artifact_type === 'chart'` events and push to `appState.addChart`
6. `appState` already has `charts` + `addChart` — will be used as-is
7. Replace the existing `ChartArtifact` lazy import in `ArtifactPanel` with the new `ChartDashboard`

---

## 10. Design Principles

- **Data-driven**: Everything renders from `ChartSpec` — no hardcoded dashboards or static images
- **Live**: Charts pull from table data in real-time; table updates = chart updates
- **Progressive**: 1 chart fills the panel; more charts auto-grid without config
- **Chat-first**: Charts are always created/modified through conversation with the Visualize agent
- **Monochrome SPACE tokens**: Consistent with the rest of the workspace UI (white/gray, no purple/blue)
