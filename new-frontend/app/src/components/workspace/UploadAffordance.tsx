import { useId, useRef, useState } from 'react';
import { Paperclip, UploadCloud } from 'lucide-react';
import { isAllowedUploadFile } from '../../hooks/useFolderUpload';
import { SPACE } from './theme';

/**
 * UploadAffordance - folds the legacy Upload page into the conversation.
 *
 * Provides the two in-conversation upload entry points described in the design
 * (Requirements 6.1, 6.4):
 *   - {@link AttachButton}: a paperclip trigger that opens the native file
 *     picker, scoped to the `.csv/.xls/.xlsx` allowlist via the `accept`
 *     attribute.
 *   - {@link UploadAffordance}: a drop-zone wrapper that accepts files dragged
 *     onto its children (the composer), shows a drop overlay while dragging,
 *     and validates dropped files against the same allowlist.
 *
 * Both forward only allowed files to `onUpload` (which is wired to the
 * `useFolderUpload` hook in WorkspaceView). The `.csv/.xls/.xlsx` allowlist is
 * communicated in the UI: the picker is filtered, the drop overlay names the
 * accepted types, and any rejected files surface a transient coral hint. The
 * hook remains the authoritative validator; the server is authoritative beyond
 * that. Uses only monochrome SPACE tokens - coral for the rejection hint only.
 */

/** Comma-separated `accept` value for the native file input. */
const ACCEPT = '.csv,.xls,.xlsx';

/** Human-readable allowlist label shown in hints and the drop overlay. */
const ALLOWLIST_LABEL = '.csv, .xls, or .xlsx';

/** Default validator: the same allowlist enforced by `useFolderUpload`. */
const defaultValidator = isAllowedUploadFile;

/** Split a file list into allowed/rejected using the given validator. */
function partitionFiles(
  files: File[],
  isAllowed: (name: string) => boolean,
): { allowed: File[]; rejected: File[] } {
  const allowed: File[] = [];
  const rejected: File[] = [];
  for (const file of files) {
    if (isAllowed(file.name)) allowed.push(file);
    else rejected.push(file);
  }
  return { allowed, rejected };
}

export interface AttachButtonProps {
  /** Disabled when no folder is selected (Requirement 6.2). */
  disabled: boolean;
  /** Receives the allowed files chosen from the picker. */
  onUpload: (files: File[]) => void;
  /** Override the allowlist validator (defaults to the upload hook's). */
  isAllowedUploadFile?: (fileName: string) => boolean;
}

/**
 * Paperclip button that opens the native file picker. Lives in the composer's
 * button row. Forwards only allowlisted files to `onUpload`.
 */
export function AttachButton({
  disabled,
  onUpload,
  isAllowedUploadFile: isAllowed = defaultValidator,
}: AttachButtonProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const inputId = useId();

  const handleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    // Reset so selecting the same file again still fires `change`.
    event.target.value = '';
    if (files.length === 0) return;
    const { allowed } = partitionFiles(files, isAllowed);
    if (allowed.length > 0) onUpload(allowed);
  };

  return (
    <>
      <input
        ref={inputRef}
        id={inputId}
        type="file"
        multiple
        accept={ACCEPT}
        className="sr-only"
        onChange={handleChange}
        disabled={disabled}
      />
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={disabled}
        aria-label={`Attach files (${ALLOWLIST_LABEL})`}
        title={disabled ? 'Select a folder to upload files' : `Attach ${ALLOWLIST_LABEL} files`}
        className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg transition-colors disabled:cursor-not-allowed disabled:opacity-40"
        style={{ color: SPACE.muted }}
        onMouseEnter={(e) => {
          if (disabled) return;
          e.currentTarget.style.backgroundColor = SPACE.hover;
          e.currentTarget.style.color = SPACE.text;
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.backgroundColor = 'transparent';
          e.currentTarget.style.color = SPACE.muted;
        }}
      >
        <Paperclip className="h-4 w-4" />
      </button>
    </>
  );
}

export interface UploadAffordanceProps {
  /** Disabled when no folder is selected; drag-drop becomes inert. */
  disabled: boolean;
  /** Receives the allowed files dropped onto the zone. */
  onUpload: (files: File[]) => void;
  /** Override the allowlist validator (defaults to the upload hook's). */
  isAllowedUploadFile?: (fileName: string) => boolean;
  /** The composer content wrapped by the drop zone. */
  children: React.ReactNode;
}

/**
 * Drop-zone wrapper. Renders `children` (the composer) and accepts files
 * dragged onto the area. While a drag is over the zone, a dashed overlay names
 * the accepted file types. Rejected files surface a transient coral hint so the
 * allowlist is always communicated in the UI.
 */
export function UploadAffordance({
  disabled,
  onUpload,
  isAllowedUploadFile: isAllowed = defaultValidator,
  children,
}: UploadAffordanceProps) {
  // Use a depth counter so nested dragenter/dragleave events don't flicker.
  const dragDepth = useRef(0);
  const [isDragging, setIsDragging] = useState(false);
  const [rejectedHint, setRejectedHint] = useState<string | null>(null);

  const isFileDrag = (event: React.DragEvent) =>
    Array.from(event.dataTransfer?.types ?? []).includes('Files');

  const handleDragEnter = (event: React.DragEvent) => {
    if (disabled || !isFileDrag(event)) return;
    event.preventDefault();
    dragDepth.current += 1;
    setIsDragging(true);
  };

  const handleDragOver = (event: React.DragEvent) => {
    if (disabled || !isFileDrag(event)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = 'copy';
  };

  const handleDragLeave = (event: React.DragEvent) => {
    if (disabled || !isFileDrag(event)) return;
    dragDepth.current = Math.max(0, dragDepth.current - 1);
    if (dragDepth.current === 0) setIsDragging(false);
  };

  const handleDrop = (event: React.DragEvent) => {
    if (disabled || !isFileDrag(event)) return;
    event.preventDefault();
    dragDepth.current = 0;
    setIsDragging(false);

    const files = Array.from(event.dataTransfer.files ?? []);
    if (files.length === 0) return;

    const { allowed, rejected } = partitionFiles(files, isAllowed);
    if (rejected.length > 0) {
      const names = rejected.map((f) => f.name).join(', ');
      setRejectedHint(`Unsupported: ${names}. Only ${ALLOWLIST_LABEL} files are allowed.`);
      window.setTimeout(() => setRejectedHint(null), 6000);
    } else {
      setRejectedHint(null);
    }
    if (allowed.length > 0) onUpload(allowed);
  };

  return (
    <div
      className="relative"
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {children}

      {/* Drag overlay - communicates the accepted file types. */}
      {isDragging && (
        <div
          className="pointer-events-none absolute inset-0 z-20 flex flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed text-sm font-medium"
          style={{
            borderColor: SPACE.text,
            backgroundColor: 'rgba(8,8,10,0.85)',
            color: SPACE.text,
          }}
        >
          <UploadCloud className="h-6 w-6" />
          <span>Drop {ALLOWLIST_LABEL} files to upload</span>
        </div>
      )}

      {/* Transient rejection hint (coral, allowlist communication). */}
      {rejectedHint && (
        <div
          role="alert"
          className="mt-1.5 px-1 text-xs"
          style={{ color: SPACE.danger }}
        >
          {rejectedHint}
        </div>
      )}
    </div>
  );
}

export default UploadAffordance;
