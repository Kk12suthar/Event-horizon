import { memo } from 'react';
import { Handle, NodeResizer, Position, type Node, type NodeProps } from '@xyflow/react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { BarChart3, Image as ImageIcon, Table2, TrendingDown, TrendingUp } from 'lucide-react';
import type {
  ChartElement,
  GanttElement,
  ImageElement,
  KpiElement,
  LegendElement,
  NodeElement,
  PathElement,
  Rect,
  ShapeElement,
  TableElement,
  TextElement,
  VisualElement,
} from '@/types/visualDocument.generated';

export interface CanvasNodeData extends Record<string, unknown> {
  element: Exclude<VisualElement, { type?: 'edge' }>;
  pathRect?: Rect;
  onResizeEnd: (elementId: string, rect: Rect) => void;
}

export type CanvasFlowNode = Node<CanvasNodeData, 'visual'>;

const SWATCHES = ['#C16E43', '#E2A56F', '#D4D4D8', '#A1A1AA', '#71717A', '#F4F4F5'];
const tooltipStyle = {
  background: '#101010',
  border: '1px solid #343434',
  borderRadius: 8,
  color: '#F4F4F5',
  fontSize: 11,
};

function metricValue(value: number | string, format?: string, unit?: string | null) {
  if (typeof value !== 'number') return `${value}${unit ? ` ${unit}` : ''}`;
  let formatted: string;
  if (format === 'percent') formatted = `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}%`;
  else if (format === 'currency') {
    formatted = value.toLocaleString(undefined, { style: 'currency', currency: unit || 'USD' });
    return formatted;
  } else if (format === 'integer') formatted = Math.round(value).toLocaleString();
  else formatted = value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return `${formatted}${unit && format !== 'percent' ? ` ${unit}` : ''}`;
}

function NodeCard({ element }: { element: NodeElement }) {
  const isEvent = ['start', 'end', 'event'].includes(element.node_kind || '');
  const isGateway = ['gateway', 'decision'].includes(element.node_kind || '');
  return (
    <div className="flex h-full w-full items-center justify-center p-2">
      <div
        className={[
          'flex h-full w-full flex-col items-center justify-center border text-center shadow-lg',
          isEvent ? 'rounded-full' : isGateway ? 'rotate-45 rounded-md' : 'rounded-xl',
          element.node_kind === 'end' ? 'border-[#C16E43] bg-[#24150e]' : 'border-[#3A3A3A] bg-[#131313]',
        ].join(' ')}
      >
        <div className={isGateway ? '-rotate-45 px-4' : 'px-3'}>
          <div className="text-[13px] font-semibold leading-tight text-[#F4F4F5]">{element.label}</div>
          {element.sublabel && <div className="mt-1 text-[10px] leading-tight text-[#8A8A8A]">{element.sublabel}</div>}
          {element.metrics?.slice(0, 2).map((metric) => (
            <div key={`${metric.label}-${metric.value}`} className="mt-1 text-[9px] text-[#C7C7C7]">
              {metric.label}: {metricValue(metric.value, metric.format, metric.unit)}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function ShapeCard({ element }: { element: ShapeElement }) {
  const clip =
    element.shape === 'triangle'
      ? 'polygon(50% 0, 100% 100%, 0 100%)'
      : element.shape === 'diamond'
        ? 'polygon(50% 0, 100% 50%, 50% 100%, 0 50%)'
        : element.shape === 'arrow'
          ? 'polygon(0 28%, 68% 28%, 68% 0, 100% 50%, 68% 100%, 68% 72%, 0 72%)'
          : element.shape === 'star'
            ? 'polygon(50% 0,61% 35%,98% 35%,68% 57%,79% 94%,50% 72%,21% 94%,32% 57%,2% 35%,39% 35%)'
            : undefined;
  return (
    <div className="h-full w-full p-1">
      <div
        className={[
          'flex h-full w-full items-center justify-center border border-[#484848] bg-[#181818] px-3 text-center text-xs text-[#E4E4E7]',
          element.shape === 'ellipse' ? 'rounded-[999px]' : element.shape === 'cloud' ? 'rounded-[45%]' : 'rounded-lg',
        ].join(' ')}
        style={{ clipPath: clip, transform: `rotate(${element.rotation || 0}deg)` }}
      >
        <span style={{ transform: `rotate(-${element.rotation || 0}deg)` }}>{element.text}</span>
      </div>
    </div>
  );
}

function TextCard({ element }: { element: TextElement }) {
  const size = element.role === 'title' ? 'text-xl font-semibold' : element.role === 'caption' ? 'text-[11px]' : 'text-sm';
  return (
    <div className={`flex h-full w-full items-center whitespace-pre-wrap px-2 text-[#E4E4E7] ${size}`}>
      {element.text}
    </div>
  );
}

function KpiCard({ element }: { element: KpiElement }) {
  return (
    <div className="flex h-full w-full flex-col justify-between rounded-xl border border-[#343434] bg-[#121212] p-4 shadow-xl">
      <div className="text-[10px] font-medium uppercase tracking-[0.16em] text-[#8A8A8A]">{element.label}</div>
      <div className="truncate text-2xl font-semibold tabular-nums text-[#F4F4F5]">
        {metricValue(element.metric.value, element.metric.format, element.metric.unit)}
      </div>
      <div className="flex items-center gap-1 text-[10px] text-[#A1A1AA]">
        {element.trend === 'up' && <TrendingUp className="h-3 w-3 text-[#C16E43]" />}
        {element.trend === 'down' && <TrendingDown className="h-3 w-3" />}
        {element.delta ? `${element.delta.label} ${metricValue(element.delta.value, element.delta.format, element.delta.unit)}` : 'Grounded metric'}
      </div>
    </div>
  );
}

type ChartPoint = { label: string; value: number; series?: string | null };

function ChartCard({ element }: { element: ChartElement }) {
  const data = ((element as ChartElement & { data?: ChartPoint[] }).data || []).map((point) => ({
    label: point.label,
    value: Number(point.value || 0),
    series: point.series || '',
  }));
  const chartType = element.chart_type;
  const chart = data.length ? (
    chartType === 'pie' || chartType === 'donut' ? (
      <PieChart>
        <Pie data={data} dataKey="value" nameKey="label" innerRadius={chartType === 'donut' ? '45%' : 0} outerRadius="76%">
          {data.map((_, index) => <Cell key={index} fill={SWATCHES[index % SWATCHES.length]} />)}
        </Pie>
        <Tooltip contentStyle={tooltipStyle} />
      </PieChart>
    ) : chartType === 'line' ? (
      <LineChart data={data}>
        {element.show_grid && <CartesianGrid stroke="#292929" strokeDasharray="3 3" />}
        <XAxis dataKey="label" tick={{ fill: '#8A8A8A', fontSize: 9 }} tickLine={false} axisLine={false} />
        <YAxis tick={{ fill: '#8A8A8A', fontSize: 9 }} tickLine={false} axisLine={false} width={34} />
        <Tooltip contentStyle={tooltipStyle} />
        <Line type="monotone" dataKey="value" stroke="#C16E43" strokeWidth={2} dot={{ r: 2 }} />
      </LineChart>
    ) : chartType === 'area' ? (
      <AreaChart data={data}>
        {element.show_grid && <CartesianGrid stroke="#292929" strokeDasharray="3 3" />}
        <XAxis dataKey="label" tick={{ fill: '#8A8A8A', fontSize: 9 }} tickLine={false} axisLine={false} />
        <YAxis tick={{ fill: '#8A8A8A', fontSize: 9 }} tickLine={false} axisLine={false} width={34} />
        <Tooltip contentStyle={tooltipStyle} />
        <Area type="monotone" dataKey="value" stroke="#C16E43" fill="rgba(193,110,67,.25)" />
      </AreaChart>
    ) : (
      <BarChart data={data} layout={chartType === 'bar' ? 'vertical' : 'horizontal'}>
        {element.show_grid && <CartesianGrid stroke="#292929" strokeDasharray="3 3" />}
        {chartType === 'bar' ? (
          <>
            <XAxis type="number" tick={{ fill: '#8A8A8A', fontSize: 9 }} tickLine={false} axisLine={false} />
            <YAxis type="category" dataKey="label" tick={{ fill: '#8A8A8A', fontSize: 9 }} tickLine={false} axisLine={false} width={62} />
          </>
        ) : (
          <>
            <XAxis dataKey="label" tick={{ fill: '#8A8A8A', fontSize: 9 }} tickLine={false} axisLine={false} />
            <YAxis tick={{ fill: '#8A8A8A', fontSize: 9 }} tickLine={false} axisLine={false} width={34} />
          </>
        )}
        <Tooltip contentStyle={tooltipStyle} />
        <Bar dataKey="value" fill="#C16E43" radius={[3, 3, 0, 0]} />
      </BarChart>
    )
  ) : null;
  return (
    <div className="flex h-full w-full flex-col overflow-hidden rounded-xl border border-[#343434] bg-[#111111] p-3 shadow-xl">
      <div className="mb-1 flex items-center gap-2">
        <BarChart3 className="h-3.5 w-3.5 text-[#C16E43]" />
        <div className="truncate text-xs font-semibold text-[#F4F4F5]">{element.title}</div>
      </div>
      <div className="min-h-0 flex-1">
        {chart ? <ResponsiveContainer width="100%" height="100%">{chart}</ResponsiveContainer> : (
          <div className="flex h-full items-center justify-center text-[10px] text-[#71717A]">Waiting for grounded chart data</div>
        )}
      </div>
    </div>
  );
}

function GanttCard({ element }: { element: GanttElement }) {
  const dates = element.bars?.flatMap((bar) => [Date.parse(bar.start), Date.parse(bar.end)]).filter(Number.isFinite) || [];
  const min = dates.length ? Math.min(...dates) : 0;
  const max = dates.length ? Math.max(...dates) : min + 1;
  const span = Math.max(1, max - min);
  return (
    <div className="h-full w-full overflow-hidden rounded-xl border border-[#343434] bg-[#111111] p-3 shadow-xl">
      <div className="mb-2 text-xs font-semibold text-[#F4F4F5]">{element.title}</div>
      <div className="space-y-2 overflow-y-auto">
        {(element.bars || []).map((bar, index) => {
          const left = ((Date.parse(bar.start) - min) / span) * 100;
          const width = Math.max(4, ((Date.parse(bar.end) - Date.parse(bar.start)) / span) * 100);
          return (
            <div key={bar.id} className="grid grid-cols-[72px_1fr] items-center gap-2 text-[9px]">
              <span className="truncate text-[#A1A1AA]">{bar.label}</span>
              <div className="relative h-4 rounded bg-[#202020]">
                <div className="absolute inset-y-0 rounded" style={{ left: `${left}%`, width: `${Math.min(width, 100 - left)}%`, background: SWATCHES[index % SWATCHES.length] }}>
                  {bar.progress != null && <span className="block h-full rounded bg-white/20" style={{ width: `${Math.min(100, bar.progress)}%` }} />}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function TableCard({ element }: { element: TableElement }) {
  const rows = (element as TableElement & { rows?: Array<Record<string, unknown>> }).rows || [];
  return (
    <div className="flex h-full w-full flex-col overflow-hidden rounded-xl border border-[#343434] bg-[#111111] shadow-xl">
      <div className="flex items-center gap-2 border-b border-[#292929] px-3 py-2">
        <Table2 className="h-3.5 w-3.5 text-[#C16E43]" />
        <span className="truncate text-xs font-semibold">{element.title}</span>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        <table className="w-full border-collapse text-[9px]">
          <thead className="sticky top-0 bg-[#171717] text-[#A1A1AA]">
            <tr>{element.columns.map((column) => <th key={column.field} className="border-b border-[#292929] px-2 py-1.5 text-left font-medium">{column.header}</th>)}</tr>
          </thead>
          <tbody>
            {rows.slice(0, element.page_size || 10).map((row, index) => (
              <tr key={index} className="border-b border-[#222]">
                {element.columns.map((column) => <td key={column.field} className="max-w-[140px] truncate px-2 py-1.5 text-[#D4D4D8]">{String(row[column.field] ?? '-')}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
        {!rows.length && <div className="p-4 text-center text-[10px] text-[#71717A]">{element.columns.length} grounded columns</div>}
      </div>
    </div>
  );
}

function LegendCard({ element }: { element: LegendElement }) {
  return (
    <div className="h-full w-full rounded-lg border border-[#343434] bg-[#111111]/95 p-3 text-[10px]">
      {element.title && <div className="mb-2 font-semibold text-[#E4E4E7]">{element.title}</div>}
      <div className={element.orientation === 'horizontal' ? 'flex flex-wrap gap-3' : 'space-y-1.5'}>
        {element.entries.map((entry, index) => (
          <div key={`${entry.label}-${index}`} className="flex items-center gap-2 text-[#A1A1AA]">
            <span className={`h-2.5 w-2.5 ${entry.shape === 'dot' ? 'rounded-full' : 'rounded-sm'}`} style={{ background: SWATCHES[index % SWATCHES.length] }} />
            {entry.label}
          </div>
        ))}
      </div>
    </div>
  );
}

function PathCard({ element, rect }: { element: PathElement; rect?: Rect }) {
  const box = rect || { x: 0, y: 0, w: 1, h: 1 };
  const points = element.points.map((point) => `${point.x - box.x},${point.y - box.y}`).join(' ');
  return (
    <svg viewBox={`0 0 ${Math.max(1, box.w)} ${Math.max(1, box.h)}`} className="h-full w-full overflow-visible">
      <polyline points={points} fill={element.closed ? 'rgba(193,110,67,.12)' : 'none'} stroke="#C16E43" strokeWidth={element.tool === 'highlighter' ? 8 : element.tool === 'marker' ? 4 : 2} strokeLinecap="round" strokeLinejoin="round" opacity={element.tool === 'highlighter' ? 0.45 : 1} />
    </svg>
  );
}

function ImageCard({ element }: { element: ImageElement }) {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center rounded-xl border border-dashed border-[#484848] bg-[#111111] text-[#71717A]">
      <ImageIcon className="mb-2 h-6 w-6" />
      <span className="max-w-[80%] truncate text-[10px]">{element.asset_id}</span>
      <span className="text-[9px]">{element.origin || 'visual asset'}</span>
    </div>
  );
}

function VisualElementNodeComponent({ data, selected }: NodeProps<CanvasFlowNode>) {
  const element = data.element;
  const locked = Boolean(element.locked);
  const content =
    element.type === 'node' ? <NodeCard element={element as NodeElement} /> :
    element.type === 'shape' ? <ShapeCard element={element as ShapeElement} /> :
    element.type === 'text' ? <TextCard element={element as TextElement} /> :
    element.type === 'kpi' ? <KpiCard element={element as KpiElement} /> :
    element.type === 'chart' ? <ChartCard element={element as ChartElement} /> :
    element.type === 'gantt' ? <GanttCard element={element as GanttElement} /> :
    element.type === 'table' ? <TableCard element={element as TableElement} /> :
    element.type === 'legend' ? <LegendCard element={element as LegendElement} /> :
    element.type === 'path' ? <PathCard element={element as PathElement} rect={data.pathRect} /> :
    element.type === 'image' ? <ImageCard element={element as ImageElement} /> :
    <div className="flex h-full items-center justify-center rounded border border-[#343434] bg-[#111] text-xs">{element.id}</div>;

  return (
    <div className={`h-full w-full ${selected ? 'ring-2 ring-[#C16E43] ring-offset-2 ring-offset-black' : ''}`} aria-label={element.a11y_label || `${element.type} ${element.id}`}>
      <NodeResizer
        isVisible={selected && !locked && element.type !== 'path'}
        minWidth={40}
        minHeight={32}
        lineClassName="!border-[#C16E43]"
        handleClassName="!h-2 !w-2 !border-[#C16E43] !bg-black"
        onResizeEnd={(_, params) => data.onResizeEnd(element.id, { x: params.x, y: params.y, w: params.width, h: params.height })}
      />
      <Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-[#777] !bg-[#151515]" />
      {content}
      <Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-[#777] !bg-[#C16E43]" />
    </div>
  );
}

export const VisualElementNode = memo(VisualElementNodeComponent);
