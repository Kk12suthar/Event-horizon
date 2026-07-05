import { useCallback, useRef, useState } from 'react';
import {
  UploadCloud,
  FileSpreadsheet,
  Table2,
  Trash2,
  Loader2,
  CheckCircle2,
  AlertCircle,
  ChevronDown,
  ChevronRight,
  Clock,
  type LucideIcon,
} from 'lucide-react';
import type { DataTable, Session, UploadedFile } from '../../../types';
import { SPACE } from '../theme';
import { TableBrowser } from './TableBrowser';

/**
 * SourcesPanel - the right artifact panel for Sources (Upload) mode.
 *
 * Presentational only: every piece of data and state arrives via props and all
 * actions are delegated to callbacks. It renders, in order, a dropzone, the
 * uploaded file list with per-file status/delete, an upload progress bar with
 * processing status, the raw created tables, and collapsed session info. When
 * no folder is selected the whole panel renders in a disabled state with the
 * dropzone inert (Requirement 6.2).
 *
 * Uses only the monochrome SPACE tokens and lucide-react icons, matching the
 * conventions in SlimRail/ModeSwitcher (inline-style colors, hover handlers,
 * thin borders, compact density). No purple/blue, no gradients.
 *
 * Requirements: 6.1 (dropzone, file list, progress, raw tables, processing
 * status, delete, collapsed session info), 6.2 (disabled state when no folder),
 * 6.3 (prominent dropzone when folder has no files).
 */

/** Coarse stage of the in-flight upload, drives the processing status line. */
export type UploadStage = 'idle' | 'uploading' | 'creating' | 'complete' | 'error';

/** Client-side allowlist mirrored from the upload hook (Requirement 6.4). */
const ACCEPTED_EXTENSIONS = ['.csv', '.xls', '.xlsx'] as const;
const ACCEPT_ATTR = ACCEPTED_EXTENSIONS.join(',');

export interface SourcesPanelProps {
  /** True when no folder is selected - renders the disabled upload state. */
  disabled: boolean;
  /** Uploaded files with their per-file status. */
  files: UploadedFile[];
  /** Raw created tables (source === 'uploaded') produced from the files. */
  tables: DataTable[];
  /** Current upload progress in [0, 100]. */
  progress?: number;
  /** Coarse stage of the in-flight upload. */
  stage?: UploadStage;
  /** Optional error message shown when {@link stage} is `error`. */
  error?: string | null;
  /** Active session, shown in the collapsed session info section. */
  session?: Session | null;
  /** Invoked with the dropped/selected files (already filtered by the caller). */
  onFilesSelected: (files: File[]) => void;
  /** Invoked when the user deletes an uploaded file. */
  onDeleteFile?: (fileId: string) => void;
  /**
   * Load one page of a table's rows for the interactive raw-table browser.
   * When provided, raw tables become clickable and preview their data inline
   * with pagination; when omitted they render as a static list.
   */
  onLoadTablePage?: (tableId: string, page: number) => Promise<DataTable | null>;
}

/** Human-readable byte size. */
function formatBytes(bytes: number): string {
  if (!bytes || bytes < 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / Math.pow(1024, i);
  return `${value >= 10 || i === 0 ? Math.round(value) : value.toFixed(1)} ${units[i]}`;
}

/** Section heading shared across the panel. */
function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="px-4 pb-1.5 pt-3 text-[11px] font-medium uppercase tracking-wide"
      style={{ color: SPACE.subtle }}
    >
      {children}
    </div>
  );
}

/** The drag-and-drop / click-to-browse target. */
function Dropzone({
  disabled,
  prominent,
  onFilesSelected,
}: {
  disabled: boolean;
  prominent: boolean;
  onFilesSelected: (files: File[]) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const emit = useCallback(
    (fileList: FileList | null) => {
      if (!fileList || disabled) return;
      const accepted = Array.from(fileList).filter((f) =>
        ACCEPTED_EXTENSIONS.some((ext) => f.name.toLowerCase().endsWith(ext)),
      );
      if (accepted.length > 0) onFilesSelected(accepted);
    },
    [disabled, onFilesSelected],
  );

  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => !disabled && inputRef.current?.click()}
      onDragOver={(e) => {
        if (disabled) return;
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        if (disabled) return;
        e.preventDefault();
        setDragging(false);
        emit(e.dataTransfer.files);
      }}
      className="flex w-full flex-col items-center justify-center gap-2 rounded-xl border border-dashed text-center outline-none transition-colors focus-visible:ring-1"
      style={{
        borderColor: dragging ? SPACE.text : SPACE.border,
        backgroundColor: dragging ? SPACE.hover : SPACE.panelAlt,
        color: SPACE.muted,
        padding: prominent ? '2.25rem 1rem' : '1.25rem 1rem',
        opacity: disabled ? 0.4 : 1,
        cursor: disabled ? 'not-allowed' : 'pointer',
      }}
      onMouseEnter={(e) => {
        if (disabled || dragging) return;
        e.currentTarget.style.borderColor = SPACE.muted;
      }}
      onMouseLeave={(e) => {
        if (disabled || dragging) return;
        e.currentTarget.style.borderColor = SPACE.border;
      }}
    >
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={ACCEPT_ATTR}
        className="hidden"
        onChange={(e) => {
          emit(e.target.files);
          e.target.value = '';
        }}
      />
      <UploadCloud
        className={prominent ? 'h-7 w-7' : 'h-5 w-5'}
        strokeWidth={1.75}
        style={{ color: dragging ? SPACE.text : SPACE.muted }}
      />
      <span className="text-sm font-medium" style={{ color: disabled ? SPACE.muted : SPACE.text }}>
        {disabled ? 'Select a folder to upload' : 'Drop files or click to browse'}
      </span>
      <span className="text-xs" style={{ color: SPACE.subtle }}>
        CSV, XLS, or XLSX
      </span>
    </button>
  );
}

/** Maps a file status to an icon + color. */
function fileStatusIcon(status: UploadedFile['status']): { Icon: LucideIcon; color: string } {
  switch (status) {
    case 'uploaded':
      return { Icon: CheckCircle2, color: SPACE.success };
    case 'error':
      return { Icon: AlertCircle, color: SPACE.danger };
    case 'pending':
    default:
      return { Icon: Loader2, color: SPACE.muted };
  }
}

/** A single uploaded-file row with status and a delete action. */
function FileRow({
  file,
  onDelete,
}: {
  file: UploadedFile;
  onDelete?: (fileId: string) => void;
}) {
  const { Icon, color } = fileStatusIcon(file.status);
  return (
    <div
      className="group flex items-center gap-2.5 rounded-lg px-3 py-2"
      style={{ backgroundColor: SPACE.panel, border: `1px solid ${SPACE.border}` }}
    >
      <FileSpreadsheet className="h-4 w-4 flex-shrink-0" style={{ color: SPACE.muted }} />
      <div className="min-w-0 flex-1">
        <div className="truncate text-xs font-medium" style={{ color: SPACE.text }}>
          {file.name}
        </div>
        <div className="text-[11px]" style={{ color: SPACE.subtle }}>
          {formatBytes(file.size)}
        </div>
      </div>
      <Icon
        className={`h-3.5 w-3.5 flex-shrink-0 ${file.status === 'pending' ? 'animate-spin' : ''}`}
        style={{ color }}
      />
      {onDelete && (
        <button
          type="button"
          onClick={() => onDelete(file.id)}
          aria-label={`Delete ${file.name}`}
          title="Delete file"
          className="flex-shrink-0 rounded-md p-1 opacity-0 transition-opacity group-hover:opacity-100"
          style={{ color: SPACE.muted }}
          onMouseEnter={(e) => (e.currentTarget.style.color = SPACE.danger)}
          onMouseLeave={(e) => (e.currentTarget.style.color = SPACE.muted)}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}

/** Upload progress bar + processing status line. */
function ProcessingStatus({
  progress,
  stage,
  error,
}: {
  progress: number;
  stage: UploadStage;
  error?: string | null;
}) {
  const label =
    stage === 'uploading'
      ? `Uploading… ${Math.round(progress)}%`
      : stage === 'creating'
        ? 'Creating tables…'
        : stage === 'complete'
          ? 'Upload complete'
          : stage === 'error'
            ? error || 'Upload failed'
            : '';

  const showBar = stage === 'uploading' || stage === 'creating';
  const isError = stage === 'error';
  const isComplete = stage === 'complete';

  return (
    <div className="px-4 pb-1">
      <div className="flex items-center gap-2 text-xs" style={{ color: isError ? SPACE.danger : SPACE.muted }}>
        {stage === 'creating' && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
        {isComplete && <CheckCircle2 className="h-3.5 w-3.5" style={{ color: SPACE.success }} />}
        {isError && <AlertCircle className="h-3.5 w-3.5" />}
        <span>{label}</span>
      </div>
      {showBar && (
        <div
          className="mt-1.5 h-1 w-full overflow-hidden rounded-full"
          style={{ backgroundColor: SPACE.border }}
        >
          <div
            className="h-full rounded-full transition-all duration-200"
            style={{
              width: `${Math.max(0, Math.min(100, progress))}%`,
              backgroundColor: SPACE.text,
            }}
          />
        </div>
      )}
    </div>
  );
}

/** A raw created table row. */
function TableRow({ table }: { table: DataTable }) {
  return (
    <div
      className="flex items-center gap-2.5 rounded-lg px-3 py-2"
      style={{ backgroundColor: SPACE.panel, border: `1px solid ${SPACE.border}` }}
    >
      <Table2 className="h-4 w-4 flex-shrink-0" style={{ color: SPACE.muted }} />
      <div className="min-w-0 flex-1">
        <div className="truncate text-xs font-medium" style={{ color: SPACE.text }}>
          {table.name}
        </div>
        <div className="text-[11px]" style={{ color: SPACE.subtle }}>
          {table.columns.length} cols · {table.rowCount} rows
        </div>
      </div>
      {table.isLoading && <Loader2 className="h-3.5 w-3.5 animate-spin" style={{ color: SPACE.muted }} />}
    </div>
  );
}

/** Collapsed session info disclosure. */
function SessionInfo({ session }: { session: Session }) {
  const [open, setOpen] = useState(false);
  const Chevron = open ? ChevronDown : ChevronRight;
  return (
    <div className="px-4 pb-3 pt-1">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-1.5 rounded-md py-1 text-[11px] font-medium uppercase tracking-wide outline-none"
        style={{ color: SPACE.subtle }}
      >
        <Chevron className="h-3.5 w-3.5" />
        Session
      </button>
      {open && (
        <div
          className="mt-1.5 space-y-1 rounded-lg px-3 py-2 text-[11px]"
          style={{ backgroundColor: SPACE.panel, border: `1px solid ${SPACE.border}`, color: SPACE.muted }}
        >
          <div className="flex items-center gap-1.5">
            <span style={{ color: SPACE.subtle }}>ID</span>
            <span className="truncate font-mono" style={{ color: SPACE.text }}>{session.id}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span
              className="h-1.5 w-1.5 rounded-full"
              style={{ backgroundColor: session.status === 'active' ? SPACE.success : SPACE.subtle }}
            />
            <span style={{ color: SPACE.text }}>{session.status}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Clock className="h-3 w-3" />
            <span>{new Date(session.createdAt).toLocaleString()}</span>
          </div>
        </div>
      )}
    </div>
  );
}

export function SourcesPanel({
  disabled,
  files,
  tables,
  progress = 0,
  stage = 'idle',
  error,
  session,
  onFilesSelected,
  onDeleteFile,
  onLoadTablePage,
}: SourcesPanelProps) {
  const hasFiles = files.length > 0;
  const hasTables = tables.length > 0;
  const showProcessing = stage !== 'idle';

  return (
    <div className="flex h-full flex-col overflow-y-auto" style={{ backgroundColor: SPACE.panelAlt }}>
      {/* Dropzone - prominent when the folder has no files yet (Req 6.3). */}
      <div className="px-4 pt-4">
        <Dropzone disabled={disabled} prominent={!hasFiles} onFilesSelected={onFilesSelected} />
      </div>

      {showProcessing && (
        <div className="pt-2">
          <ProcessingStatus progress={progress} stage={stage} error={error} />
        </div>
      )}

      {hasFiles && (
        <>
          <SectionLabel>Files ({files.length})</SectionLabel>
          <div className="space-y-1.5 px-4">
            {files.map((file) => (
              <FileRow key={file.id} file={file} onDelete={onDeleteFile} />
            ))}
          </div>
        </>
      )}

      {hasTables && (
        <>
          <SectionLabel>Raw tables ({tables.length})</SectionLabel>
          {onLoadTablePage ? (
            <TableBrowser tables={tables} onLoadPage={onLoadTablePage} />
          ) : (
            <div className="space-y-1.5 px-4">
              {tables.map((table) => (
                <TableRow key={table.id} table={table} />
              ))}
            </div>
          )}
        </>
      )}

      {!disabled && !hasFiles && !hasTables && !showProcessing && (
        <div className="px-4 pt-3 text-xs" style={{ color: SPACE.subtle }}>
          No files yet. Drop a CSV or spreadsheet above to get started.
        </div>
      )}

      <div className="mt-auto">{session && <SessionInfo session={session} />}</div>
    </div>
  );
}

export default SourcesPanel;
