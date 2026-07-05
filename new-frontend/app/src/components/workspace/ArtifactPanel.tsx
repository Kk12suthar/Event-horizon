import { lazy, Suspense, type ComponentType } from 'react';
import { Database, Wand2, BarChart3, FileText, X, type LucideIcon } from 'lucide-react';
import type {
  ArtifactState,
  DataTable,
  PipelineState,
  Session,
  UploadedFile,
  WorkspaceMode,
} from '../../types';
import type { SourcesPanelProps, UploadStage as SourcesPanelUploadStage } from './artifacts/SourcesPanel';
import type { TableArtifactProps } from './artifacts/TableArtifact';
import type { ChartArtifactProps } from './artifacts/ChartArtifact';
import type { ReportArtifactProps } from './artifacts/ReportArtifact';
import { SPACE } from './theme';

type VariantComponent = ComponentType<Record<string, unknown>>;

const SourcesPanel = lazy(
  () => import('./artifacts/SourcesPanel') as Promise<{ default: ComponentType<SourcesPanelProps> }>,
);
const TableArtifact = lazy(
  () => import('./artifacts/TableArtifact') as Promise<{ default: ComponentType<TableArtifactProps> }>,
);
const ChartArtifact = lazy(
  () => import('./artifacts/ChartArtifact') as Promise<{ default: ComponentType<ChartArtifactProps> }>,
);
const ReportArtifact = lazy(
  () => import('./artifacts/ReportArtifact') as Promise<{ default: ComponentType<ReportArtifactProps> }>,
);

export interface ArtifactVariant {
  Component: VariantComponent;
  title: string;
  icon: LucideIcon;
}

const asVariantComponent = <Props,>(component: ComponentType<Props>) =>
  component as unknown as VariantComponent;

const VARIANTS: Record<WorkspaceMode, ArtifactVariant> = {
  sources: { Component: asVariantComponent(SourcesPanel), title: 'Sources', icon: Database },
  prepare: { Component: asVariantComponent(TableArtifact), title: 'Prepare', icon: Wand2 },
  visualize: { Component: asVariantComponent(ChartArtifact), title: 'Visualize', icon: BarChart3 },
  publish: { Component: asVariantComponent(ReportArtifact), title: 'Publish', icon: FileText },
};

export function variantForMode(mode: WorkspaceMode): ArtifactVariant {
  return VARIANTS[mode];
}

export interface ArtifactPanelProps {
  mode: WorkspaceMode;
  open: boolean;
  onClose: () => void;
  artifact?: ArtifactState;
  hasFolder: boolean;
  files: UploadedFile[];
  session?: Session | null;
  uploadProgress: number;
  uploadStage: Exclude<SourcesPanelUploadStage, 'error'>;
  uploadError?: string | null;
  onUpload: (files: File[]) => void;
  onDeleteFile?: (fileId: string) => void;
  pipeline: PipelineState;
  isGenerating?: boolean;
  /** Load one page of a table's rows (drives the interactive table browser). */
  onLoadTablePage?: (tableId: string, page: number) => Promise<DataTable | null>;
}

function ArtifactLoading() {
  return (
    <div className="flex flex-col gap-3 p-4" aria-busy="true" aria-live="polite">
      <div
        className="h-5 w-1/3 animate-pulse rounded"
        style={{ backgroundColor: SPACE.hover }}
      />
      <div
        className="h-32 w-full animate-pulse rounded-lg"
        style={{ backgroundColor: SPACE.panel }}
      />
      <div
        className="h-4 w-2/3 animate-pulse rounded"
        style={{ backgroundColor: SPACE.hover }}
      />
    </div>
  );
}

function sourceTables(artifact?: ArtifactState): DataTable[] {
  return (artifact?.tables ?? []).filter((table) => table.source === 'uploaded');
}

function transformedTable(artifact?: ArtifactState): DataTable | null {
  return (artifact?.tables ?? []).find((table) => table.source === 'agent_created') ?? null;
}

export function ArtifactPanel({
  mode,
  open,
  onClose,
  artifact,
  hasFolder,
  files,
  session,
  uploadProgress,
  uploadStage,
  uploadError,
  onUpload,
  onDeleteFile,
  pipeline,
  isGenerating = false,
  onLoadTablePage,
}: ArtifactPanelProps) {
  if (!open) return null;

  const { title, icon: Icon } = variantForMode(mode);
  const uploadedTables = sourceTables(artifact);
  const preparedTable = transformedTable(artifact);

  const renderVariant = () => {
    switch (mode) {
      case 'sources':
        return (
          <SourcesPanel
            disabled={!hasFolder}
            files={files}
            tables={uploadedTables}
            progress={uploadProgress}
            stage={uploadError ? 'error' : uploadStage}
            error={uploadError}
            session={session}
            onFilesSelected={onUpload}
            onDeleteFile={onDeleteFile}
            onLoadTablePage={onLoadTablePage}
          />
        );
      case 'prepare':
        if (!pipeline.hasUploadedTables) {
          return (
            <SourcesPanel
              disabled={!hasFolder}
              files={files}
              tables={uploadedTables}
              progress={uploadProgress}
              stage={uploadError ? 'error' : uploadStage}
              error={uploadError}
              session={session}
              onFilesSelected={onUpload}
              onDeleteFile={onDeleteFile}
              onLoadTablePage={onLoadTablePage}
            />
          );
        }
        return (
          <TableArtifact
            state={isGenerating ? 'running' : 'ready'}
            table={preparedTable}
            sourceTables={uploadedTables}
            onLoadTablePage={onLoadTablePage}
          />
        );
      case 'visualize':
        return <ChartArtifact artifact={artifact} mode={mode} onClose={onClose} />;
      case 'publish':
        return (
          <ReportArtifact
            artifact={artifact}
            mode={mode}
            onClose={onClose}
            state={pipeline.hasTransformTable ? undefined : 'disabled'}
          />
        );
    }
  };

  return (
    <>
      <div
        className="fixed inset-0 z-40 bg-black/60 lg:hidden"
        onClick={onClose}
        aria-hidden="true"
      />

      <aside
        role="complementary"
        aria-label={`${title} panel`}
        className="fixed inset-y-0 right-0 z-50 flex w-full flex-col sm:w-[420px] lg:static lg:inset-auto lg:z-auto lg:w-[440px]"
        style={{
          backgroundColor: SPACE.panelAlt,
          borderLeft: `1px solid ${SPACE.border}`,
        }}
      >
        <header
          className="flex h-12 flex-shrink-0 items-center justify-between px-3"
          style={{ borderBottom: `1px solid ${SPACE.border}` }}
        >
          <div className="flex items-center gap-2" style={{ color: SPACE.text }}>
            <Icon className="h-4 w-4" strokeWidth={2} />
            <span className="text-sm font-medium">{title}</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close artifact panel"
            title="Close"
            className="flex h-8 w-8 items-center justify-center rounded-lg outline-none transition-colors focus-visible:ring-1"
            style={{ color: SPACE.muted }}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = SPACE.hover;
              e.currentTarget.style.color = SPACE.text;
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = 'transparent';
              e.currentTarget.style.color = SPACE.muted;
            }}
          >
            <X className="h-[18px] w-[18px]" strokeWidth={2} />
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto">
          <Suspense fallback={<ArtifactLoading />}>{renderVariant()}</Suspense>
        </div>
      </aside>
    </>
  );
}

export default ArtifactPanel;

