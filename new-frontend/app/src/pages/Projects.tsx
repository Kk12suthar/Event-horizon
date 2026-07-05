import { useState, useMemo, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Plus, Search, Grid3X3, List, FolderOpen,
  MoreHorizontal, Pencil, Trash2, Info,
  Wand2, BarChart3, FileText, Lock,
  type LucideIcon,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { EmptyState } from '@/components/EmptyState';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { SPACE } from '@/components/workspace/theme';
import { usePipelineStage } from '@/hooks/usePipelineStage';
import { useAppState } from '@/hooks/useAppState';
import { useAuth } from '@/hooks/useAuth';
import { fetchAllFolderTables } from '@/lib/api';
import type { DataTable, Folder, PipelineState, WorkspaceMode } from '@/types';

/**
 * The three workflow modes shown on every folder card, in pipeline order.
 * Sources/upload is handled inside Prepare, so Home and the Workspace expose
 * the same Prepare - Visualize - Publish workflow.
 */
const WORKFLOW_MODES: { id: WorkspaceMode; label: string; icon: LucideIcon }[] = [
  { id: 'prepare', label: 'Prepare', icon: Wand2 },
  { id: 'visualize', label: 'Visualize', icon: BarChart3 },
  { id: 'publish', label: 'Publish', icon: FileText },
];

/** Tooltip copy explaining why a locked workflow icon is unavailable. */
const LOCKED_REASON: Record<WorkspaceMode, string> = {
  sources: 'You need upload permission to add sources.',
  prepare: 'Prepare is always available.',
  visualize: 'Create a transformed table in Prepare first.',
  publish: 'Create a transformed table in Prepare first.',
};

/**
 * Build a minimal `DataTable[]` for a folder from its cached `entities.tables`.
 * These are always treated as uploaded sources; the transform/agent-created
 * distinction is only known after {@link fetchAllFolderTables} resolves. Used
 * as the synchronous initial state so cards gate sensibly before the network
 * round-trip completes.
 */
function folderEntitiesToTables(folder: Folder): DataTable[] {
  const uploaded = folder.entities?.tables || {};
  return Object.entries(uploaded).map(([id, name]) => ({
    id,
    name: String(name),
    source: 'uploaded' as const,
    columns: [],
    rows: [],
    rowCount: 0,
    hasMore: true,
    page: 0,
  }));
}

/**
 * Load a folder's tables (mirroring `useAppState.loadTablesForFolder` but
 * without mutating global state) so per-card gating can distinguish uploaded
 * from agent-created tables. Falls back to cached entities if the request
 * fails.
 */
async function loadFolderTablesLocal(folder: Folder): Promise<DataTable[]> {
  const uploaded = folder.entities?.tables || {};
  const tableTypes: Record<string, 'uploaded' | 'agent_created'> = {};
  Object.keys(uploaded).forEach((id) => {
    tableTypes[id] = 'uploaded';
  });

  let merged: Record<string, string> = { ...(uploaded as Record<string, string>) };
  try {
    const dbTables = await fetchAllFolderTables(folder.id);
    if (dbTables.tables) merged = { ...merged, ...dbTables.tables };
    if (dbTables.table_types) Object.assign(tableTypes, dbTables.table_types);
  } catch {
    // Cached entities are still enough to render uploaded-table gating.
  }

  return Object.entries(merged).map(([id, name]) => ({
    id,
    name: String(name),
    source: tableTypes[id] || 'uploaded',
    columns: [],
    rows: [],
    rowCount: 0,
    hasMore: true,
    page: 0,
  }));
}

/**
 * Derive the pipeline gating state for a single folder card. Seeds from cached
 * entities, then refreshes from the tables API. Prepare is always available for
 * users with upload access; Visualize and Publish require a transformed table.
 */
function useFolderPipeline(folder: Folder, canUpload: boolean): PipelineState {
  const [tables, setTables] = useState<DataTable[]>(() => folderEntitiesToTables(folder));

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const next = await loadFolderTablesLocal(folder);
      if (!cancelled) setTables(next);
    })();
    return () => {
      cancelled = true;
    };
    // Re-derive when the folder identity or its cached table set changes. We
    // intentionally key off these fields rather than the whole `folder` object
    // to avoid refetching on unrelated parent re-renders.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [folder.id, folder.entities?.tables]);

  const pipeline = usePipelineStage(tables);

  return useMemo(
    () => ({
      ...pipeline,
      enabledModes: { ...pipeline.enabledModes, prepare: canUpload && pipeline.enabledModes.prepare },
    }),
    [pipeline, canUpload],
  );
}

/**
 * The row of three gated workflow icons shared by the folder grid card and list
 * row. Enabled icons use a subtle white tint and open the Workspace for the
 * folder in the matching mode; disabled icons render at 40% opacity with a
 * `not-allowed` cursor, a lock glyph, and a tooltip (Requirement 5.5/5.6). A
 * small green dot marks the completed Prepare step once it produced
 * a transformed table).
 */
function WorkflowActions({
  folder,
  pipeline,
  onOpen,
  size = 'md',
}: {
  folder: Folder;
  pipeline: PipelineState;
  onOpen: (folderId: string, mode: WorkspaceMode) => void;
  size?: 'sm' | 'md';
}) {
  const completed: Record<WorkspaceMode, boolean> = {
    sources: pipeline.hasUploadedTables,
    prepare: pipeline.hasTransformTable,
    visualize: false,
    publish: false,
  };
  const box = size === 'sm' ? 'h-7 w-7' : 'h-8 w-8';
  const glyph = size === 'sm' ? 'h-3.5 w-3.5' : 'h-4 w-4';

  return (
    <div className="flex items-center gap-1">
      {WORKFLOW_MODES.map(({ id, label, icon: Icon }) => {
        const enabled = pipeline.enabledModes[id];
        const isComplete = enabled && completed[id];
        return (
          <div key={id} className="group relative flex">
            <button
              type="button"
              disabled={!enabled}
              onClick={() => enabled && onOpen(folder.id, id)}
              aria-label={enabled ? `Open ${folder.name} in ${label}` : LOCKED_REASON[id]}
              title={enabled ? label : LOCKED_REASON[id]}
              className={`relative flex ${box} items-center justify-center rounded-md transition-colors`}
              style={{
                color: enabled ? SPACE.text : SPACE.muted,
                opacity: enabled ? 1 : 0.4,
                cursor: enabled ? 'pointer' : 'not-allowed',
                backgroundColor: 'transparent',
              }}
              onMouseEnter={(e) => {
                if (!enabled) return;
                e.currentTarget.style.backgroundColor = SPACE.hover;
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.backgroundColor = 'transparent';
              }}
            >
              <Icon className={glyph} strokeWidth={2} />
              {!enabled && (
                <Lock
                  className="absolute -right-0.5 -top-0.5 h-2.5 w-2.5"
                  strokeWidth={2.5}
                  aria-hidden="true"
                />
              )}
              {isComplete && (
                <span
                  className="absolute -right-0.5 -top-0.5 h-1.5 w-1.5 rounded-full"
                  style={{ backgroundColor: SPACE.success }}
                  aria-hidden="true"
                />
              )}
            </button>

            {!enabled && (
              <span
                role="tooltip"
                className="pointer-events-none absolute left-1/2 top-full z-50 mt-1.5 -translate-x-1/2 whitespace-nowrap rounded-md px-2 py-1 text-xs font-medium opacity-0 shadow-md transition-opacity duration-150 group-hover:opacity-100"
                style={{
                  backgroundColor: SPACE.panel,
                  color: SPACE.text,
                  border: `1px solid ${SPACE.border}`,
                }}
              >
                {LOCKED_REASON[id]}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function Projects() {
  const navigate = useNavigate();
  const appState = useAppState();
  const { isAdmin, isAnalyst } = useAuth();
  const [searchQuery, setSearchQuery] = useState('');
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
  const [showCreateProject, setShowCreateProject] = useState(false);
  const [showCreateFolder, setShowCreateFolder] = useState(false);
  const [showProjectInfo, setShowProjectInfo] = useState(false);
  const [showFolderInfoId, setShowFolderInfoId] = useState<string | null>(null);
  const [showDeleteProject, setShowDeleteProject] = useState(false);
  const [showDeleteFolder, setShowDeleteFolder] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [editingProjectId, setEditingProjectId] = useState<string | null>(null);

  const [projectForm, setProjectForm] = useState({ name: '', description: '', status: 'Active' as string });
  const [folderForm, setFolderForm] = useState({ name: '', description: '', status: 'Active' as string });

  const filteredProjects = useMemo(() => {
    return appState.projectList.filter(p =>
      p.name.toLowerCase().includes(searchQuery.toLowerCase())
    );
  }, [appState.projectList, searchQuery]);

  const projectFolders = appState.selectedProject
    ? appState.folderList.filter(folder => folder.projectId === appState.selectedProject?.id)
    : [];

  const resetProjectForm = () => {
    setProjectForm({ name: '', description: '', status: 'Active' });
    setEditingProjectId(null);
  };
  const resetFolderForm = () => setFolderForm({ name: '', description: '', status: 'Active' });

  const handleCreateProject = async () => {
    if (!projectForm.name.trim()) return;
    setIsSubmitting(true);
    try {
      if (editingProjectId) {
        await appState.updateProject(editingProjectId, {
          name: projectForm.name,
          description: projectForm.description,
          status: projectForm.status as 'Active' | 'Archived' | 'Published' | 'Deleted',
        });
      } else {
        const project = await appState.createProject(projectForm.name, projectForm.description, projectForm.status as 'Active' | 'Archived' | 'Published' | 'Deleted');
        if (project) appState.selectProject(project);
      }
      setShowCreateProject(false);
      resetProjectForm();
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCreateFolder = async () => {
    if (!folderForm.name.trim() || !appState.selectedProject) return;
    setIsSubmitting(true);
    try {
      await appState.createFolder(folderForm.name, folderForm.description, appState.selectedProject.id);
      setShowCreateFolder(false);
      resetFolderForm();
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDeleteProject = async () => {
    if (!appState.selectedProject) return;
    setIsSubmitting(true);
    try {
      await appState.deleteProject(appState.selectedProject.id);
      setShowDeleteProject(false);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDeleteFolder = async (folderId: string) => {
    setIsSubmitting(true);
    try {
      await appState.deleteFolder(folderId);
      setShowDeleteFolder(null);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Activating a folder workflow icon opens the Workspace for that folder in
  // the corresponding mode (Requirement 5.6).
  const openWorkspace = (folderId: string, mode: WorkspaceMode) => {
    const folder = appState.folderList.find(f => f.id === folderId);
    if (folder) appState.selectFolder(folder);
    navigate(`/app/workspace?folderId=${folderId}&mode=${mode}`);
  };

  const canUpload = isAdmin || isAnalyst;

  const infoFolder = showFolderInfoId ? appState.folderList.find(f => f.id === showFolderInfoId) : null;

  return (
    <div className="flex h-full min-h-0 overflow-hidden bg-[#000000] max-md:flex-col">
      {/* Project Sidebar */}
      <div className="w-[300px] flex-shrink-0 bg-[#151515]/95 border-r border-[#2E2E2E] flex min-h-0 flex-col max-md:h-[260px] max-md:w-full max-md:border-b max-md:border-r-0 lg:w-[320px]">
        <div className="p-4 border-b border-[#2E2E2E]">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-white uppercase tracking-wider">Projects</h2>
            {isAdmin && (
              <Button
                size="sm"
                onClick={() => { resetProjectForm(); setShowCreateProject(true); }}
                className="h-8 bg-[#c16e43] text-[#0A0A0A] hover:bg-[#d08a5e]"
              >
                <Plus className="w-4 h-4 mr-1" />
                New
              </Button>
            )}
          </div>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#8C8C8C]" />
            <Input
              placeholder="Search projects..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="h-9 pl-9 bg-[#000000] border-[#2E2E2E] text-white placeholder:text-[#8C8C8C] text-sm"
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {filteredProjects.length === 0 ? (
            <div className="px-3 py-8 text-center">
              <p className="text-sm text-[#8C8C8C]">No projects found</p>
            </div>
          ) : (
            filteredProjects.map(project => (
              <button
                key={project.id}
                onClick={() => appState.selectProject(project)}
                className={`w-full text-left px-3 py-3 rounded-lg transition-all ${
                  appState.selectedProject?.id === project.id
                    ? 'bg-[#c16e43]/10 border-l-2 border-[#c16e43]'
                    : 'hover:bg-[#1E1E1E] border-l-2 border-transparent'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className={`text-sm font-medium truncate ${
                    appState.selectedProject?.id === project.id ? 'text-[#E4E4E7]' : 'text-white'
                  }`}>
                    {project.name}
                  </span>
                  <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
                    project.status === 'Active' ? 'bg-[#22C55E]/10 text-[#22C55E]' :
                    project.status === 'Archived' ? 'bg-[#8C8C8C]/10 text-[#8C8C8C]' :
                    'bg-[#F97066]/10 text-[#F97066]'
                  }`}>
                    {project.status}
                  </span>
                </div>
              </button>
            ))
          )}
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 min-w-0 overflow-y-auto px-6 py-5">
        {!appState.selectedProject ? (
          <EmptyState
            icon="folder"
            title="Select a project"
            description="Choose a project from the sidebar to view and manage its folders."
            action={isAdmin ? {
              label: 'Create your first project',
              onClick: () => { resetProjectForm(); setShowCreateProject(true); }
            } : undefined}
          />
        ) : (
          <div className="animate-fade-in">
            {/* Project Header */}
            <div className="mb-6">
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-3">
                    <h1 className="text-2xl font-bold text-white">{appState.selectedProject.name}</h1>
                    <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${
                      appState.selectedProject.status === 'Active' ? 'bg-[#22C55E]/10 text-[#22C55E]' :
                      appState.selectedProject.status === 'Archived' ? 'bg-[#8C8C8C]/10 text-[#8C8C8C]' :
                      'bg-[#F97066]/10 text-[#F97066]'
                    }`}>
                      {appState.selectedProject.status}
                    </span>
                  </div>
                  <p className="mt-2 text-sm text-[#B8B8B8] max-w-2xl line-clamp-2">
                    {appState.selectedProject.description}
                  </p>
                  <div className="flex items-center gap-4 mt-2">
                    <span className="text-xs text-[#8C8C8C]">{projectFolders.length} folders</span>
                    <span className="text-xs text-[#8C8C8C]">Created {appState.selectedProject.createdAt}</span>
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2 mt-4 flex-wrap">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowProjectInfo(true)}
                  className="border-[#2E2E2E] text-[#B8B8B8] hover:bg-[#1E1E1E] hover:text-white"
                >
                  <Info className="w-4 h-4 mr-1.5" />
                  Info
                </Button>
                {(isAdmin || isAnalyst) && (
                  <Button
                    size="sm"
                    onClick={() => { resetFolderForm(); setShowCreateFolder(true); }}
                    className="bg-[#c16e43] text-[#0A0A0A] hover:bg-[#d08a5e]"
                  >
                    <Plus className="w-4 h-4 mr-1" />
                    Create Folder
                  </Button>
                )}
                {isAdmin && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setProjectForm({
                        name: appState.selectedProject!.name,
                        description: appState.selectedProject!.description,
                        status: appState.selectedProject!.status
                      });
                      setEditingProjectId(appState.selectedProject!.id);
                      setShowCreateProject(true);
                    }}
                    className="border-[#2E2E2E] text-[#B8B8B8] hover:bg-[#1E1E1E] hover:text-white"
                  >
                    <Pencil className="w-4 h-4 mr-1.5" />
                    Edit
                  </Button>
                )}
                {isAdmin && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setShowDeleteProject(true)}
                    className="border-[#F97066]/30 text-[#F97066] hover:bg-[#F97066]/10"
                  >
                    <Trash2 className="w-4 h-4 mr-1.5" />
                    Delete
                  </Button>
                )}
                <div className="ml-auto flex items-center gap-1 bg-[#151515] rounded-lg p-1 border border-[#2E2E2E]">
                  <button
                    onClick={() => setViewMode('grid')}
                    className={`p-1.5 rounded ${viewMode === 'grid' ? 'bg-[#1E1E1E] text-white' : 'text-[#8C8C8C] hover:text-white'}`}
                  >
                    <Grid3X3 className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => setViewMode('list')}
                    className={`p-1.5 rounded ${viewMode === 'list' ? 'bg-[#1E1E1E] text-white' : 'text-[#8C8C8C] hover:text-white'}`}
                  >
                    <List className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>

            {/* Folders */}
            {projectFolders.length === 0 ? (
              <EmptyState
                icon="folder"
                title="No folders yet"
                description="This project doesn't have any folders."
                action={(isAdmin || isAnalyst) ? {
                  label: 'Create Folder',
                  onClick: () => { resetFolderForm(); setShowCreateFolder(true); }
                } : undefined}
              />
            ) : viewMode === 'grid' ? (
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
                {projectFolders.map(folder => (
                  <FolderCard
                    key={folder.id}
                    folder={folder}
                    canUpload={canUpload}
                    onOpenWorkspace={openWorkspace}
                    onInfo={() => setShowFolderInfoId(folder.id)}
                  />
                ))}
              </div>
            ) : (
              <div className="bg-[#151515] rounded-xl border border-[#2E2E2E] overflow-x-auto">
                <table className="w-full min-w-[640px]">
                  <thead>
                    <tr className="border-b border-[#2E2E2E]">
                      <th className="text-left px-4 py-3 text-xs font-medium text-[#B8B8B8] uppercase tracking-wider">Name</th>
                      <th className="text-left px-4 py-3 text-xs font-medium text-[#B8B8B8] uppercase tracking-wider hidden md:table-cell">Description</th>
                      <th className="text-left px-4 py-3 text-xs font-medium text-[#B8B8B8] uppercase tracking-wider hidden lg:table-cell">Created By</th>
                      <th className="text-left px-4 py-3 text-xs font-medium text-[#B8B8B8] uppercase tracking-wider">Status</th>
                      <th className="text-right px-4 py-3 text-xs font-medium text-[#B8B8B8] uppercase tracking-wider">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {projectFolders.map(folder => (
                      <FolderRow
                        key={folder.id}
                        folder={folder}
                        canUpload={canUpload}
                        onOpenWorkspace={openWorkspace}
                        onInfo={() => setShowFolderInfoId(folder.id)}
                        onDelete={() => setShowDeleteFolder(folder.id)}
                        canDelete={isAdmin || isAnalyst}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Create Project Modal */}
      <Dialog open={showCreateProject} onOpenChange={(open) => { setShowCreateProject(open); if (!open) resetProjectForm(); }}>
        <DialogContent className="bg-[#151515] border-[#2E2E2E] max-w-md">
          <DialogHeader><DialogTitle className="text-lg font-semibold text-white">{editingProjectId ? 'Edit Project' : 'Create Project'}</DialogTitle></DialogHeader>
          <div className="space-y-4 mt-2">
            <div>
              <label className="text-xs text-[#B8B8B8] uppercase">Project Name *</label>
              <Input value={projectForm.name} onChange={(e) => setProjectForm(p => ({ ...p, name: e.target.value }))} placeholder="Enter project name" className="mt-1 bg-[#000000] border-[#2E2E2E] text-white" />
            </div>
            <div>
              <label className="text-xs text-[#B8B8B8] uppercase">Description</label>
              <textarea value={projectForm.description} onChange={(e) => setProjectForm(p => ({ ...p, description: e.target.value }))} placeholder="Enter description" className="mt-1 w-full h-20 bg-[#000000] border border-[#2E2E2E] rounded-lg p-3 text-white text-sm placeholder:text-[#8C8C8C] resize-none focus:border-[#c16e43] focus:outline-none" />
            </div>
            <div>
              <label className="text-xs text-[#B8B8B8] uppercase">Status</label>
              <select value={projectForm.status} onChange={(e) => setProjectForm(p => ({ ...p, status: e.target.value }))} className="mt-1 w-full h-10 bg-[#000000] border border-[#2E2E2E] rounded-lg px-3 text-white text-sm">
                <option>Active</option>
                <option>Archived</option>
                <option>Published</option>
                <option>Deleted</option>
              </select>
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <Button variant="outline" onClick={() => { setShowCreateProject(false); resetProjectForm(); }} className="border-[#2E2E2E] text-[#B8B8B8] hover:bg-[#1E1E1E]">Cancel</Button>
              <Button onClick={handleCreateProject} disabled={!projectForm.name.trim() || isSubmitting} className="bg-[#c16e43] text-[#0A0A0A] hover:bg-[#d08a5e]">
                {isSubmitting ? (editingProjectId ? 'Saving...' : 'Creating...') : (editingProjectId ? 'Save Changes' : 'Create Project')}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Create Folder Modal */}
      <Dialog open={showCreateFolder} onOpenChange={setShowCreateFolder}>
        <DialogContent className="bg-[#151515] border-[#2E2E2E] max-w-md">
          <DialogHeader><DialogTitle className="text-lg font-semibold text-white">Create Folder</DialogTitle></DialogHeader>
          <div className="space-y-4 mt-2">
            <div>
              <label className="text-xs text-[#B8B8B8] uppercase">Folder Name *</label>
              <Input value={folderForm.name} onChange={(e) => setFolderForm(p => ({ ...p, name: e.target.value }))} placeholder="Enter folder name" className="mt-1 bg-[#000000] border-[#2E2E2E] text-white" />
            </div>
            <div>
              <label className="text-xs text-[#B8B8B8] uppercase">Description</label>
              <textarea value={folderForm.description} onChange={(e) => setFolderForm(p => ({ ...p, description: e.target.value }))} placeholder="Enter description" className="mt-1 w-full h-20 bg-[#000000] border border-[#2E2E2E] rounded-lg p-3 text-white text-sm placeholder:text-[#8C8C8C] resize-none focus:border-[#c16e43] focus:outline-none" />
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <Button variant="outline" onClick={() => setShowCreateFolder(false)} className="border-[#2E2E2E] text-[#B8B8B8] hover:bg-[#1E1E1E]">Cancel</Button>
              <Button onClick={handleCreateFolder} disabled={!folderForm.name.trim() || isSubmitting} className="bg-[#c16e43] text-[#0A0A0A] hover:bg-[#d08a5e]">
                {isSubmitting ? 'Creating...' : 'Create Folder'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Project Info Modal */}
      <Dialog open={showProjectInfo} onOpenChange={setShowProjectInfo}>
        <DialogContent className="bg-[#151515] border-[#2E2E2E] max-w-md">
          <DialogHeader><DialogTitle className="text-lg font-semibold text-white">Project Info</DialogTitle></DialogHeader>
          {appState.selectedProject && (
            <div className="space-y-3 mt-2 text-sm">
              <p className="text-white font-medium">{appState.selectedProject.name}</p>
              <p className="text-[#B8B8B8]">{appState.selectedProject.description}</p>
              <div className="flex gap-4 text-xs text-[#8C8C8C]">
                <span>Status: {appState.selectedProject.status}</span>
                <span>Created: {appState.selectedProject.createdAt}</span>
                <span>By: {appState.selectedProject.createdBy}</span>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Folder Info Modal */}
      <Dialog open={!!showFolderInfoId} onOpenChange={() => setShowFolderInfoId(null)}>
        <DialogContent className="bg-[#151515] border-[#2E2E2E] max-w-md">
          <DialogHeader><DialogTitle className="text-lg font-semibold text-white">Folder Info</DialogTitle></DialogHeader>
          {infoFolder && (
            <div className="space-y-3 mt-2 text-sm">
              <p className="text-white font-medium">{infoFolder.name}</p>
              <p className="text-[#B8B8B8]">{infoFolder.description}</p>
              <div className="flex gap-4 text-xs text-[#8C8C8C]">
                <span>Status: {infoFolder.status}</span>
                <span>Created: {infoFolder.createdAt}</span>
                <span>By: {infoFolder.createdBy}</span>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <ConfirmDialog open={showDeleteProject} onOpenChange={setShowDeleteProject} title="Delete Project?" description={`This will permanently delete "${appState.selectedProject?.name}" and all its folders. This action cannot be undone.`} onConfirm={handleDeleteProject} isLoading={isSubmitting} />
      <ConfirmDialog open={!!showDeleteFolder} onOpenChange={() => setShowDeleteFolder(null)} title="Delete Folder?" description={`This will permanently delete this folder. This action cannot be undone.`} onConfirm={() => showDeleteFolder && handleDeleteFolder(showDeleteFolder)} isLoading={isSubmitting} />
    </div>
  );
}

function FolderCard({ folder, canUpload, onOpenWorkspace, onInfo }: {
  folder: Folder;
  canUpload: boolean;
  onOpenWorkspace: (folderId: string, mode: WorkspaceMode) => void;
  onInfo: () => void;
}) {
  const pipeline = useFolderPipeline(folder, canUpload);

  return (
    <div
      className="group flex h-full min-h-[216px] flex-col rounded-xl border border-[#2E2E2E] bg-[#151515]/95 p-5 shadow-[0_14px_40px_rgba(0,0,0,0.16)] transition-all hover:-translate-y-0.5 hover:border-[#525252] hover:shadow-[0_20px_55px_rgba(0,0,0,0.25)]"
    >
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-10 h-10 rounded-lg bg-[#c16e43]/10 flex items-center justify-center flex-shrink-0">
            <FolderOpen className="w-5 h-5 text-[#E4E4E7]" />
          </div>
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-white truncate">{folder.name}</h3>
            <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
              folder.status === 'Active' ? 'bg-[#22C55E]/10 text-[#22C55E]' :
              folder.status === 'Archived' ? 'bg-[#8C8C8C]/10 text-[#8C8C8C]' :
              'bg-[#F97066]/10 text-[#F97066]'
            }`}>{folder.status}</span>
          </div>
        </div>
        <button onClick={onInfo} className="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg text-[#8C8C8C] hover:text-white hover:bg-[#1E1E1E] transition-all">
          <MoreHorizontal className="w-4 h-4" />
        </button>
      </div>

      <p className="mt-3 flex-1 text-sm leading-6 text-[#B8B8B8] line-clamp-3">{folder.description || 'No description provided.'}</p>
      <div className="mt-3 text-xs text-[#8C8C8C]">Created by {folder.createdBy} on {folder.createdAt}</div>

      <div className="mt-4 flex items-center justify-between border-t border-[#2E2E2E] pt-4">
        <WorkflowActions folder={folder} pipeline={pipeline} onOpen={onOpenWorkspace} />
      </div>
    </div>
  );
}

function FolderRow({ folder, canUpload, onOpenWorkspace, onInfo, onDelete, canDelete }: {
  folder: Folder;
  canUpload: boolean;
  onOpenWorkspace: (folderId: string, mode: WorkspaceMode) => void;
  onInfo: () => void;
  onDelete: () => void;
  canDelete: boolean;
}) {
  const pipeline = useFolderPipeline(folder, canUpload);

  return (
    <tr className="border-b border-[#2E2E2E] last:border-0 hover:bg-[#1E1E1E] transition-colors">
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          <FolderOpen className="w-4 h-4 text-[#E4E4E7]" />
          <span className="text-sm font-medium text-white">{folder.name}</span>
        </div>
      </td>
      <td className="px-4 py-3 text-sm text-[#B8B8B8] hidden md:table-cell max-w-[200px] truncate">{folder.description}</td>
      <td className="px-4 py-3 text-sm text-[#B8B8B8] hidden lg:table-cell">{folder.createdBy}</td>
      <td className="px-4 py-3">
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
          folder.status === 'Active' ? 'bg-[#22C55E]/10 text-[#22C55E]' :
          folder.status === 'Archived' ? 'bg-[#8C8C8C]/10 text-[#8C8C8C]' :
          'bg-[#F97066]/10 text-[#F97066]'
        }`}>
          {folder.status}
        </span>
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center justify-end gap-1">
          <WorkflowActions folder={folder} pipeline={pipeline} onOpen={onOpenWorkspace} size="sm" />
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button size="sm" variant="ghost" className="h-7 px-2 text-[#B8B8B8] hover:text-white">
                <MoreHorizontal className="w-3.5 h-3.5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent className="bg-[#151515] border-[#2E2E2E]">
              <DropdownMenuItem onClick={onInfo} className="text-[#B8B8B8] focus:text-white focus:bg-[#1E1E1E]">
                <Info className="w-4 h-4 mr-2" /> Info
              </DropdownMenuItem>
              {canDelete && (
                <DropdownMenuItem onClick={onDelete} className="text-[#F97066] focus:text-[#F97066] focus:bg-[#F97066]/10">
                  <Trash2 className="w-4 h-4 mr-2" /> Delete
                </DropdownMenuItem>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </td>
    </tr>
  );
}


