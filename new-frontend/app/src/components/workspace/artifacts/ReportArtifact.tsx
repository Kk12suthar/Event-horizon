import {
  FileText,
  ListTree,
  Eye,
  Download,
  RotateCw,
  Pencil,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Table2,
  BarChart3,
  Link2,
  Lock,
  type LucideIcon,
} from 'lucide-react';
import type { ArtifactState, GeneratedReport, ReportFormat, WorkspaceMode } from '../../../types';
import { SPACE } from '../theme';

/**
 * ReportArtifact - the right artifact panel for Publish (Report) mode.
 *
 * Presentational only; fully driven by props. It renders the section-based
 * report workflow described by Requirement 9:
 *
 *  - Eight report sections (Executive Summary … Appendix) each with a status,
 *    a preview excerpt, evidence chips (table/chart/source), an include/exclude
 *    toggle, and regenerate + edit icon buttons (9.1, 9.2).
 *  - Two views - Outline and Preview - switched via a segmented control (9.3).
 *  - A disabled state until a transformed table exists (9.4).
 *  - An empty state showing the section outline with empty rows (9.5).
 *  - While generating, the section rows fill in one by one - sections still
 *    pending render a skeleton/spinner instead of content (9.6).
 *  - When ready, the Preview view shows the composed report with visible
 *    download buttons (9.7).
 *  - A failed section shows a coral status WITHOUT failing the whole page -
 *    every other section continues to render normally (9.8).
 *
 * Uses only SPACE tokens + lucide-react, matching TableArtifact styling.
 *
 * The default export accepts a broad, all-optional props interface so it is
 * compatible with the `{ mode, artifact, onClose }` contract used by
 * `ArtifactPanel`'s lazy `import('./artifacts/ReportArtifact')`.
 */

/** Lifecycle/status of a single report section (Requirement 9.2 / 9.6 / 9.8). */
export type ReportSectionStatus =
  | 'empty' // not yet drafted
  | 'generating' // currently being filled in
  | 'drafted' // content produced, not reviewed
  | 'reviewed' // content reviewed/approved
  | 'needs-update' // stale / flagged for regeneration
  | 'failed'; // coral failure - does not fail the page

/** Kind of evidence backing a section (Requirement 9.2). */
export type ReportEvidenceKind = 'table' | 'chart' | 'source';

export interface ReportEvidence {
  kind: ReportEvidenceKind;
  /** Short label, e.g. a table name, chart title, or source file. */
  label: string;
}

/** A single report section row view-model. */
export interface ReportSectionVM {
  /** Stable id (also used as the canonical section key). */
  id: string;
  /** Section title, e.g. "Executive Summary". */
  title: string;
  status: ReportSectionStatus;
  /** Short preview excerpt of the drafted content. */
  excerpt?: string;
  /** Evidence chips (table/chart/source). */
  evidence?: ReportEvidence[];
  /** Whether the section is included in the composed report. */
  included: boolean;
  /** Failure detail shown for `failed` sections. */
  error?: string;
}

/** Which of the two views is active (Requirement 9.3). */
export type ReportView = 'outline' | 'preview';

/** Coarse panel state (Requirement 9.4 / 9.5 / 9.6 / 9.7). */
export type ReportArtifactState = 'disabled' | 'empty' | 'generating' | 'ready';

export interface ReportArtifactProps {
  // --- ArtifactPanel pass-through contract (all optional) ---
  /** Active workspace mode (unused here; present for the variant contract). */
  mode?: WorkspaceMode;
  /** Shared artifact snapshot; `artifact.reports[0]` is used as a fallback report. */
  artifact?: ArtifactState;
  /** Close the panel (unused here; present for the variant contract). */
  onClose?: () => void;

  // --- Report-specific props ---
  /** Coarse panel state; derived from sections/report when omitted. */
  state?: ReportArtifactState;
  /** The eight report sections; defaults to the empty canonical outline. */
  sections?: ReportSectionVM[];
  /** Active view; defaults to `'outline'`. */
  view?: ReportView;
  /** The generated report (drives Preview metadata + download availability). */
  report?: GeneratedReport | null;
  /** Download formats offered in Preview; defaults to all four. */
  downloadFormats?: ReportFormat[];

  // --- Callbacks ---
  /** Regenerate a single section. */
  onRegenerateSection?: (sectionId: string) => void;
  /** Edit a single section. */
  onEditSection?: (sectionId: string) => void;
  /** Toggle include/exclude for a section. */
  onToggleSection?: (sectionId: string, included: boolean) => void;
  /** Switch between Outline and Preview. */
  onSwitchView?: (view: ReportView) => void;
  /** Download the composed report in the given format. */
  onDownload?: (format: ReportFormat) => void;
}

/**
 * The eight canonical report sections, in order (Requirement 9.1). Exported so
 * the orchestrator can seed an empty outline with consistent ids/titles.
 */
export const REPORT_SECTIONS: ReadonlyArray<{ id: string; title: string }> = [
  { id: 'executive-summary', title: 'Executive Summary' },
  { id: 'data-overview', title: 'Data Overview' },
  { id: 'key-metrics', title: 'Key Metrics' },
  { id: 'trends-patterns', title: 'Trends and Patterns' },
  { id: 'visual-evidence', title: 'Visual Evidence' },
  { id: 'data-quality-notes', title: 'Data Quality Notes' },
  { id: 'recommendations', title: 'Recommendations' },
  { id: 'appendix', title: 'Appendix' },
];

const ALL_FORMATS: ReportFormat[] = ['PDF', 'PPTX', 'DOCX', 'XLSX'];

/** Build the default empty outline from the canonical section list. */
function defaultSections(): ReportSectionVM[] {
  return REPORT_SECTIONS.map((s) => ({
    id: s.id,
    title: s.title,
    status: 'empty',
    included: true,
  }));
}

/** Visual treatment (icon + color + label) for a section status. */
function statusMeta(status: ReportSectionStatus): {
  Icon: LucideIcon;
  color: string;
  label: string;
  spin?: boolean;
} {
  switch (status) {
    case 'generating':
      return { Icon: Loader2, color: SPACE.muted, label: 'Generating…', spin: true };
    case 'drafted':
      return { Icon: FileText, color: SPACE.text, label: 'Drafted' };
    case 'reviewed':
      return { Icon: CheckCircle2, color: SPACE.success, label: 'Reviewed' };
    case 'needs-update':
      return { Icon: AlertCircle, color: '#EAB308', label: 'Needs update' };
    case 'failed':
      return { Icon: AlertCircle, color: SPACE.danger, label: 'Failed' };
    case 'empty':
    default:
      return { Icon: FileText, color: SPACE.subtle, label: 'Empty' };
  }
}

/** Icon for an evidence kind. */
function evidenceIcon(kind: ReportEvidenceKind): LucideIcon {
  switch (kind) {
    case 'table':
      return Table2;
    case 'chart':
      return BarChart3;
    case 'source':
    default:
      return Link2;
  }
}

/** Derive the coarse panel state from sections + report when not given. */
function deriveState(
  sections: ReportSectionVM[],
  report: GeneratedReport | null | undefined,
): ReportArtifactState {
  if (report?.status === 'ready') return 'ready';
  if (report?.status === 'generating' || sections.some((s) => s.status === 'generating')) {
    return 'generating';
  }
  if (sections.some((s) => s.status !== 'empty')) return 'ready';
  return 'empty';
}

/** Shared section heading. */
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

/** A small icon button used for regenerate/edit row actions. */
function IconButton({
  icon: Icon,
  label,
  onClick,
  danger,
}: {
  icon: LucideIcon;
  label: string;
  onClick?: () => void;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!onClick}
      aria-label={label}
      title={label}
      className="flex h-7 w-7 items-center justify-center rounded-lg outline-none transition-colors focus-visible:ring-1 disabled:opacity-40"
      style={{ color: danger ? SPACE.danger : SPACE.muted, cursor: onClick ? 'pointer' : 'not-allowed' }}
      onMouseEnter={(e) => {
        if (!onClick) return;
        e.currentTarget.style.backgroundColor = SPACE.hover;
        if (!danger) e.currentTarget.style.color = SPACE.text;
      }}
      onMouseLeave={(e) => {
        if (!onClick) return;
        e.currentTarget.style.backgroundColor = 'transparent';
        e.currentTarget.style.color = danger ? SPACE.danger : SPACE.muted;
      }}
    >
      <Icon className="h-3.5 w-3.5" />
    </button>
  );
}

/** An include/exclude toggle pill. */
function IncludeToggle({
  included,
  onToggle,
}: {
  included: boolean;
  onToggle?: () => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={included}
      aria-label={included ? 'Included - click to exclude' : 'Excluded - click to include'}
      title={included ? 'Included in report' : 'Excluded from report'}
      onClick={onToggle}
      disabled={!onToggle}
      className="flex h-4 w-7 flex-shrink-0 items-center rounded-full px-0.5 outline-none transition-colors focus-visible:ring-1 disabled:opacity-40"
      style={{
        backgroundColor: included ? SPACE.success : SPACE.hover,
        cursor: onToggle ? 'pointer' : 'not-allowed',
      }}
    >
      <span
        className="h-3 w-3 rounded-full transition-transform"
        style={{
          backgroundColor: included ? SPACE.bg : SPACE.subtle,
          transform: included ? 'translateX(12px)' : 'translateX(0)',
        }}
      />
    </button>
  );
}

/** Evidence chips row (table/chart/source). */
function EvidenceChips({ evidence }: { evidence: ReportEvidence[] }) {
  if (evidence.length === 0) return null;
  return (
    <div className="mt-1.5 flex flex-wrap gap-1">
      {evidence.map((ev, i) => {
        const Icon = evidenceIcon(ev.kind);
        return (
          <span
            key={`${ev.kind}-${i}`}
            className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px]"
            style={{ backgroundColor: SPACE.hover, color: SPACE.muted }}
          >
            <Icon className="h-3 w-3" />
            <span className="max-w-[120px] truncate">{ev.label}</span>
          </span>
        );
      })}
    </div>
  );
}

/** A single section row in the Outline view (Requirement 9.2). */
function OutlineRow({
  section,
  index,
  onRegenerate,
  onEdit,
  onToggle,
}: {
  section: ReportSectionVM;
  index: number;
  onRegenerate?: () => void;
  onEdit?: () => void;
  onToggle?: () => void;
}) {
  const { Icon, color, label, spin } = statusMeta(section.status);
  const failed = section.status === 'failed';
  const generating = section.status === 'generating';
  const dimmed = !section.included;

  return (
    <div
      className="rounded-lg px-3 py-2.5"
      style={{
        backgroundColor: SPACE.panel,
        // Coral left border for a failed section without failing the page (9.8).
        border: `1px solid ${failed ? SPACE.danger : SPACE.border}`,
        opacity: dimmed ? 0.55 : 1,
      }}
    >
      <div className="flex items-start gap-2.5">
        <span
          className="flex h-4 w-4 flex-shrink-0 items-center justify-center rounded-full text-[10px] font-medium"
          style={{ backgroundColor: SPACE.hover, color: SPACE.muted }}
        >
          {index + 1}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate text-xs font-medium" style={{ color: SPACE.text }}>
              {section.title}
            </span>
            <span className="ml-auto flex flex-shrink-0 items-center gap-1 text-[10px]" style={{ color }}>
              <Icon className={`h-3 w-3 ${spin ? 'animate-spin' : ''}`} />
              {label}
            </span>
          </div>

          {/* Body: skeleton while generating, excerpt/error otherwise (9.6 / 9.8). */}
          {generating ? (
            <div className="mt-2 space-y-1.5">
              <div className="h-2.5 w-full animate-pulse rounded" style={{ backgroundColor: SPACE.hover }} />
              <div className="h-2.5 w-3/4 animate-pulse rounded" style={{ backgroundColor: SPACE.hover }} />
            </div>
          ) : failed ? (
            <p className="mt-1 text-[11px]" style={{ color: SPACE.danger }}>
              {section.error || 'This section failed to generate. Try regenerating it.'}
            </p>
          ) : section.excerpt ? (
            <p className="mt-1 line-clamp-2 text-[11px] leading-relaxed" style={{ color: SPACE.muted }}>
              {section.excerpt}
            </p>
          ) : (
            <p className="mt-1 text-[11px] italic" style={{ color: SPACE.subtle }}>
              No content yet.
            </p>
          )}

          {section.evidence && <EvidenceChips evidence={section.evidence} />}

          {/* Row actions: include/exclude, regenerate, edit (9.2). */}
          <div className="mt-2 flex items-center gap-1">
            <IncludeToggle included={section.included} onToggle={onToggle} />
            <span className="text-[10px]" style={{ color: SPACE.subtle }}>
              {section.included ? 'Included' : 'Excluded'}
            </span>
            <div className="ml-auto flex items-center gap-0.5">
              <IconButton
                icon={RotateCw}
                label={`Regenerate ${section.title}`}
                onClick={onRegenerate}
                danger={failed}
              />
              <IconButton icon={Pencil} label={`Edit ${section.title}`} onClick={onEdit} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/** A composed section block in the Preview view. */
function PreviewSection({ section, index }: { section: ReportSectionVM; index: number }) {
  const failed = section.status === 'failed';
  return (
    <div className="px-4">
      <div className="flex items-baseline gap-2">
        <span className="text-[11px]" style={{ color: SPACE.subtle }}>
          {index + 1}.
        </span>
        <h3 className="text-sm font-semibold" style={{ color: SPACE.text }}>
          {section.title}
        </h3>
        {failed && (
          <span className="ml-auto inline-flex items-center gap-1 text-[10px]" style={{ color: SPACE.danger }}>
            <AlertCircle className="h-3 w-3" />
            Failed
          </span>
        )}
      </div>
      {failed ? (
        <p className="mt-1 text-xs" style={{ color: SPACE.danger }}>
          {section.error || 'This section could not be generated and is omitted from the export.'}
        </p>
      ) : section.excerpt ? (
        <p className="mt-1 text-xs leading-relaxed" style={{ color: SPACE.muted }}>
          {section.excerpt}
        </p>
      ) : (
        <p className="mt-1 text-xs italic" style={{ color: SPACE.subtle }}>
          No content.
        </p>
      )}
      {section.evidence && <EvidenceChips evidence={section.evidence} />}
    </div>
  );
}

/** The Outline/Preview segmented control (Requirement 9.3). */
function ViewToggle({
  view,
  onSwitchView,
}: {
  view: ReportView;
  onSwitchView?: (v: ReportView) => void;
}) {
  const items: { key: ReportView; label: string; Icon: LucideIcon }[] = [
    { key: 'outline', label: 'Outline', Icon: ListTree },
    { key: 'preview', label: 'Preview', Icon: Eye },
  ];
  return (
    <div
      className="flex items-center gap-0.5 rounded-lg p-0.5"
      style={{ backgroundColor: SPACE.panel, border: `1px solid ${SPACE.border}` }}
      role="tablist"
      aria-label="Report view"
    >
      {items.map(({ key, label, Icon }) => {
        const active = view === key;
        return (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onSwitchView?.(key)}
            className="flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium outline-none transition-colors focus-visible:ring-1"
            style={{
              backgroundColor: active ? 'rgba(228, 228, 231, 0.1)' : 'transparent',
              color: active ? SPACE.text : SPACE.muted,
              cursor: 'pointer',
            }}
          >
            <Icon className="h-3.5 w-3.5" />
            {label}
          </button>
        );
      })}
    </div>
  );
}

/** Download buttons shown in Preview when the report is ready (Requirement 9.7). */
function DownloadBar({
  formats,
  ready,
  onDownload,
}: {
  formats: ReportFormat[];
  ready: boolean;
  onDownload?: (format: ReportFormat) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 px-4 py-3">
      <span className="mr-1 text-[11px] font-medium uppercase tracking-wide" style={{ color: SPACE.subtle }}>
        Download
      </span>
      {formats.map((fmt) => {
        const enabled = ready && !!onDownload;
        return (
          <button
            key={fmt}
            type="button"
            onClick={enabled ? () => onDownload?.(fmt) : undefined}
            disabled={!enabled}
            className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium outline-none transition-colors focus-visible:ring-1 disabled:opacity-40"
            style={{
              backgroundColor: 'transparent',
              color: SPACE.muted,
              border: `1px solid ${SPACE.border}`,
              cursor: enabled ? 'pointer' : 'not-allowed',
            }}
            onMouseEnter={(e) => {
              if (!enabled) return;
              e.currentTarget.style.backgroundColor = SPACE.hover;
              e.currentTarget.style.color = SPACE.text;
            }}
            onMouseLeave={(e) => {
              if (!enabled) return;
              e.currentTarget.style.backgroundColor = 'transparent';
              e.currentTarget.style.color = SPACE.muted;
            }}
          >
            <Download className="h-3.5 w-3.5" />
            {fmt}
          </button>
        );
      })}
    </div>
  );
}

export function ReportArtifact({
  artifact,
  state,
  sections,
  view = 'outline',
  report,
  downloadFormats = ALL_FORMATS,
  onRegenerateSection,
  onEditSection,
  onToggleSection,
  onSwitchView,
  onDownload,
}: ReportArtifactProps) {
  const resolvedReport = report ?? artifact?.reports?.[0] ?? null;
  const resolvedSections = sections && sections.length > 0 ? sections : defaultSections();
  const resolvedState = state ?? deriveState(resolvedSections, resolvedReport);

  // --- Disabled: no transformed table yet (Requirement 9.4) ---
  if (resolvedState === 'disabled') {
    return (
      <div className="flex h-full flex-col" style={{ backgroundColor: SPACE.panelAlt }}>
        <div className="flex flex-1 flex-col items-center justify-center px-8 text-center">
          <div
            className="mb-3 flex h-11 w-11 items-center justify-center rounded-xl"
            style={{ backgroundColor: SPACE.panel, border: `1px solid ${SPACE.border}`, color: SPACE.muted }}
          >
            <Lock className="h-5 w-5" strokeWidth={1.75} />
          </div>
          <div className="text-sm font-medium" style={{ color: SPACE.text }}>
            Publishing is locked
          </div>
          <p className="mt-1 max-w-[260px] text-xs" style={{ color: SPACE.muted }}>
            Prepare a transformed table first, then come back to compose and export a report from it.
          </p>
        </div>
      </div>
    );
  }

  const isPreview = view === 'preview';
  const generating = resolvedState === 'generating';
  const ready = resolvedState === 'ready' && resolvedReport?.status === 'ready';
  const includedSections = resolvedSections.filter((s) => s.included);

  return (
    <div className="flex h-full flex-col" style={{ backgroundColor: SPACE.panelAlt }}>
      {/* Header: title + view toggle (Requirement 9.3). */}
      <div
        className="flex flex-shrink-0 items-center gap-2 border-b px-4 py-2.5"
        style={{ borderColor: SPACE.border }}
      >
        <FileText className="h-4 w-4" style={{ color: SPACE.text }} />
        <span className="truncate text-sm font-medium" style={{ color: SPACE.text }}>
          {resolvedReport?.name || 'Report'}
        </span>
        {generating && (
          <span className="flex items-center gap-1 text-[11px]" style={{ color: SPACE.muted }}>
            <Loader2 className="h-3 w-3 animate-spin" />
            Generating
          </span>
        )}
        <div className="ml-auto">
          <ViewToggle view={view} onSwitchView={onSwitchView} />
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto pb-4">
        {isPreview ? (
          // --- Preview view (Requirement 9.7) ---
          <>
            <DownloadBar formats={downloadFormats} ready={!!ready} onDownload={onDownload} />
            {!ready && (
              <p className="px-4 pb-2 text-[11px]" style={{ color: SPACE.subtle }}>
                {generating
                  ? 'Report is still generating - downloads unlock when it is ready.'
                  : 'Compose sections in Outline, then generate the report to enable downloads.'}
              </p>
            )}
            <div className="space-y-4 pt-1">
              {includedSections.length === 0 ? (
                <p className="px-4 text-xs italic" style={{ color: SPACE.subtle }}>
                  No sections included. Enable sections in the Outline view.
                </p>
              ) : (
                includedSections.map((section, i) => (
                  <PreviewSection key={section.id} section={section} index={i} />
                ))
              )}
            </div>
          </>
        ) : (
          // --- Outline view (Requirement 9.5 empty / 9.6 generating / 9.2 rows) ---
          <>
            <SectionLabel icon={ListTree}>
              Sections ({resolvedSections.length})
            </SectionLabel>
            <div className="space-y-2 px-4">
              {resolvedSections.map((section, i) => (
                <OutlineRow
                  key={section.id}
                  section={section}
                  index={i}
                  onRegenerate={
                    onRegenerateSection ? () => onRegenerateSection(section.id) : undefined
                  }
                  onEdit={onEditSection ? () => onEditSection(section.id) : undefined}
                  onToggle={
                    onToggleSection
                      ? () => onToggleSection(section.id, !section.included)
                      : undefined
                  }
                />
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default ReportArtifact;
