import { PanelRight, PanelRightClose, Radio } from 'lucide-react';
import type { Folder, Project, Session } from '@/types';
import { SPACE } from './theme';
import { WorkspaceSwitcher } from './WorkspaceSwitcher';

/**
 * WorkspaceTopbar - the compact header above the chat column.
 *
 * Shows the folder breadcrumb (Project / Folder) as a clickable
 * WorkspaceSwitcher, a small folder status, a current-session indicator, and
 * an artifact-panel toggle. Thin border, compact density, icon-first actions
 * with tooltips - no marketing hero. Monochrome SPACE tokens only.
 *
 * Requirements: 4.2 (breadcrumb + folder status + session indicator),
 * 5.1 / 5.2 (hierarchy switching via the embedded WorkspaceSwitcher).
 */

export interface WorkspaceTopbarProps {
  projects: Project[];
  folders: Folder[];
  selectedProject: Project | null;
  selectedFolder: Folder | null;
  activeSession: Session | null;
  /** Whether the right artifact panel is currently open. */
  artifactOpen: boolean;
  onToggleArtifact: () => void;
  onSelectFolder: (folderId: string) => void;
}

/** Small status pill for the selected folder. */
function FolderStatusPill({ status }: { status: Folder['status'] }) {
  const color =
    status === 'Active' ? SPACE.success : status === 'Deleted' ? SPACE.danger : SPACE.subtle;
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider"
      style={{ backgroundColor: SPACE.hover, color: SPACE.muted }}
    >
      <span
        className="h-1.5 w-1.5 rounded-full"
        style={{ backgroundColor: color }}
      />
      {status}
    </span>
  );
}

/** Current-session indicator dot + short id. */
function SessionIndicator({ session }: { session: Session | null }) {
  const active = session?.status === 'active';
  const label = session
    ? `Session ${session.id.slice(0, 8)}`
    : 'No active session';
  return (
    <span
      className="hidden items-center gap-1.5 text-xs sm:inline-flex"
      style={{ color: SPACE.muted }}
      title={label}
    >
      <Radio
        className="h-3.5 w-3.5"
        style={{ color: active ? SPACE.success : SPACE.subtle }}
      />
      <span className="max-w-[140px] truncate">{label}</span>
    </span>
  );
}

export function WorkspaceTopbar({
  projects,
  folders,
  selectedProject,
  selectedFolder,
  activeSession,
  artifactOpen,
  onToggleArtifact,
  onSelectFolder,
}: WorkspaceTopbarProps) {
  return (
    <header
      className="flex h-12 flex-shrink-0 items-center justify-between gap-3 px-3"
      style={{
        backgroundColor: SPACE.panelAlt,
        borderBottom: `1px solid ${SPACE.border}`,
      }}
    >
      {/* Left: breadcrumb switcher + folder status */}
      <div className="flex min-w-0 items-center gap-2">
        <WorkspaceSwitcher
          projects={projects}
          folders={folders}
          selectedProject={selectedProject}
          selectedFolder={selectedFolder}
          onSelectFolder={onSelectFolder}
        />
        {selectedFolder && <FolderStatusPill status={selectedFolder.status} />}
      </div>

      {/* Right: session indicator + artifact toggle */}
      <div className="flex flex-shrink-0 items-center gap-3">
        <SessionIndicator session={activeSession} />

        <div className="group relative flex justify-center">
          <button
            type="button"
            onClick={onToggleArtifact}
            aria-label={artifactOpen ? 'Hide artifact panel' : 'Show artifact panel'}
            aria-pressed={artifactOpen}
            title={artifactOpen ? 'Hide artifact panel' : 'Show artifact panel'}
            className="flex h-8 w-8 items-center justify-center rounded-lg outline-none transition-colors focus-visible:ring-1"
            style={{
              color: artifactOpen ? SPACE.text : SPACE.muted,
              backgroundColor: artifactOpen ? SPACE.hover : 'transparent',
            }}
            onMouseEnter={(e) => {
              if (artifactOpen) return;
              e.currentTarget.style.backgroundColor = SPACE.hover;
              e.currentTarget.style.color = SPACE.text;
            }}
            onMouseLeave={(e) => {
              if (artifactOpen) return;
              e.currentTarget.style.backgroundColor = 'transparent';
              e.currentTarget.style.color = SPACE.muted;
            }}
          >
            {artifactOpen ? (
              <PanelRightClose className="h-[18px] w-[18px]" strokeWidth={2} />
            ) : (
              <PanelRight className="h-[18px] w-[18px]" strokeWidth={2} />
            )}
          </button>
        </div>
      </div>
    </header>
  );
}

export default WorkspaceTopbar;
