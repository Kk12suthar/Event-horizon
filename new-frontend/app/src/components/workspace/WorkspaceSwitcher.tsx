import { useMemo, useState } from 'react';
import {
  ChevronDown,
  ChevronRight,
  Folder as FolderIcon,
  FolderPlus,
  Loader2,
  Plus,
  Search,
} from 'lucide-react';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import type { Folder, Project } from '@/types';
import { SPACE } from './theme';

/**
 * WorkspaceSwitcher - the primary hierarchy surface in the chat-first shell.
 *
 * Replaces the legacy Projects page for in-workspace navigation. A topbar
 * popover/command palette that lets the user switch project -> folder, search
 * across both, and create either inline (reusing `appState.createProject` /
 * `createFolder`). On folder pick it calls `onSelectFolder`, which the
 * orchestrator wires to `loadFolderContext`.
 *
 * Monochrome SPACE tokens only - white/light-gray accent, no purple/blue.
 *
 * Requirements: 5.1 (project list + search + new project), 5.2 (folder
 * create / selection within the selected project).
 */

export interface WorkspaceSwitcherProps {
  projects: Project[];
  folders: Folder[];
  selectedProject: Project | null;
  selectedFolder: Folder | null;
  /** Called with the folder id when the user picks a folder. */
  onSelectFolder: (folderId: string) => void;
  /** Inline create - reuses appState.createProject (status defaulted upstream). */
  onCreateProject: (name: string, description: string) => Promise<Project | null>;
  /** Inline create - reuses appState.createFolder. */
  onCreateFolder: (
    projectId: string,
    name: string,
    description: string,
  ) => Promise<Folder | null>;
}

/** Small status dot + label for a folder's status. */
function FolderStatusDot({ status }: { status: Folder['status'] }) {
  const color =
    status === 'Active' ? SPACE.success : status === 'Deleted' ? SPACE.danger : SPACE.subtle;
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className="h-1.5 w-1.5 flex-shrink-0 rounded-full"
        style={{ backgroundColor: color }}
      />
      <span className="text-[10px] uppercase tracking-wider" style={{ color: SPACE.subtle }}>
        {status}
      </span>
    </span>
  );
}

/** Inline create form shared by project/folder creation. */
function InlineCreateForm({
  label,
  onSubmit,
  onCancel,
}: {
  label: string;
  onSubmit: (name: string, description: string) => Promise<void>;
  onCancel: () => void;
}) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const canSubmit = name.trim().length > 0 && !submitting;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    try {
      await onSubmit(name.trim(), description.trim());
      setName('');
      setDescription('');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="flex flex-col gap-2 rounded-lg p-2"
      style={{ backgroundColor: SPACE.hover, border: `1px solid ${SPACE.border}` }}
    >
      <input
        autoFocus
        value={name}
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') void handleSubmit();
          if (e.key === 'Escape') onCancel();
        }}
        placeholder={`${label} name`}
        className="w-full rounded-md px-2 py-1.5 text-sm outline-none"
        style={{
          backgroundColor: SPACE.panelAlt,
          color: SPACE.text,
          border: `1px solid ${SPACE.border}`,
        }}
      />
      <input
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') void handleSubmit();
          if (e.key === 'Escape') onCancel();
        }}
        placeholder="Description (optional)"
        className="w-full rounded-md px-2 py-1.5 text-xs outline-none"
        style={{
          backgroundColor: SPACE.panelAlt,
          color: SPACE.muted,
          border: `1px solid ${SPACE.border}`,
        }}
      />
      <div className="flex items-center justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="rounded-md px-2 py-1 text-xs transition-colors"
          style={{ color: SPACE.muted }}
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={() => void handleSubmit()}
          disabled={!canSubmit}
          className="inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium transition-colors disabled:opacity-40"
          style={{ backgroundColor: SPACE.brand, color: SPACE.onBrand }}
        >
          {submitting && <Loader2 className="h-3 w-3 animate-spin" />}
          Create
        </button>
      </div>
    </div>
  );
}

export function WorkspaceSwitcher({
  projects,
  folders,
  selectedProject,
  selectedFolder,
  onSelectFolder,
  onCreateProject,
  onCreateFolder,
}: WorkspaceSwitcherProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  // Project whose folders are shown in the popover (defaults to the selected one).
  const [activeProjectId, setActiveProjectId] = useState<string | null>(
    selectedProject?.id ?? null,
  );
  const [creatingProject, setCreatingProject] = useState(false);
  const [creatingFolder, setCreatingFolder] = useState(false);

  const normalizedQuery = query.trim().toLowerCase();

  const filteredProjects = useMemo(() => {
    if (!normalizedQuery) return projects;
    return projects.filter((p) => p.name.toLowerCase().includes(normalizedQuery));
  }, [projects, normalizedQuery]);

  const effectiveProjectId = activeProjectId ?? selectedProject?.id ?? null;

  const projectFolders = useMemo(() => {
    const scoped = folders.filter((f) => f.projectId === effectiveProjectId);
    if (!normalizedQuery) return scoped;
    return scoped.filter((f) => f.name.toLowerCase().includes(normalizedQuery));
  }, [folders, effectiveProjectId, normalizedQuery]);

  const handleSelectFolder = (folderId: string) => {
    onSelectFolder(folderId);
    setOpen(false);
    setQuery('');
  };

  const handleCreateProject = async (name: string, description: string) => {
    const created = await onCreateProject(name, description);
    if (created) setActiveProjectId(created.id);
    setCreatingProject(false);
  };

  const handleCreateFolder = async (name: string, description: string) => {
    if (!effectiveProjectId) return;
    const created = await onCreateFolder(effectiveProjectId, name, description);
    if (created) handleSelectFolder(created.id);
    setCreatingFolder(false);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label="Switch project or folder"
          className="flex min-w-0 items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm outline-none transition-colors focus-visible:ring-1"
          style={{ color: SPACE.text }}
          onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor = SPACE.hover;
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = 'transparent';
          }}
        >
          <span className="truncate" style={{ color: SPACE.muted }}>
            {selectedProject?.name ?? 'Select project'}
          </span>
          <ChevronRight className="h-3.5 w-3.5 flex-shrink-0" style={{ color: SPACE.subtle }} />
          <span className="truncate font-medium">
            {selectedFolder?.name ?? 'Select folder'}
          </span>
          <ChevronDown className="h-3.5 w-3.5 flex-shrink-0" style={{ color: SPACE.subtle }} />
        </button>
      </PopoverTrigger>

      <PopoverContent
        align="start"
        sideOffset={6}
        className="w-[380px] p-0"
        style={{
          backgroundColor: SPACE.panel,
          border: `1px solid ${SPACE.border}`,
          color: SPACE.text,
        }}
      >
        {/* Search */}
        <div
          className="flex items-center gap-2 px-3 py-2.5"
          style={{ borderBottom: `1px solid ${SPACE.border}` }}
        >
          <Search className="h-4 w-4 flex-shrink-0" style={{ color: SPACE.subtle }} />
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search projects and folders…"
            className="w-full bg-transparent text-sm outline-none placeholder:text-[#5C5C5C]"
            style={{ color: SPACE.text }}
          />
        </div>

        <div className="flex max-h-[420px] flex-col gap-3 overflow-y-auto p-3">
          {/* Projects */}
          <section className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between px-1">
              <span
                className="text-[10px] font-semibold uppercase tracking-wider"
                style={{ color: SPACE.subtle }}
              >
                Projects
              </span>
              <button
                type="button"
                onClick={() => setCreatingProject((v) => !v)}
                className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] transition-colors"
                style={{ color: SPACE.muted }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.color = SPACE.text;
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.color = SPACE.muted;
                }}
              >
                <Plus className="h-3 w-3" />
                New project
              </button>
            </div>

            {creatingProject && (
              <InlineCreateForm
                label="Project"
                onSubmit={handleCreateProject}
                onCancel={() => setCreatingProject(false)}
              />
            )}

            {filteredProjects.length === 0 && !creatingProject ? (
              <p className="px-1 py-1 text-xs" style={{ color: SPACE.subtle }}>
                No projects found.
              </p>
            ) : (
              filteredProjects.map((project) => {
                const isActive = project.id === effectiveProjectId;
                return (
                  <button
                    key={project.id}
                    type="button"
                    onClick={() => setActiveProjectId(project.id)}
                    className="flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors"
                    style={{
                      backgroundColor: isActive ? SPACE.hover : 'transparent',
                      color: isActive ? SPACE.text : SPACE.muted,
                    }}
                    onMouseEnter={(e) => {
                      if (!isActive) e.currentTarget.style.backgroundColor = SPACE.hover;
                    }}
                    onMouseLeave={(e) => {
                      if (!isActive) e.currentTarget.style.backgroundColor = 'transparent';
                    }}
                  >
                    <span className="truncate">{project.name}</span>
                    <span className="flex-shrink-0 text-[11px]" style={{ color: SPACE.subtle }}>
                      {project.folderCount}
                    </span>
                  </button>
                );
              })
            )}
          </section>

          {/* Folders for the active project */}
          <section className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between px-1">
              <span
                className="text-[10px] font-semibold uppercase tracking-wider"
                style={{ color: SPACE.subtle }}
              >
                Folders
              </span>
              <button
                type="button"
                onClick={() => setCreatingFolder((v) => !v)}
                disabled={!effectiveProjectId}
                className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] transition-colors disabled:opacity-40"
                style={{ color: SPACE.muted }}
                onMouseEnter={(e) => {
                  if (effectiveProjectId) e.currentTarget.style.color = SPACE.text;
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.color = SPACE.muted;
                }}
              >
                <FolderPlus className="h-3 w-3" />
                New folder
              </button>
            </div>

            {creatingFolder && effectiveProjectId && (
              <InlineCreateForm
                label="Folder"
                onSubmit={handleCreateFolder}
                onCancel={() => setCreatingFolder(false)}
              />
            )}

            {!effectiveProjectId ? (
              <p className="px-1 py-1 text-xs" style={{ color: SPACE.subtle }}>
                Select a project to see its folders.
              </p>
            ) : projectFolders.length === 0 && !creatingFolder ? (
              <p className="px-1 py-1 text-xs" style={{ color: SPACE.subtle }}>
                No folders yet.
              </p>
            ) : (
              projectFolders.map((folder) => {
                const isSelected = folder.id === selectedFolder?.id;
                return (
                  <button
                    key={folder.id}
                    type="button"
                    onClick={() => handleSelectFolder(folder.id)}
                    className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors"
                    style={{
                      backgroundColor: isSelected ? SPACE.hover : 'transparent',
                      color: isSelected ? SPACE.text : SPACE.muted,
                    }}
                    onMouseEnter={(e) => {
                      if (!isSelected) e.currentTarget.style.backgroundColor = SPACE.hover;
                    }}
                    onMouseLeave={(e) => {
                      if (!isSelected) e.currentTarget.style.backgroundColor = 'transparent';
                    }}
                  >
                    <FolderIcon
                      className="h-4 w-4 flex-shrink-0"
                      style={{ color: isSelected ? SPACE.text : SPACE.subtle }}
                    />
                    <span className="min-w-0 flex-1 truncate">{folder.name}</span>
                    <FolderStatusDot status={folder.status} />
                  </button>
                );
              })
            )}
          </section>
        </div>
      </PopoverContent>
    </Popover>
  );
}

export default WorkspaceSwitcher;
