import {
  Wand2,
  Table2,
  ListChecks,
  ArrowRight,
  CheckCircle2,
  AlertCircle,
  AlertTriangle,
  Loader2,
  RotateCw,
  Search,
  Database,
  type LucideIcon,
} from 'lucide-react';
import type { DataTable } from '../../../types';
import { SPACE } from '../theme';
import { TableBrowser } from './TableBrowser';

/**
 * TableArtifact - the right artifact panel for Prepare (Transform) mode.
 *
 * Presentational only. It renders one of four states (Requirement 7.2-7.6):
 *  - `disabled`: no uploaded files - tells the user to upload in Sources.
 *  - `ready`:    uploaded files exist but no transform yet - "Ready to prepare
 *                data." with the Rerun action available to kick one off.
 *  - `running`:  a transform is in flight - table skeleton (the live activity
 *                trail lives in the chat thread, not here).
 *  - `error`:    a neutral error panel with a retry action.
 * When a transform has completed, pass `state="ready"` together with a `table`
 * and the supporting metadata; the final transformed table becomes the main
 * artifact (Requirement 7.5) alongside source tables, the recipe/steps, data
 * quality checks, and the column mapping summary (Requirement 7.1).
 *
 * Uses only SPACE tokens + lucide-react, matching SlimRail/ModeSwitcher styling.
 *
 * Requirements: 7.1 (preview, source tables, recipe, quality checks, column
 * mapping, Rerun/Save/Inspect), 7.2 (disabled), 7.3 (ready), 7.4 (running
 * skeleton), 7.5 (completed table as main artifact), 7.6 (neutral error + retry).
 */

/** Visual state of the Prepare artifact panel. */
export type TableArtifactState = 'disabled' | 'ready' | 'running' | 'error';

/** Outcome of a single data-quality check. */
export type QualityStatus = 'pass' | 'warn' | 'fail';

export interface DataQualityCheck {
  /** Human-readable label, e.g. "No null values in key columns". */
  label: string;
  status: QualityStatus;
  /** Optional detail, e.g. "3 nulls found in `email`". */
  detail?: string;
}

export interface ColumnMapping {
  /** Source column expression, e.g. "orders.amount". */
  source: string;
  /** Target column in the transformed table, e.g. "revenue". */
  target: string;
}

export interface TableArtifactProps {
  /** Which state to render. */
  state: TableArtifactState;
  /** The final transformed table (shown when present, typically in `ready`). */
  table?: DataTable | null;
  /** All active prepared tables available to this folder session. */
  preparedTables?: DataTable[];
  /** Stable prepared-table ID used by Visualize and Publish. */
  selectedTableId?: string | null;
  /** Persist the table selection for downstream modes. */
  onSelectTable?: (tableId: string) => Promise<void> | void;
  /** Source tables used by the transform (name + shape). */
  sourceTables?: DataTable[];
  /** Ordered transformation recipe / steps. */
  recipe?: string[];
  /** Data-quality check results. */
  qualityChecks?: DataQualityCheck[];
  /** Column mapping summary (source → target). */
  columnMapping?: ColumnMapping[];
  /** Error message shown in the `error` state. */
  error?: string | null;
  /** Re-run the transform. */
  onRerun?: () => void;
  /** Open a full inspector for the transformed table. */
  onInspect?: () => void;
  /** Retry after an error (defaults to {@link onRerun} when omitted). */
  onRetry?: () => void;
  /**
   * Load one page of a table's rows for the interactive source-table browser.
   * When provided, source tables become clickable and preview their data
   * inline with pagination; when omitted they render as a static list.
   */
  onLoadTablePage?: (tableId: string, page: number) => Promise<DataTable | null>;
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

/** Centered empty/disabled/ready message block. */
function MessageBlock({
  icon: Icon,
  title,
  body,
  tone = 'muted',
}: {
  icon: LucideIcon;
  title: string;
  body: string;
  tone?: 'muted' | 'ready';
}) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-8 text-center">
      <div
        className="mb-3 flex h-11 w-11 items-center justify-center rounded-xl"
        style={{
          backgroundColor: SPACE.panel,
          border: `1px solid ${SPACE.border}`,
          color: tone === 'ready' ? SPACE.text : SPACE.muted,
        }}
      >
        <Icon className="h-5 w-5" strokeWidth={1.75} />
      </div>
      <div className="text-sm font-medium" style={{ color: SPACE.text }}>
        {title}
      </div>
      <p className="mt-1 max-w-[260px] text-xs" style={{ color: SPACE.muted }}>
        {body}
      </p>
    </div>
  );
}

/** Skeleton rows for the running state. */
function TableSkeleton() {
  return (
    <div className="space-y-2 px-4 pt-3">
      <div className="flex items-center gap-2 text-xs" style={{ color: SPACE.muted }}>
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        Preparing data…
      </div>
      <div className="overflow-hidden rounded-lg border" style={{ borderColor: SPACE.border }}>
        {Array.from({ length: 6 }).map((_, i) => (
          <div
            key={i}
            className="flex gap-2 px-3 py-2"
            style={{ borderTop: i === 0 ? 'none' : `1px solid ${SPACE.border}` }}
          >
            {Array.from({ length: 4 }).map((__, j) => (
              <div
                key={j}
                className="h-3 flex-1 animate-pulse rounded"
                style={{ backgroundColor: SPACE.hover }}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

/** The transformed-table preview (header + scrollable rows). */
function TablePreview({ table }: { table: DataTable }) {
  if (table.isLoading) {
    return (
      <div className="flex items-center justify-center py-8" style={{ color: SPACE.muted }}>
        <Loader2 className="h-4 w-4 animate-spin" />
      </div>
    );
  }
  if (table.rows.length === 0) {
    return (
      <div className="px-4 py-6 text-center text-xs" style={{ color: SPACE.subtle }}>
        No rows to preview.
      </div>
    );
  }
  return (
    <div className="px-4">
      <div className="overflow-x-auto rounded-lg border" style={{ borderColor: SPACE.border }}>
        <table className="w-full text-left text-xs">
          <thead>
            <tr style={{ backgroundColor: SPACE.panel }}>
              {table.columns.map((col) => (
                <th
                  key={col}
                  className="whitespace-nowrap px-3 py-2 font-medium"
                  style={{ color: SPACE.muted, fontFamily: 'JetBrains Mono, monospace' }}
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.slice(0, 50).map((row, i) => (
              <tr key={i} style={{ borderTop: `1px solid ${SPACE.border}` }}>
                {table.columns.map((col) => (
                  <td
                    key={col}
                    className="whitespace-nowrap px-3 py-1.5"
                    style={{ color: SPACE.text, fontFamily: 'JetBrains Mono, monospace' }}
                  >
                    {String(row[col] ?? '')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="px-1 pt-1.5 text-[11px]" style={{ color: SPACE.subtle }}>
        {table.columns.length} columns / {table.rowCount} rows
        {table.rowCount > 50 ? ' (showing first 50)' : ''}
      </div>
    </div>
  );
}

/** Maps a quality status to an icon + color. */
function qualityIcon(status: QualityStatus): { Icon: LucideIcon; color: string } {
  switch (status) {
    case 'pass':
      return { Icon: CheckCircle2, color: SPACE.success };
    case 'warn':
      return { Icon: AlertTriangle, color: SPACE.muted };
    case 'fail':
    default:
      return { Icon: AlertCircle, color: SPACE.danger };
  }
}

export function TableArtifact({
  state,
  table,
  preparedTables = [],
  selectedTableId,
  onSelectTable,
  sourceTables = [],
  recipe = [],
  qualityChecks = [],
  columnMapping = [],
  error,
  onRerun,
  onInspect,
  onRetry,
  onLoadTablePage,
}: TableArtifactProps) {
  // --- Disabled: no uploaded files (Requirement 7.2) ---
  if (state === 'disabled') {
    return (
      <div className="flex h-full flex-col" style={{ backgroundColor: SPACE.panelAlt }}>
        <MessageBlock
          icon={Database}
          title="Nothing to prepare yet"
          body="Upload a file in Sources first, then come back here to clean, join, and transform it."
        />
      </div>
    );
  }

  // --- Error: neutral panel + retry (Requirement 7.6) ---
  if (state === 'error') {
    return (
      <div className="flex h-full flex-col items-center justify-center px-8 text-center" style={{ backgroundColor: SPACE.panelAlt }}>
        <div
          className="mb-3 flex h-11 w-11 items-center justify-center rounded-xl"
          style={{ backgroundColor: 'rgba(244, 244, 245, 0.06)', border: `1px solid ${SPACE.danger}`, color: SPACE.danger }}
        >
          <AlertCircle className="h-5 w-5" />
        </div>
        <div className="text-sm font-medium" style={{ color: SPACE.danger }}>
          Transform failed
        </div>
        <p className="mt-1 max-w-[260px] text-xs" style={{ color: SPACE.muted }}>
          {error || 'Something went wrong while preparing the data.'}
        </p>
        <div className="mt-4">
          <ActionButton icon={RotateCw} label="Retry" variant="primary" onClick={onRetry || onRerun} />
        </div>
      </div>
    );
  }

  // --- Running: skeleton (Requirement 7.4) ---
  if (state === 'running') {
    return (
      <div className="flex h-full flex-col overflow-y-auto" style={{ backgroundColor: SPACE.panelAlt }}>
        <TableSkeleton />
      </div>
    );
  }

  // --- Ready without a completed table: "Ready to prepare data." (Req 7.3) ---
  if (state === 'ready' && !table) {
    return (
      <div className="flex h-full flex-col" style={{ backgroundColor: SPACE.panelAlt }}>
        <MessageBlock
          icon={Wand2}
          title="Ready to prepare data"
          body="Ask in the chat how to clean, join, or transform your uploaded tables into one final table."
          tone="ready"
        />
        {sourceTables.length > 0 && (
          <>
            <SectionLabel icon={Table2}>Source tables ({sourceTables.length})</SectionLabel>
            {onLoadTablePage ? (
              <div className="pb-4">
                <TableBrowser tables={sourceTables} onLoadPage={onLoadTablePage} />
              </div>
            ) : (
              <div className="space-y-1.5 px-4 pb-4">
                {sourceTables.map((t) => (
                  <SourceTableRow key={t.id} table={t} />
                ))}
              </div>
            )}
          </>
        )}
      </div>
    );
  }

  // --- Ready with a completed transform table (Requirement 7.1, 7.5) ---
  return (
    <div className="flex h-full flex-col overflow-y-auto" style={{ backgroundColor: SPACE.panelAlt }}>
      {/* Action bar */}
      <div
        className="flex flex-shrink-0 items-center gap-2 border-b px-4 py-2.5"
        style={{ borderColor: SPACE.border }}
      >
        <div className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium" style={{ color: SPACE.text }}>
            {table?.name || 'Prepared table'}
          </span>
          <span className="text-[11px]" style={{ color: SPACE.subtle }}>
            {table?.revision ? `Revision ${table.revision} · ` : ''}Selected for Visualize and Publish
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <ActionButton icon={RotateCw} label="Rerun" variant="outline" onClick={onRerun} />
          <ActionButton icon={Search} label="Inspect" variant="outline" onClick={onInspect} />
        </div>      </div>

      {preparedTables.length > 1 && (
        <label
          className="flex items-center gap-3 px-4 py-3"
          style={{ borderBottom: `1px solid ${SPACE.border}` }}
        >
          <span className="flex-shrink-0 text-[11px] font-medium uppercase tracking-wide" style={{ color: SPACE.subtle }}>
            Prepared table
          </span>
          <select
            value={selectedTableId || table?.id || ''}
            onChange={(event) => void onSelectTable?.(event.target.value)}
            disabled={!onSelectTable}
            className="min-w-0 flex-1 rounded-md border px-2.5 py-1.5 text-xs outline-none focus-visible:ring-1 disabled:opacity-60"
            style={{ backgroundColor: SPACE.panel, borderColor: SPACE.border, color: SPACE.text }}
            aria-label="Prepared table used by Visualize and Publish"
          >
            {preparedTables.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}{item.revision ? ` · r${item.revision}` : ''}
              </option>
            ))}
          </select>
        </label>
      )}
      {/* Final transformed table preview (main artifact) */}
      {table && (
        <div className="pt-3">
          <TablePreview table={table} />
        </div>
      )}

      {/* Source tables used */}
      {sourceTables.length > 0 && (
        <>
          <SectionLabel icon={Table2}>Source tables ({sourceTables.length})</SectionLabel>
          {onLoadTablePage ? (
            <TableBrowser tables={sourceTables} onLoadPage={onLoadTablePage} />
          ) : (
            <div className="space-y-1.5 px-4">
              {sourceTables.map((t) => (
                <SourceTableRow key={t.id} table={t} />
              ))}
            </div>
          )}
        </>
      )}

      {/* Transformation recipe / steps */}
      {recipe.length > 0 && (
        <>
          <SectionLabel icon={ListChecks}>Recipe</SectionLabel>
          <ol className="space-y-1.5 px-4">
            {recipe.map((step, i) => (
              <li
                key={i}
                className="flex gap-2.5 rounded-lg px-3 py-2 text-xs"
                style={{ backgroundColor: SPACE.panel, border: `1px solid ${SPACE.border}`, color: SPACE.text }}
              >
                <span
                  className="flex h-4 w-4 flex-shrink-0 items-center justify-center rounded-full text-[10px] font-medium"
                  style={{ backgroundColor: SPACE.hover, color: SPACE.muted }}
                >
                  {i + 1}
                </span>
                <span>{step}</span>
              </li>
            ))}
          </ol>
        </>
      )}

      {/* Data quality checks */}
      {qualityChecks.length > 0 && (
        <>
          <SectionLabel icon={CheckCircle2}>Data quality</SectionLabel>
          <div className="space-y-1.5 px-4">
            {qualityChecks.map((check, i) => {
              const { Icon, color } = qualityIcon(check.status);
              return (
                <div
                  key={i}
                  className="flex items-start gap-2.5 rounded-lg px-3 py-2"
                  style={{ backgroundColor: SPACE.panel, border: `1px solid ${SPACE.border}` }}
                >
                  <Icon className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" style={{ color }} />
                  <div className="min-w-0">
                    <div className="text-xs" style={{ color: SPACE.text }}>{check.label}</div>
                    {check.detail && (
                      <div className="text-[11px]" style={{ color: SPACE.subtle }}>{check.detail}</div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}

      {/* Column mapping summary */}
      {columnMapping.length > 0 && (
        <>
          <SectionLabel icon={ArrowRight}>Column mapping</SectionLabel>
          <div className="space-y-1 px-4 pb-4">
            {columnMapping.map((m, i) => (
              <div
                key={i}
                className="flex items-center gap-2 rounded-lg px-3 py-1.5 text-[11px]"
                style={{ backgroundColor: SPACE.panel, border: `1px solid ${SPACE.border}` }}
              >
                <span className="truncate font-mono" style={{ color: SPACE.muted }}>{m.source}</span>
                <ArrowRight className="h-3 w-3 flex-shrink-0" style={{ color: SPACE.subtle }} />
                <span className="truncate font-mono" style={{ color: SPACE.text }}>{m.target}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

/** A compact source-table row. */
function SourceTableRow({ table }: { table: DataTable }) {
  return (
    <div
      className="flex items-center gap-2.5 rounded-lg px-3 py-2"
      style={{ backgroundColor: SPACE.panel, border: `1px solid ${SPACE.border}` }}
    >
      <Table2 className="h-4 w-4 flex-shrink-0" style={{ color: SPACE.muted }} />
      <div className="min-w-0 flex-1">
        <div className="truncate text-xs font-medium" style={{ color: SPACE.text }}>{table.name}</div>
        <div className="text-[11px]" style={{ color: SPACE.subtle }}>
          {table.columns.length} cols / {table.rowCount} rows
        </div>
      </div>
    </div>
  );
}

export default TableArtifact;

