import { createElement, useMemo } from 'react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  LineChart,
  Line,
  AreaChart,
  Area,
  PieChart,
  Pie,
  Cell,
  RadialBarChart,
  RadialBar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts';
import {
  BarChart3,
  LineChart as LineChartIcon,
  AreaChart as AreaChartIcon,
  PieChart as PieChartIcon,
  Activity,
  Plus,
  RotateCw,
  Sparkles,
  AlertCircle,
  TrendingUp,
  TrendingDown,
  Minus,
  Loader2,
  Trash2,
  type LucideIcon,
} from 'lucide-react';
import type { ArtifactState, ChartType, ChartWidget, WorkspaceMode } from '../../../types';
import { SPACE } from '../theme';

/**
 * ChartArtifact - the right artifact panel for Visualize (Dashboard) mode.
 *
 * Presentational only. Driven entirely by props; all actions delegate to
 * callbacks. It renders, top to bottom: a KPI strip, a chart canvas/grid, a
 * compact chart list, a selected-chart inspector, generated chart suggestions,
 * and the "Add chart" / "Regenerate" actions (Requirement 8.1). It renders one
 * of four states (Requirement 8.3-8.6):
 *
 *  - `empty`:    no charts yet - show chart suggestions derived from the
 *                transformed table so the user can kick one off (Req 8.3).
 *  - `skeleton`: charts are generating - chart skeletons + (the live activity
 *                trail lives in the chat thread, not here) (Req 8.4).
 *  - `ready`:    charts render cleanly and **not oversized** - every chart sits
 *                in a fixed-height responsive container (Req 8.5).
 *  - `error`:    a neutral inline error with a retry action (Req 8.6).
 *
 * Charts are drawn with `recharts` (already a dependency, used by
 * `components/ui/chart.tsx`) via `ResponsiveContainer` at a fixed height so they
 * never balloon to fill the panel.
 *
 * Uses only the monochrome SPACE tokens + lucide-react, matching the
 * conventions in SourcesPanel/TableArtifact (inline-style colors, hover
 * handlers, thin borders, compact density). No purple/blue, no gradients.
 *
 * DEFAULT export is compatible with the ArtifactPanel variant contract
 * (`{ mode, artifact, onClose }`) - it accepts a broader props interface where
 * those fields are optional and `charts`/`kpis`/`suggestions`/`state` may be
 * supplied directly by a parent.
 *
 * Requirements: 8.1 (KPI strip, chart canvas/grid, chart list, selected-chart
 * inspector, suggestions, Add chart/Regenerate), 8.2 (gating handled upstream),
 * 8.3 (empty → suggestions), 8.4 (skeleton while generating), 8.5 (clean, not
 * oversized), 8.6 (neutral inline error + retry).
 */

/** Visual state of the Visualize artifact panel. */
export type ChartArtifactState = 'empty' | 'skeleton' | 'ready' | 'error';

/** A single KPI in the top strip. */
export interface KpiItem {
  id?: string;
  stale?: boolean;
  /** Metric label, e.g. "Total revenue". */
  label: string;
  /** Formatted metric value, e.g. "$1.2M" or 4821. */
  value: string | number;
  /** Optional delta annotation rendered as a small trend pill. */
  delta?: { value: string; trend: 'up' | 'down' | 'neutral' };
}

/** A generated chart suggestion shown when the dashboard is empty. */
export interface ChartSuggestion {
  id: string;
  /** Short prompt-like label, e.g. "Revenue by region". */
  label: string;
  /** Optional one-line description. */
  description?: string;
  /** Suggested chart type (drives the leading icon). */
  chartType?: ChartType;
}

export interface ChartArtifactProps {
  /**
   * Which state to render. When omitted it is derived from the charts list
   * (`empty` when there are none, otherwise `ready`).
   */
  state?: ChartArtifactState;
  /** Active mode - accepted for the ArtifactPanel variant contract. */
  mode?: WorkspaceMode;
  /** Shared artifact snapshot - `charts` falls back to `artifact.charts`. */
  artifact?: ArtifactState;
  /** Charts to render in the canvas/grid + list. */
  charts?: ChartWidget[];
  /** Currently selected chart id (drives the inspector). */
  selectedChartId?: string | null;
  /** KPI strip items. */
  kpis?: KpiItem[];
  /** Chart suggestions shown in the empty state (and below the grid). */
  suggestions?: ChartSuggestion[];
  /** Error message shown in the `error` state. */
  error?: string | null;
  /** Create a new chart (Add chart action / suggestion activation). */
  onAddChart?: (suggestionId?: string) => void;
  /** Regenerate charts (whole dashboard) or a specific chart when an id is given. */
  onRegenerate?: (chartId?: string) => void;
  /** Select a chart for the inspector. */
  onSelectChart?: (chartId: string) => void;
  /** Delete a persisted chart from this session dashboard. */
  onDeleteChart?: (chartId: string) => Promise<void> | void;
  /** Retry after an error (defaults to {@link onRegenerate} when omitted). */
  onRetry?: () => void;
  /** Close affordance - accepted for the ArtifactPanel variant contract. */
  onClose?: () => void;
}

/**
 * Monochrome chart palette. White/light-gray is the only accent, so multi-series
 * charts (pie/radial categories) step down through grays rather than using hues.
 */
const CHART_GRAYS = ['#F4F4F5', '#A1A1AA', '#71717A', '#525252', '#3E3E3E', '#262626'] as const;

/** Resolve a chart's primary stroke/fill, defaulting to the light-gray accent. */
function chartColor(chart: ChartWidget): string {
  return chart.config?.primaryColor || SPACE.text;
}

/** Maps a chart type to its lucide icon (used in the list + suggestions). */
function chartTypeIcon(type?: ChartType): LucideIcon {
  switch (type) {
    case 'kpi':
      return Activity;
    case 'line':
      return LineChartIcon;
    case 'area':
      return AreaChartIcon;
    case 'pie':
    case 'radial':
      return PieChartIcon;
    case 'bar':
    default:
      return BarChart3;
  }
}

/** Section heading shared across the panel. */
function SectionLabel({ icon: Icon, children }: { icon?: LucideIcon; children: React.ReactNode }) {
  return (
    <div
      className="flex items-center gap-1.5 px-4 pb-1.5 pt-3 text-[11px] font-medium uppercase tracking-wide"
      style={{ color: SPACE.subtle }}
    >
      {Icon && <Icon className="h-3.5 w-3.5" />}
      {children}
    </div>
  );
}

/**
 * Renders the lucide icon for a chart type. Uses `createElement` so the icon
 * component (which is selected at call time) is never declared as a capitalized
 * local during render - keeping it a stable component reference.
 */
function ChartTypeIcon({
  type,
  className,
  style,
}: {
  type?: ChartType;
  className?: string;
  style?: React.CSSProperties;
}) {
  return createElement(chartTypeIcon(type), { className, style });
}

/** A compact action button (primary or outline) matching the preserved theme. */
function ActionButton({
  icon: Icon,
  label,
  variant,
  onClick,
}: {
  icon: LucideIcon;
  label: string;
  variant: 'primary' | 'outline';
  onClick?: () => void;
}) {
  const primary = variant === 'primary';
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!onClick}
      className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium outline-none transition-colors focus-visible:ring-1 disabled:opacity-40"
      style={{
        backgroundColor: primary ? SPACE.brand : 'transparent',
        color: primary ? SPACE.onBrand : SPACE.muted,
        border: primary ? 'none' : `1px solid ${SPACE.border}`,
        cursor: onClick ? 'pointer' : 'not-allowed',
      }}
      onMouseEnter={(e) => {
        if (!onClick) return;
        if (primary) e.currentTarget.style.backgroundColor = SPACE.brandHover;
        else {
          e.currentTarget.style.backgroundColor = SPACE.hover;
          e.currentTarget.style.color = SPACE.text;
        }
      }}
      onMouseLeave={(e) => {
        if (!onClick) return;
        if (primary) e.currentTarget.style.backgroundColor = SPACE.brand;
        else {
          e.currentTarget.style.backgroundColor = 'transparent';
          e.currentTarget.style.color = SPACE.muted;
        }
      }}
    >
      <Icon className="h-3.5 w-3.5" />
      {label}
    </button>
  );
}

/** Shared recharts tooltip styling so it stays on-theme (dark, thin border). */
const TOOLTIP_STYLES = {
  contentStyle: {
    backgroundColor: SPACE.panel,
    border: `1px solid ${SPACE.border}`,
    borderRadius: 8,
    fontSize: 11,
    color: SPACE.text,
  },
  labelStyle: { color: SPACE.muted },
  itemStyle: { color: SPACE.text },
} as const;

/**
 * Render a single chart's body inside a fixed-height ResponsiveContainer so it
 * fills the available width but never grows oversized (Requirement 8.5).
 */
export function ChartCanvas({ chart, height = 180 }: { chart: ChartWidget; height?: number }) {
  const color = chartColor(chart);
  const { config, data, type } = chart;
  const showGrid = config?.showGrid ?? true;
  const showLegend = config?.showLegend ?? false;
  const showTooltip = config?.showTooltip ?? true;

  if (!data || data.length === 0) {
    return (
      <div
        className="flex items-center justify-center rounded-lg text-[11px]"
        style={{ height, backgroundColor: SPACE.panel, border: `1px solid ${SPACE.border}`, color: SPACE.subtle }}
      >
        No data
      </div>
    );
  }

  if (type === 'kpi') {
    const point = data[0];
    const formatted = new Intl.NumberFormat(undefined, {
      notation: Math.abs(point.value) >= 10000 ? 'compact' : 'standard',
      maximumFractionDigits: 2,
    }).format(point.value);
    return (
      <div className="flex h-full min-h-[112px] flex-col justify-between py-1">
        <span className="text-[11px] font-medium uppercase tracking-wide" style={{ color: SPACE.subtle }}>
          {point.label || chart.name}
        </span>
        <strong className="break-words text-3xl font-semibold" style={{ color: SPACE.text }}>
          {formatted}
        </strong>
        <span className="text-[11px]" style={{ color: SPACE.muted }}>
          From the selected prepared table
        </span>
      </div>
    );
  }
  const axisProps = {
    stroke: SPACE.subtle,
    tick: { fill: SPACE.muted, fontSize: 10 },
    tickLine: false,
    axisLine: { stroke: SPACE.border },
  } as const;

  return (
    <ResponsiveContainer width="100%" height={height}>
      {type === 'bar' ? (
        <BarChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
          {showGrid && <CartesianGrid strokeDasharray="3 3" stroke={SPACE.border} vertical={false} />}
          <XAxis dataKey="label" {...axisProps} />
          <YAxis {...axisProps} />
          {showTooltip && <Tooltip cursor={{ fill: SPACE.hover }} {...TOOLTIP_STYLES} />}
          {showLegend && <Legend wrapperStyle={{ fontSize: 11, color: SPACE.muted }} />}
          <Bar dataKey="value" fill={color} radius={[3, 3, 0, 0]} maxBarSize={36} />
        </BarChart>
      ) : type === 'line' ? (
        <LineChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
          {showGrid && <CartesianGrid strokeDasharray="3 3" stroke={SPACE.border} vertical={false} />}
          <XAxis dataKey="label" {...axisProps} />
          <YAxis {...axisProps} />
          {showTooltip && <Tooltip {...TOOLTIP_STYLES} />}
          {showLegend && <Legend wrapperStyle={{ fontSize: 11, color: SPACE.muted }} />}
          <Line
            type={config?.lineType === 'straight' ? 'linear' : 'monotone'}
            dataKey="value"
            stroke={color}
            strokeWidth={2}
            dot={config?.showDots ? { r: 2, fill: color } : false}
          />
        </LineChart>
      ) : type === 'area' ? (
        <AreaChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
          <defs>
            <linearGradient id={`area-${chart.id}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={color} stopOpacity={config?.gradientOpacity ?? 0.3} />
              <stop offset="95%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          {showGrid && <CartesianGrid strokeDasharray="3 3" stroke={SPACE.border} vertical={false} />}
          <XAxis dataKey="label" {...axisProps} />
          <YAxis {...axisProps} />
          {showTooltip && <Tooltip {...TOOLTIP_STYLES} />}
          {showLegend && <Legend wrapperStyle={{ fontSize: 11, color: SPACE.muted }} />}
          <Area
            type={config?.lineType === 'straight' ? 'linear' : 'monotone'}
            dataKey="value"
            stroke={color}
            strokeWidth={2}
            fill={`url(#area-${chart.id})`}
          />
        </AreaChart>
      ) : type === 'pie' ? (
        <PieChart margin={{ top: 4, right: 4, left: 4, bottom: 4 }}>
          {showTooltip && <Tooltip {...TOOLTIP_STYLES} />}
          {showLegend && <Legend wrapperStyle={{ fontSize: 11, color: SPACE.muted }} />}
          <Pie
            data={data}
            dataKey="value"
            nameKey="label"
            cx="50%"
            cy="50%"
            outerRadius={Math.min(height / 2 - 8, 70)}
            innerRadius={config?.innerRadius ?? 0}
            stroke={SPACE.panelAlt}
            strokeWidth={1}
          >
            {data.map((_, i) => (
              <Cell key={i} fill={CHART_GRAYS[i % CHART_GRAYS.length]} />
            ))}
          </Pie>
        </PieChart>
      ) : (
        // radial
        <RadialBarChart
          data={data.map((d, i) => ({ ...d, fill: CHART_GRAYS[i % CHART_GRAYS.length] }))}
          cx="50%"
          cy="50%"
          innerRadius="30%"
          outerRadius="100%"
          margin={{ top: 4, right: 4, left: 4, bottom: 4 }}
        >
          {showTooltip && <Tooltip {...TOOLTIP_STYLES} />}
          {showLegend && <Legend wrapperStyle={{ fontSize: 11, color: SPACE.muted }} />}
          <RadialBar dataKey="value" background={{ fill: SPACE.panel }} cornerRadius={3} />
        </RadialBarChart>
      )}
    </ResponsiveContainer>
  );
}

/** The KPI strip - a horizontally scrollable row of metric cards. */
function KpiStrip({
  kpis,
  onDelete,
}: {
  kpis: KpiItem[];
  onDelete?: (id: string) => Promise<void> | void;
}) {
  return (
    <div className="flex gap-2 overflow-x-auto px-4 pt-4">
      {kpis.map((kpi, i) => {
        const TrendIcon =
          kpi.delta?.trend === 'up' ? TrendingUp : kpi.delta?.trend === 'down' ? TrendingDown : Minus;
        const trendColor =
          kpi.delta?.trend === 'up' ? SPACE.success : kpi.delta?.trend === 'down' ? SPACE.danger : SPACE.muted;
        return (
          <div
            key={i}
            className="min-w-[120px] flex-1 rounded-lg px-3 py-2.5"
            style={{ backgroundColor: SPACE.panel, border: `1px solid ${SPACE.border}` }}
          >
            <div className="flex items-start gap-1">
              <div className="min-w-0 flex-1 truncate text-[11px]" style={{ color: SPACE.muted }}>
                {kpi.label}
              </div>
              {kpi.id && onDelete && (
                <button
                  type="button"
                  onClick={() => void onDelete(kpi.id!)}
                  className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded outline-none transition-colors"
                  style={{ color: SPACE.subtle }}
                  aria-label={`Delete ${kpi.label}`}
                  title="Delete KPI"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              )}
            </div>
            <div className="mt-0.5 text-lg font-semibold" style={{ color: SPACE.text }}>
              {kpi.value}
            </div>
            {kpi.stale && (
              <div className="mt-0.5 text-[10px]" style={{ color: SPACE.subtle }}>
                Out of date
              </div>
            )}
            {kpi.delta && (
              <div className="mt-0.5 flex items-center gap-1 text-[11px]" style={{ color: trendColor }}>
                <TrendIcon className="h-3 w-3" />
                {kpi.delta.value}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

/** A compact chart-list row (selectable). */
function ChartListRow({
  chart,
  active,
  onSelect,
}: {
  chart: ChartWidget;
  active: boolean;
  onSelect?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      disabled={!onSelect}
      className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left outline-none transition-colors focus-visible:ring-1"
      style={{
        backgroundColor: active ? SPACE.hover : SPACE.panel,
        border: `1px solid ${active ? SPACE.muted : SPACE.border}`,
        cursor: onSelect ? 'pointer' : 'default',
      }}
      onMouseEnter={(e) => {
        if (onSelect && !active) e.currentTarget.style.backgroundColor = SPACE.hover;
      }}
      onMouseLeave={(e) => {
        if (onSelect && !active) e.currentTarget.style.backgroundColor = SPACE.panel;
      }}
    >
      <ChartTypeIcon
        type={chart.type}
        className="h-4 w-4 flex-shrink-0"
        style={{ color: active ? SPACE.text : SPACE.muted }}
      />
      <div className="min-w-0 flex-1">
        <div className="truncate text-xs font-medium" style={{ color: SPACE.text }}>
          {chart.name}
        </div>
        <div className="text-[11px] capitalize" style={{ color: SPACE.subtle }}>
          {chart.type} · {chart.data?.length ?? 0} points
        </div>
      </div>
    </button>
  );
}

/** A chart-suggestion chip. */
function SuggestionRow({
  suggestion,
  onActivate,
}: {
  suggestion: ChartSuggestion;
  onActivate?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onActivate}
      disabled={!onActivate}
      className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left outline-none transition-colors focus-visible:ring-1"
      style={{
        backgroundColor: SPACE.panel,
        border: `1px solid ${SPACE.border}`,
        cursor: onActivate ? 'pointer' : 'default',
      }}
      onMouseEnter={(e) => {
        if (onActivate) e.currentTarget.style.backgroundColor = SPACE.hover;
      }}
      onMouseLeave={(e) => {
        if (onActivate) e.currentTarget.style.backgroundColor = SPACE.panel;
      }}
    >
      <ChartTypeIcon
        type={suggestion.chartType}
        className="h-4 w-4 flex-shrink-0"
        style={{ color: SPACE.muted }}
      />
      <div className="min-w-0 flex-1">
        <div className="truncate text-xs font-medium" style={{ color: SPACE.text }}>
          {suggestion.label}
        </div>
        {suggestion.description && (
          <div className="truncate text-[11px]" style={{ color: SPACE.subtle }}>
            {suggestion.description}
          </div>
        )}
      </div>
      <Plus className="h-3.5 w-3.5 flex-shrink-0" style={{ color: SPACE.subtle }} />
    </button>
  );
}

/** Skeleton chart cards for the generating state. */
function ChartSkeletonGrid() {
  return (
    <div className="space-y-2 px-4 pt-3">
      <div className="flex items-center gap-2 text-xs" style={{ color: SPACE.muted }}>
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        Generating charts…
      </div>
      {Array.from({ length: 2 }).map((_, i) => (
        <div
          key={i}
          className="rounded-lg p-3"
          style={{ backgroundColor: SPACE.panel, border: `1px solid ${SPACE.border}` }}
        >
          <div className="mb-3 h-3 w-1/3 animate-pulse rounded" style={{ backgroundColor: SPACE.hover }} />
          <div className="flex h-[140px] items-end gap-2">
            {[60, 85, 45, 70, 95, 55, 80].map((h, j) => (
              <div
                key={j}
                className="flex-1 animate-pulse rounded-t"
                style={{ height: `${h}%`, backgroundColor: SPACE.hover }}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export function ChartArtifact({
  state,
  artifact,
  charts: chartsProp,
  selectedChartId,
  kpis = [],
  suggestions = [],
  error,
  onAddChart,
  onRegenerate,
  onSelectChart,
  onDeleteChart,
  onRetry,
}: ChartArtifactProps) {
  const charts = useMemo(
    () => chartsProp ?? artifact?.charts ?? [],
    [chartsProp, artifact],
  );

  const kpiCharts = useMemo(() => charts.filter((chart) => chart.type === 'kpi'), [charts]);
  const visualCharts = useMemo(() => charts.filter((chart) => chart.type !== 'kpi'), [charts]);
  const resolvedKpis = useMemo<KpiItem[]>(
    () => [
      ...kpis,
      ...kpiCharts.map((chart) => ({
        id: chart.id,
        stale: chart.stale,
        label: chart.name,
        value: new Intl.NumberFormat(undefined, {
          notation: Math.abs(chart.data[0]?.value || 0) >= 10000 ? 'compact' : 'standard',
          maximumFractionDigits: 2,
        }).format(chart.data[0]?.value || 0),
      })),
    ],
    [kpiCharts, kpis],
  );

  // Derive the state when not explicitly provided.
  const resolvedState: ChartArtifactState = state ?? (charts.length === 0 ? 'empty' : 'ready');

  const selectedChart = useMemo(
    () => visualCharts.find((chart) => chart.id === selectedChartId) ?? visualCharts[0] ?? null,
    [selectedChartId, visualCharts],
  );

  // --- Error: neutral inline error + retry (Requirement 8.6) ---
  if (resolvedState === 'error') {
    return (
      <div
        className="flex h-full flex-col items-center justify-center px-8 text-center"
        style={{ backgroundColor: SPACE.panelAlt }}
      >
        <div
          className="mb-3 flex h-11 w-11 items-center justify-center rounded-xl"
          style={{
            backgroundColor: 'rgba(244, 244, 245, 0.06)',
            border: `1px solid ${SPACE.danger}`,
            color: SPACE.danger,
          }}
        >
          <AlertCircle className="h-5 w-5" />
        </div>
        <div className="text-sm font-medium" style={{ color: SPACE.danger }}>
          Chart generation failed
        </div>
        <p className="mt-1 max-w-[260px] text-xs" style={{ color: SPACE.muted }}>
          {error || 'Something went wrong while building the charts.'}
        </p>
        <div className="mt-4">
          <ActionButton icon={RotateCw} label="Retry" variant="primary" onClick={onRetry || onRegenerate} />
        </div>
      </div>
    );
  }

  // --- Skeleton: charts generating (Requirement 8.4) ---
  if (resolvedState === 'skeleton') {
    return (
      <div className="flex h-full flex-col overflow-y-auto" style={{ backgroundColor: SPACE.panelAlt }}>
        {resolvedKpis.length > 0 && <KpiStrip kpis={resolvedKpis} onDelete={onDeleteChart} />}
        <ChartSkeletonGrid />
      </div>
    );
  }

  // --- Empty: suggestions derived from the transformed table (Requirement 8.3) ---
  if (resolvedState === 'empty') {
    return (
      <div className="flex h-full flex-col overflow-y-auto" style={{ backgroundColor: SPACE.panelAlt }}>
        {resolvedKpis.length > 0 && <KpiStrip kpis={resolvedKpis} onDelete={onDeleteChart} />}

        <div className="flex flex-col items-center px-8 pt-8 text-center">
          <div
            className="mb-3 flex h-11 w-11 items-center justify-center rounded-xl"
            style={{ backgroundColor: SPACE.panel, border: `1px solid ${SPACE.border}`, color: SPACE.text }}
          >
            <Activity className="h-5 w-5" strokeWidth={1.75} />
          </div>
          <div className="text-sm font-medium" style={{ color: SPACE.text }}>
            No charts yet
          </div>
          <p className="mt-1 max-w-[260px] text-xs" style={{ color: SPACE.muted }}>
            Ask in the chat for a chart, or start from a suggestion below.
          </p>
          <div className="mt-4">
            <ActionButton icon={Plus} label="Add chart" variant="primary" onClick={onAddChart ? () => onAddChart() : undefined} />
          </div>
        </div>

        {suggestions.length > 0 && (
          <>
            <SectionLabel icon={Sparkles}>Suggestions</SectionLabel>
            <div className="space-y-1.5 px-4 pb-4">
              {suggestions.map((s) => (
                <SuggestionRow
                  key={s.id}
                  suggestion={s}
                  onActivate={onAddChart ? () => onAddChart(s.id) : undefined}
                />
              ))}
            </div>
          </>
        )}
      </div>
    );
  }

  // --- Ready: KPI strip + canvas + list + inspector + suggestions (Req 8.1, 8.5) ---
  return (
    <div className="flex h-full flex-col overflow-y-auto" style={{ backgroundColor: SPACE.panelAlt }}>
      {/* Action bar */}
      <div
        className="flex flex-shrink-0 items-center gap-2 border-b px-4 py-2.5"
        style={{ borderColor: SPACE.border }}
      >
        <span className="text-sm font-medium" style={{ color: SPACE.text }}>
          Dashboard
        </span>
        <span className="text-[11px]" style={{ color: SPACE.subtle }}>
          {charts.length} saved item{charts.length === 1 ? '' : 's'}
        </span>
        <div className="ml-auto flex items-center gap-1.5">
          <ActionButton
            icon={RotateCw}
            label="Regenerate"
            variant="outline"
            onClick={onRegenerate ? () => onRegenerate() : undefined}
          />
          <ActionButton
            icon={Plus}
            label="Add chart"
            variant="primary"
            onClick={onAddChart ? () => onAddChart() : undefined}
          />
        </div>
      </div>

      {/* KPI strip */}
      {resolvedKpis.length > 0 && <KpiStrip kpis={resolvedKpis} onDelete={onDeleteChart} />}

      {/* Selected-chart inspector (larger, on top) */}
      {selectedChart && (
        <>
          <SectionLabel icon={chartTypeIcon(selectedChart.type)}>{selectedChart.name}</SectionLabel>
          <div className="px-4">
            <div
              className="rounded-lg p-3"
              style={{ backgroundColor: SPACE.panel, border: `1px solid ${SPACE.border}` }}
            >
              <ChartCanvas chart={selectedChart} height={220} />
            </div>
          </div>
        </>
      )}

      {/* Chart canvas/grid (all charts, compact) */}
      {visualCharts.length > 0 && <SectionLabel icon={BarChart3}>Charts</SectionLabel>}
      <div className="grid grid-cols-1 gap-2 px-4">
        {visualCharts.map((chart) => (
          <div
            key={chart.id}
            className="rounded-lg p-3 transition-colors"
            style={{
              backgroundColor: SPACE.panel,
              border: `1px solid ${chart.id === selectedChart?.id ? SPACE.muted : SPACE.border}`,
            }}
          >
            <div className="mb-2 flex items-center gap-2">
              <span className="truncate text-xs font-medium" style={{ color: SPACE.text }}>
                {chart.name}
              </span>
              {chart.stale && (
                <span
                  className="flex-shrink-0 rounded border px-1.5 py-0.5 text-[10px]"
                  style={{ borderColor: SPACE.border, color: SPACE.subtle }}
                >
                  Out of date
                </span>
              )}
              <div className="ml-auto flex items-center gap-1">
                <button
                  type="button"
                  onClick={onRegenerate ? () => onRegenerate(chart.id) : undefined}
                  disabled={!onRegenerate}
                  aria-label={`Regenerate ${chart.name}`}
                  title="Regenerate chart"
                  className="rounded-md p-1 outline-none transition-colors disabled:opacity-40"
                  style={{ color: SPACE.muted, cursor: onRegenerate ? 'pointer' : 'not-allowed' }}
                  onMouseEnter={(e) => {
                    if (onRegenerate) e.currentTarget.style.color = SPACE.text;
                  }}
                  onMouseLeave={(e) => {
                    if (onRegenerate) e.currentTarget.style.color = SPACE.muted;
                  }}
                >
                  <RotateCw className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  onClick={onDeleteChart ? () => void onDeleteChart(chart.id) : undefined}
                  disabled={!onDeleteChart}
                  aria-label={`Delete ${chart.name}`}
                  title="Delete chart"
                  className="rounded-md p-1 outline-none transition-colors disabled:opacity-40"
                  style={{ color: SPACE.muted, cursor: onDeleteChart ? 'pointer' : 'not-allowed' }}
                  onMouseEnter={(event) => {
                    if (onDeleteChart) event.currentTarget.style.color = SPACE.text;
                  }}
                  onMouseLeave={(event) => {
                    if (onDeleteChart) event.currentTarget.style.color = SPACE.muted;
                  }}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
            <ChartCanvas chart={chart} height={160} />
          </div>
        ))}
      </div>

      {/* Chart list (compact, selectable) */}
      {visualCharts.length > 0 && (
        <>
          <SectionLabel>All charts ({visualCharts.length})</SectionLabel>
          <div className="space-y-1.5 px-4">
            {visualCharts.map((chart) => (
              <ChartListRow
                key={chart.id}
                chart={chart}
                active={chart.id === selectedChart?.id}
                onSelect={onSelectChart ? () => onSelectChart(chart.id) : undefined}
              />
            ))}
          </div>
        </>
      )}

      {/* Suggestions for more charts */}
      {suggestions.length > 0 && (
        <>
          <SectionLabel icon={Sparkles}>Suggestions</SectionLabel>
          <div className="space-y-1.5 px-4 pb-4">
            {suggestions.map((s) => (
              <SuggestionRow
                key={s.id}
                suggestion={s}
                onActivate={onAddChart ? () => onAddChart(s.id) : undefined}
              />
            ))}
          </div>
        </>
      )}

      <div className="pb-4" />
    </div>
  );
}

export default ChartArtifact;
