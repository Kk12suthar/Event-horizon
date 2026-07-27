/**
 * GENERATED FILE - DO NOT EDIT.
 *
 * Source of truth: shared/visual_document.py
 * Regenerate with: python shared/visual_schema_export.py
 *
 * Wire format is snake_case to match the FastAPI payloads exactly.
 */

/** Canvas limits mirrored from the Python schema. */
export const VISUAL_LIMITS = {
  SCHEMA_VERSION: "1.0",
  CANVAS_MIN: -100000.0,
  CANVAS_MAX: 100000.0,
  MIN_ELEMENT_SIZE: 8.0,
  MAX_ELEMENT_SIZE: 20000.0,
  MIN_ZOOM: 0.05,
  MAX_ZOOM: 8.0,
  MAX_ELEMENTS: 2000,
  MAX_HISTORY: 200,
} as const;

export interface AddElementOp {
  op?: "add_element";
  element: NodeElement | EdgeElement | ChartElement | KpiElement | TableElement | GanttElement | TextElement | ShapeElement | PathElement | ImageElement | LegendElement;
}

export interface AddLayerOp {
  op?: "add_layer";
  layer: Layer;
}

export interface ChartDataPoint {
  label: string;
  value: number;
  series?: string | null;
}

export interface ChartElement {
  id: string;
  layer_id: string;
  group_id?: string | null;
  z?: number;
  locked?: boolean;
  hidden?: boolean;
  a11y_label?: string | null;
  style?: StyleTokens;
  meta?: ElementMeta;
  type?: "chart";
  rect: Rect;
  chart_type: "bar" | "column" | "line" | "area" | "pie" | "donut" | "scatter" | "heatmap" | "waterfall" | "funnel" | "sankey" | "treemap" | "radar" | "boxplot";
  title: string;
  x_field: string;
  y_fields: string[];
  data?: ChartDataPoint[];
  series_field?: string | null;
  stacked?: boolean;
  show_grid?: boolean;
  show_legend?: boolean;
  show_tooltip?: boolean;
  row_limit?: number;
  palette?: ("series-1" | "series-2" | "series-3" | "series-4" | "series-5" | "series-6" | "neutral" | "accent" | "success" | "warning" | "danger")[];
  provenance: Provenance;
}

/** One applied batch of ops plus the inverse needed to undo it. */
export interface Commit {
  id: string;
  revision: number;
  at: string;
  author: string;
  author_kind?: "user" | "agent" | "system";
  label?: string;
  ops?: (AddElementOp | RemoveElementOp | UpdateElementOp | MoveElementsOp | ResizeElementOp | SetStyleOp | SetLayerOp | ReorderElementOp | AddLayerOp | UpdateLayerOp | RemoveLayerOp | CreateGroupOp | UngroupOp | SetViewportOp | SetSelectionOp | SetTitleOp)[];
  inverse_ops?: (AddElementOp | RemoveElementOp | UpdateElementOp | MoveElementsOp | ResizeElementOp | SetStyleOp | SetLayerOp | ReorderElementOp | AddLayerOp | UpdateLayerOp | RemoveLayerOp | CreateGroupOp | UngroupOp | SetViewportOp | SetSelectionOp | SetTitleOp)[];
}

export interface CreateGroupOp {
  op?: "create_group";
  group: Group;
}

export interface DocumentMetadata {
  id: string;
  project_id: string;
  folder_id: string;
  session_id?: string | null;
  title: string;
  schema_version?: "1.0";
  revision?: number;
  created_by?: string | null;
  created_at?: string;
  updated_at?: string;
  updated_by?: string | null;
  source_table_ids?: string[];
  source_revision?: number | null;
}

/** Edges have no rect - geometry is derived from endpoints plus waypoints. */
export interface EdgeElement {
  id: string;
  layer_id: string;
  group_id?: string | null;
  z?: number;
  locked?: boolean;
  hidden?: boolean;
  a11y_label?: string | null;
  style?: StyleTokens;
  meta?: ElementMeta;
  type?: "edge";
  source_id: string;
  target_id: string;
  source_handle?: "top" | "right" | "bottom" | "left" | null;
  target_handle?: "top" | "right" | "bottom" | "left" | null;
  edge_kind?: "sequence" | "conditional" | "message" | "dependency" | "association" | "rework";
  label?: string | null;
  marker?: "none" | "arrow" | "arrow-both" | "dot";
  routing?: "straight" | "smoothstep" | "bezier" | "orthogonal";
  waypoints?: Point[];
  metrics?: Metric[];
  provenance?: Provenance | null;
}

/** Server-maintained audit fields. Tools never need to send these. */
export interface ElementMeta {
  created_at?: string | null;
  created_by?: string | null;
  updated_at?: string | null;
  updated_by?: string | null;
  revision?: number;
}

export interface GanttBar {
  id: string;
  label: string;
  lane: string;
  start: string;
  end: string;
  progress?: number | null;
  swatch?: "series-1" | "series-2" | "series-3" | "series-4" | "series-5" | "series-6" | "neutral" | "accent" | "success" | "warning" | "danger";
  depends_on?: string[];
}

export interface GanttElement {
  id: string;
  layer_id: string;
  group_id?: string | null;
  z?: number;
  locked?: boolean;
  hidden?: boolean;
  a11y_label?: string | null;
  style?: StyleTokens;
  meta?: ElementMeta;
  type?: "gantt";
  rect: Rect;
  title: string;
  bars?: GanttBar[];
  time_unit?: "hour" | "day" | "week" | "month" | "quarter" | "year";
  show_dependencies?: boolean;
  provenance: Provenance;
}

export interface Group {
  id: string;
  name: string;
  element_ids?: string[];
  locked?: boolean;
}

export interface ImageElement {
  id: string;
  layer_id: string;
  group_id?: string | null;
  z?: number;
  locked?: boolean;
  hidden?: boolean;
  a11y_label?: string | null;
  style?: StyleTokens;
  meta?: ElementMeta;
  type?: "image";
  rect: Rect;
  asset_id: string;
  origin?: "upload" | "generated" | "export";
  prompt?: string | null;
  fit?: "contain" | "cover" | "fill";
}

export interface KpiElement {
  id: string;
  layer_id: string;
  group_id?: string | null;
  z?: number;
  locked?: boolean;
  hidden?: boolean;
  a11y_label?: string | null;
  style?: StyleTokens;
  meta?: ElementMeta;
  type?: "kpi";
  rect: Rect;
  label: string;
  metric: Metric;
  delta?: Metric | null;
  trend?: "none" | "up" | "down" | "flat";
  provenance: Provenance;
}

export interface Layer {
  id: string;
  name: string;
  index?: number;
  visible?: boolean;
  locked?: boolean;
  kind?: "semantic" | "data" | "freeform" | "annotation" | "background";
}

export interface LegendElement {
  id: string;
  layer_id: string;
  group_id?: string | null;
  z?: number;
  locked?: boolean;
  hidden?: boolean;
  a11y_label?: string | null;
  style?: StyleTokens;
  meta?: ElementMeta;
  type?: "legend";
  rect: Rect;
  title?: string | null;
  entries: LegendEntry[];
  orientation?: "vertical" | "horizontal";
}

export interface LegendEntry {
  label: string;
  swatch?: "series-1" | "series-2" | "series-3" | "series-4" | "series-5" | "series-6" | "neutral" | "accent" | "success" | "warning" | "danger";
  shape?: "square" | "line" | "dashed-line" | "dot";
}

/** A single grounded number rendered inside a semantic element. */
export interface Metric {
  label: string;
  value: number | string;
  unit?: string | null;
  format?: "raw" | "integer" | "decimal" | "percent" | "currency" | "duration";
}

export interface MoveElementsOp {
  op?: "move_elements";
  element_ids: string[];
  dx?: number;
  dy?: number;
}

export interface NodeElement {
  id: string;
  layer_id: string;
  group_id?: string | null;
  z?: number;
  locked?: boolean;
  hidden?: boolean;
  a11y_label?: string | null;
  style?: StyleTokens;
  meta?: ElementMeta;
  type?: "node";
  rect: Rect;
  node_kind?: "task" | "event" | "gateway" | "decision" | "start" | "end" | "entity" | "actor" | "lane" | "milestone" | "annotation" | "generic";
  label: string;
  sublabel?: string | null;
  metrics?: Metric[];
  provenance?: Provenance | null;
  parent_id?: string | null;
}

/** Freeform stroke. Bounding box is derived, never authored. */
export interface PathElement {
  id: string;
  layer_id: string;
  group_id?: string | null;
  z?: number;
  locked?: boolean;
  hidden?: boolean;
  a11y_label?: string | null;
  style?: StyleTokens;
  meta?: ElementMeta;
  type?: "path";
  points: Point[];
  tool?: "pen" | "marker" | "highlighter";
  closed?: boolean;
  smoothing?: number;
}

export interface Point {
  x: number;
  y: number;
}

/** Where the numbers came from. Required on every data-bearing element. */
export interface Provenance {
  source_table_id: string;
  folder_id?: string | null;
  transform_revision?: number | null;
  columns?: string[];
  aggregation?: "none" | "sum" | "avg" | "min" | "max" | "count" | "median";
  filters?: ProvenanceFilter[];
  query_id?: string | null;
  generated_at?: string | null;
}

export interface ProvenanceFilter {
  field: string;
  op: "eq" | "neq" | "gt" | "gte" | "lt" | "lte" | "in" | "not_in" | "contains" | "between";
  value?: string | number | boolean | (string | number | boolean | null)[] | null;
}

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface RemoveElementOp {
  op?: "remove_element";
  element_id: string;
}

export interface RemoveLayerOp {
  op?: "remove_layer";
  layer_id: string;
}

export interface ReorderElementOp {
  op?: "reorder_element";
  element_id: string;
  z: number;
}

export interface ResizeElementOp {
  op?: "resize_element";
  element_id: string;
  rect: Rect;
}

export interface SetLayerOp {
  op?: "set_layer";
  element_ids: string[];
  layer_id: string;
}

export interface SetSelectionOp {
  op?: "set_selection";
  element_ids?: string[];
}

export interface SetStyleOp {
  op?: "set_style";
  element_ids: string[];
  style?: Record<string, unknown>;
}

export interface SetTitleOp {
  op?: "set_title";
  title: string;
}

export interface SetViewportOp {
  op?: "set_viewport";
  zoom?: number | null;
  x?: number | null;
  y?: number | null;
}

export interface ShapeElement {
  id: string;
  layer_id: string;
  group_id?: string | null;
  z?: number;
  locked?: boolean;
  hidden?: boolean;
  a11y_label?: string | null;
  style?: StyleTokens;
  meta?: ElementMeta;
  type?: "shape";
  rect: Rect;
  shape?: "rect" | "ellipse" | "triangle" | "diamond" | "arrow" | "line" | "star" | "cloud" | "callout" | "bracket";
  text?: string | null;
  rotation?: number;
}

/** Closed style vocabulary. No raw CSS, colors, or font names allowed. */
export interface StyleTokens {
  fill?: "transparent" | "surface" | "surface-muted" | "surface-raised" | "surface-inverted" | "accent" | "accent-muted" | "success" | "warning" | "danger" | "info";
  stroke?: "none" | "subtle" | "default" | "strong" | "accent" | "success" | "warning" | "danger" | "info";
  stroke_width?: "none" | "thin" | "regular" | "thick";
  stroke_dash?: "solid" | "dashed" | "dotted";
  text?: "caption" | "label" | "body-sm" | "body" | "heading-sm" | "heading" | "heading-lg" | "mono";
  text_align?: "left" | "center" | "right";
  corner?: "sharp" | "soft" | "round" | "pill";
  shadow?: "none" | "soft" | "raised";
  emphasis?: "none" | "highlight" | "dim" | "outline";
  opacity?: number;
}

export interface TableColumn {
  field: string;
  header: string;
  align?: "left" | "center" | "right";
  format?: "raw" | "integer" | "decimal" | "percent" | "currency" | "duration";
}

export interface TableElement {
  id: string;
  layer_id: string;
  group_id?: string | null;
  z?: number;
  locked?: boolean;
  hidden?: boolean;
  a11y_label?: string | null;
  style?: StyleTokens;
  meta?: ElementMeta;
  type?: "table";
  rect: Rect;
  title: string;
  columns: TableColumn[];
  page_size?: number;
  provenance: Provenance;
}

export interface TextElement {
  id: string;
  layer_id: string;
  group_id?: string | null;
  z?: number;
  locked?: boolean;
  hidden?: boolean;
  a11y_label?: string | null;
  style?: StyleTokens;
  meta?: ElementMeta;
  type?: "text";
  rect: Rect;
  text: string;
  role?: "note" | "title" | "caption" | "callout";
}

export interface UngroupOp {
  op?: "ungroup";
  group_id: string;
}

/** Partial update. The result is re-validated against the element model, so */
export interface UpdateElementOp {
  op?: "update_element";
  element_id: string;
  patch?: Record<string, unknown>;
}

export interface UpdateLayerOp {
  op?: "update_layer";
  layer_id: string;
  patch?: Record<string, unknown>;
}

export interface Viewport {
  zoom?: number;
  x?: number;
  y?: number;
  selected_ids?: string[];
}

export interface VisualDocument {
  metadata: DocumentMetadata;
  viewport?: Viewport;
  layers?: Layer[];
  groups?: Group[];
  elements?: (NodeElement | EdgeElement | ChartElement | KpiElement | TableElement | GanttElement | TextElement | ShapeElement | PathElement | ImageElement | LegendElement)[];
  history?: Commit[];
  redo_stack?: Commit[];
}

export type VisualElement = NodeElement | EdgeElement | ChartElement | KpiElement | TableElement | GanttElement | TextElement | ShapeElement | PathElement | ImageElement | LegendElement;

export type VisualElementType = VisualElement['type'];

export type VisualOp = AddElementOp | RemoveElementOp | UpdateElementOp | MoveElementsOp | ResizeElementOp | SetStyleOp | SetLayerOp | ReorderElementOp | AddLayerOp | UpdateLayerOp | RemoveLayerOp | CreateGroupOp | UngroupOp | SetViewportOp | SetSelectionOp | SetTitleOp;

export type VisualOpName = VisualOp['op'];
