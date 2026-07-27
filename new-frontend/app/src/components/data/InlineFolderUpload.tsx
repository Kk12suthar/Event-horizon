import { useRef, useState } from 'react';
import { AlertCircle, CheckCircle2, Loader2, UploadCloud, X } from 'lucide-react';
import type { UploadStage } from '@/hooks/useFolderUpload';

type InlineFolderUploadProps = {
  folderName: string;
  open: boolean;
  canUpload: boolean;
  stage: UploadStage;
  progress: number;
  error: string | null;
  onUpload: (files: File[]) => Promise<void>;
  onOpen: () => void;
  onClose: () => void;
};

export function InlineFolderUpload({
  folderName,
  open,
  canUpload,
  stage,
  progress,
  error,
  onUpload,
  onOpen,
  onClose,
}: InlineFolderUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const busy = stage === 'uploading' || stage === 'creating';

  if (!canUpload) return null;

  if (!open) {
    return (
      <button
        type="button"
        onClick={onOpen}
        className="flex h-8 w-full items-center justify-center gap-2 rounded-md border border-[#323232] bg-[#171717] text-xs font-medium text-[#CFCFCF] transition hover:border-[#5B3A29] hover:bg-[#1C1511] hover:text-white"
      >
        <UploadCloud className="h-3.5 w-3.5 text-[#D88A5F]" />
        Add source files
      </button>
    );
  }

  const submit = (files: File[]) => {
    if (!files.length || busy) return;
    void onUpload(files);
  };

  return (
    <section className="rounded-md" aria-label={`Upload files to ${folderName}`}>
      <div className="mb-2.5 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-[#777]">Add data</p>
          <p className="truncate text-xs text-[#BDBDBD]">Upload into {folderName}</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="flex h-7 w-7 flex-none items-center justify-center rounded-md text-[#777] transition hover:bg-[#222] hover:text-white"
          aria-label="Close upload panel"
          title="Close upload panel"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      <input
        ref={inputRef}
        type="file"
        multiple
        accept=".csv,.xls,.xlsx"
        className="hidden"
        onChange={(event) => {
          submit(Array.from(event.target.files || []));
          event.target.value = '';
        }}
      />

      <button
        type="button"
        disabled={busy}
        onClick={() => inputRef.current?.click()}
        onDragEnter={(event) => {
          event.preventDefault();
          if (!busy) setDragging(true);
        }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={(event) => {
          event.preventDefault();
          if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false);
        }}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          submit(Array.from(event.dataTransfer.files));
        }}
        className={`flex min-h-24 w-full flex-col items-center justify-center rounded-lg border border-dashed px-3 py-3 text-center transition ${
          dragging
            ? 'border-[#C16E43] bg-[#C16E43]/8'
            : 'border-[#383838] bg-[#151515] hover:border-[#5B3A29] hover:bg-[#191512]'
        } ${busy ? 'cursor-wait opacity-75' : ''}`}
      >
        {busy ? <Loader2 className="h-5 w-5 animate-spin text-[#D88A5F]" /> : <UploadCloud className="h-5 w-5 text-[#D88A5F]" />}
        <span className="mt-2 text-xs font-medium text-[#E4E4E4]">
          {busy ? (stage === 'creating' ? 'Creating tables' : 'Uploading files') : 'Drop files or browse'}
        </span>
        <span className="mt-1 text-[10px] text-[#777]">CSV, XLS, or XLSX</span>
      </button>

      {busy && (
        <div className="mt-2.5">
          <div className="h-1 overflow-hidden rounded-full bg-[#292929]">
            <div className="h-full rounded-full bg-[#C16E43] transition-all" style={{ width: `${Math.max(2, progress)}%` }} />
          </div>
          <p className="mt-1.5 text-[10px] text-[#888]">{Math.round(progress)}% complete</p>
        </div>
      )}

      {stage === 'complete' && !error && (
        <p className="mt-2.5 flex items-center gap-1.5 text-[11px] text-[#5FD38A]">
          <CheckCircle2 className="h-3.5 w-3.5" /> Files are ready
        </p>
      )}

      {error && (
        <p className="mt-2.5 flex items-start gap-1.5 text-[11px] leading-4 text-[#F97066]">
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 flex-none" /> {error}
        </p>
      )}
    </section>
  );
}

export default InlineFolderUpload;