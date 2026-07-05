import { useCallback, useState } from 'react';
import {
  Table2,
  ChevronRight,
  Loader2,
  Plus,
  Rows3,
  AlertCircle,
  type LucideIcon,
} from 'lucide-react';
import type { DataTable } from '../../../types';
import { SPACE } from '../theme';

/**
 * TableBrowser - an interactive list of tables where each row can be expanded
 * to preview its data on demand.
 *
 * Behaviour (per product spec):
 *  - Lists every table passed in (uploaded source tables, or raw tables).
 *  - Clicking a table row loads and reveals its data inline (accordion style);
 *    only one table is expanded at a time.
 *  - Data is fetched page-by-page via {@link onLoadPage}. The first page shows a
 *    threshold of `pageSize` rows (default 20) at natural height - no scrollbar.
 *  - "Load more" appends the next page. Once more than one page is loaded the
 *    data grid becomes a fixed-height, scrollable container (scrollbar appears)
 *    with a sticky header.
 *  - Rows are cached in the parent's global state (the loader merges pages into
 *    the same {@link DataTable}), so re-opening a table shows cached rows
 *    instantly with no refetch.
 *
 * Presentational + minimal local UI state only. Uses SPACE tokens + lucide-react
 * to match SourcesPanel / TableArtifact styling.
 */

/** Fixed height (px) the data grid is capped to once it becomes scrollable. */
const SCROLL_MAX_HEIGHT = 340;

export interface TableBrowserProps {
  /** Tables to list. Each carries its own cached rows / page / hasMore. */
  tables: DataTable[];
  /**
   * Load one page of a table's rows. Implementations should merge the page into
   * the table (append when `page > 1`) and return the updated table. Called with
   * page 1 when a table is first opened, and page N+1 on "Load more".
   */
  onLoadPage: (tableId: string, page: number) => Promise<DataTable | null>;
  /** Rows per page / initial threshold before a scrollbar appears. Default 20. */
  pageSize?: number;
  /** Optional icon for the list rows. Defaults to a table glyph. */
  rowIcon?: LucideIcon;
}

/** The expandable data grid for a single, selected table. */
function TableDataView({
  table,
  pageSize,
  onLoadMore,
}: {
  table: DataTable;
  pageSize: number;
  onLoadMore: () => void;
}) {
  const loadedRows = table.rows.length;
  const totalRows = table.rowCount || loadedRows;
  const scrollable = loadedRows > pageSize;
  const initialLoading = table.isLoading && loadedRows === 0;

  if (initialLoading) {
    return (
      <div
        className="flex items-center justify-center gap-2 py-8 text-xs"
        style={{ color: SPACE.muted }}
      >
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading table…
      </div>
    );
  }

  if (!table.isLoading && loadedRows === 0) {
    return (
      <div
        className="flex items-center justify-center gap-2 py-6 text-xs"
        style={{ color: SPACE.subtle }}
      >
        <AlertCircle className="h-3.5 w-3.5" />
        No rows to preview.
      </div>
    );
  }

  return (
    <div className="space-y-2 pb-1">
      <div
        className="overflow-auto rounded-lg border"
        style={{
          borderColor: SPACE.border,
          maxHeight: scrollable ? SCROLL_MAX_HEIGHT : undefined,
        }}
      >
        <table className="w-full text-left text-xs" style={{ borderCollapse: 'separate', borderSpacing: 0 }}>
          <thead>
            <tr>
              {table.columns.map((col) => (
                <th
                  key={col}
                  className="sticky top-0 z-10 whitespace-nowrap px-3 py-2 font-medium"
                  style={{
                    color: SPACE.muted,
                    backgroundColor: SPACE.panel,
                    fontFamily: 'JetBrains Mono, monospace',
                    borderBottom: `1px solid ${SPACE.border}`,
                  }}
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, i) => (
              <tr key={i} style={{ borderTop: i === 0 ? 'none' : `1px solid ${SPACE.border}` }}>
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

      <div className="flex items-center justify-between px-0.5">
        <span className="text-[11px]" style={{ color: SPACE.subtle }}>
          Showing {loadedRows}{totalRows > loadedRows ? ` of ${totalRows}` : ''} rows
        </span>
        {table.hasMore && (
          <button
            type="button"
            onClick={onLoadMore}
            disabled={table.isLoading}
            className="flex items-center gap-1.5 rounded-md px-2 py-1 text-[11px] font-medium outline-none transition-colors focus-visible:ring-1 disabled:opacity-50"
            style={{ color: SPACE.text, border: `1px solid ${SPACE.border}`, cursor: table.isLoading ? 'wait' : 'pointer' }}
            onMouseEnter={(e) => {
              if (table.isLoading) return;
              e.currentTarget.style.backgroundColor = SPACE.hover;
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = 'transparent';
            }}
          >
            {table.isLoading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Plus className="h-3.5 w-3.5" />
            )}
            Load more
          </button>
        )}
      </div>
    </div>
  );
}

export function TableBrowser({ tables, onLoadPage, pageSize = 20, rowIcon }: TableBrowserProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const RowIcon = rowIcon ?? Table2;

  const handleToggle = useCallback(
    (table: DataTable) => {
      // Collapse if the same row is clicked again.
      if (selectedId === table.id) {
        setSelectedId(null);
        return;
      }
      setSelectedId(table.id);
      // Fetch the first page lazily - cached rows are reused with no refetch.
      if (table.rows.length === 0) {
        void onLoadPage(table.id, 1);
      }
    },
    [onLoadPage, selectedId],
  );

  const handleLoadMore = useCallback(
    (table: DataTable) => {
      const nextPage = (table.page || 1) + 1;
      void onLoadPage(table.id, nextPage);
    },
    [onLoadPage],
  );

  return (
    <div className="space-y-1.5 px-4">
      {tables.map((table) => {
        const open = selectedId === table.id;
        return (
          <div key={table.id}>
            <button
              type="button"
              onClick={() => handleToggle(table)}
              aria-expanded={open}
              className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left outline-none transition-colors focus-visible:ring-1"
              style={{
                backgroundColor: open ? SPACE.hover : SPACE.panel,
                border: `1px solid ${open ? SPACE.muted : SPACE.border}`,
                cursor: 'pointer',
              }}
              onMouseEnter={(e) => {
                if (!open) e.currentTarget.style.backgroundColor = SPACE.hover;
              }}
              onMouseLeave={(e) => {
                if (!open) e.currentTarget.style.backgroundColor = SPACE.panel;
              }}
            >
              <RowIcon className="h-4 w-4 flex-shrink-0" style={{ color: SPACE.muted }} />
              <div className="min-w-0 flex-1">
                <div className="truncate text-xs font-medium" style={{ color: SPACE.text }}>
                  {table.name}
                </div>
                <div className="flex items-center gap-1 text-[11px]" style={{ color: SPACE.subtle }}>
                  <Rows3 className="h-3 w-3" />
                  {table.columns.length > 0
                    ? `${table.columns.length} cols${table.rowCount ? ` · ${table.rowCount} rows` : ''}`
                    : 'Click to preview'}
                </div>
              </div>
              {table.isLoading && open && (
                <Loader2 className="h-3.5 w-3.5 flex-shrink-0 animate-spin" style={{ color: SPACE.muted }} />
              )}
              <ChevronRight
                className="h-4 w-4 flex-shrink-0 transition-transform"
                style={{ color: SPACE.subtle, transform: open ? 'rotate(90deg)' : 'none' }}
              />
            </button>

            {open && (
              <div className="pt-1.5">
                <TableDataView
                  table={table}
                  pageSize={pageSize}
                  onLoadMore={() => handleLoadMore(table)}
                />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default TableBrowser;
