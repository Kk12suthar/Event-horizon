import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { PanelRight } from 'lucide-react';
import { useAppState } from '@/hooks/useAppState';
import { useAuth } from '@/hooks/useAuth';
import { usePipelineStage } from '@/hooks/usePipelineStage';
import { useAgentChat } from '@/hooks/useAgentChat';
import { useFolderUpload } from '@/hooks/useFolderUpload';
import type { ArtifactState, ReportFormat, WorkspaceMode } from '@/types';
import { AGENT_URL, downloadBlob } from '@/lib/api';
import { SPACE } from './theme';
import { WorkspaceTopbar } from './WorkspaceTopbar';
import { ModeSwitcher } from './ModeSwitcher';
import { ChatThread } from './ChatThread';
import { Composer } from './Composer';
import { EmptyState } from './EmptyState';
import { ArtifactPanel } from './ArtifactPanel';

/**
 * WorkspaceView â€” thin orchestrator + responsive shell for the unified
 * Workspace. It wires the pipeline/chat/upload hooks to the ModeSwitcher,
 * ChatThread, Composer, and ArtifactPanel, and lays them out responsively.
 *
 * Responsive layout (Requirement 10, design "Screen Anatomy & Responsive
 * Layout"). The slim 56px navigation rail is provided by the surrounding
 * AppShell (`hidden lg:block`), so this view owns the center column + the
 * right artifact panel:
 *
 *   Desktop (â‰¥1024px / `lg`): the artifact panel is in-flow on the right
 *     (its own `lg:static` styling) beside the centered chat column â€” together
 *     with the AppShell rail this is the three-zone layout (R10.1).
 *
 *   Tablet (640â€“1023px): the rail is hidden by AppShell and the artifact panel
 *     becomes an overlay drawer (R10.2/R10.3); the chat column takes the full
 *     width when the panel is closed.
 *
 *   Mobile (<640px): single chat-first column (R10.6); the mode switcher
 *     becomes a horizontally scrolling row of pills (R10.4); the artifact
 *     panel is a full-screen overlay (its own `w-full` below `sm`) opened from
 *     the composer's artifact button or the topbar toggle (R10.4); the
 *     composer stays pinned at the bottom.
 *
 * No horizontal overflow at any width (`overflow-hidden` on the row,
 * `min-w-0` on the flex children, `overflow-x-auto` on the mode row); wide
 * tables/charts scroll inside the artifact panel's own scroll container
 * (R10.5).
 */

const VALID_MODES: WorkspaceMode[] = ['sources', 'prepare', 'visualize', 'publish'];
const SWITCHABLE_MODES: WorkspaceMode[] = ['prepare', 'visualize', 'publish'];

/** Rows fetched per page in the interactive table browser (initial threshold). */
const TABLE_PAGE_SIZE = 20;

function isWorkspaceMode(value: string | null): value is WorkspaceMode {
  return value !== null && VALID_MODES.includes(value as WorkspaceMode);
}

/** Reactively track a CSS media query (used to default the panel open state). */
function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState<boolean>(() =>
    typeof window !== 'undefined' ? window.matchMedia(query).matches : false,
  );

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const media = window.matchMedia(query);
    const handler = () => setMatches(media.matches);
    handler();
    media.addEventListener('change', handler);
    return () => media.removeEventListener('change', handler);
  }, [query]);

  return matches;
}

export function WorkspaceView() {
  const appState = useAppState();
  const { user } = useAuth();
  const {
    projectList,
    folderList,
    selectedProject,
    selectedFolder,
    activeSession,
    fileList,
    tables,
    charts,
    reports,
    selectedTable,
    selectedTableId,
  } = appState;

  const [searchParams, setSearchParams] = useSearchParams();

  // Three-zone layout only at `lg`+; default the artifact panel open there and
  // closed below (chat-first, R10.6).
  const isDesktop = useMediaQuery('(min-width: 1024px)');
  const [panelOpen, setPanelOpen] = useState<boolean>(() =>
    typeof window !== 'undefined'
      ? window.matchMedia('(min-width: 1024px)').matches
      : false,
  );

  // Active mode requested by the user, seeded from the URL (`?mode=`). The
  // *effective* mode is derived below so gating can never leave us on a locked
  // mode without mutating state inside an effect.
  const [requestedMode, setMode] = useState<WorkspaceMode>(() => {
    const param = searchParams.get('mode');
    return isWorkspaceMode(param) ? param : 'prepare';
  });

  const pipeline = usePipelineStage(tables);

  // Effective mode: honor the requested mode when its gate is open, otherwise
  // fall back to the first enabled mode (Sources is always enabled). Derived
  // during render â€” no setState-in-effect needed (Requirement 3.6).
  const normalizedRequestedMode: WorkspaceMode = requestedMode === 'sources' ? 'prepare' : requestedMode;
  const mode: WorkspaceMode = pipeline.enabledModes[normalizedRequestedMode]
    ? normalizedRequestedMode
    : SWITCHABLE_MODES.find((m) => pipeline.enabledModes[m]) ?? 'prepare';

  // Resolve folder from `?folderId=` if it differs from the loaded context.
  useEffect(() => {
    const folderId = searchParams.get('folderId');
    if (folderId && selectedFolder?.id !== folderId) {
      void appState.loadFolderContext(folderId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appState.loadFolderContext, searchParams, selectedFolder?.id]);

  // Mirror the effective mode into the URL without clobbering other params.
  useEffect(() => {
    const current = searchParams.get('mode');
    if (current !== mode) {
      const next = new URLSearchParams(searchParams);
      next.set('mode', mode);
      setSearchParams(next, { replace: true });
    }
  }, [mode, searchParams, setSearchParams]);

  const chat = useAgentChat({
    folder: selectedFolder,
    session: activeSession,
    user,
    selectedTable,
    mode,
    ensureSession: appState.ensureSession,
    onCompletion: () => {
      if (selectedFolder) void appState.loadTablesForFolder(selectedFolder);
      void appState.refreshWorkspace();
    },
  });

  const upload = useFolderUpload({
    folder: selectedFolder,
    user,
    ensureSession: appState.ensureSession,
    updateFolder: appState.updateFolder,
    loadTablesForFolder: appState.loadTablesForFolder,
    addFiles: appState.addFiles,
    onTablesCreated: (folder) => {
      void appState.loadTablesForFolder(folder);
    },
  });

  const artifact: ArtifactState = useMemo(
    () => ({ tables, charts, reports }),
    [tables, charts, reports],
  );

  const handleSend = useCallback(
    (query: string) => {
      void chat.send(query, mode);
    },
    [chat, mode],
  );

  // Load one page (20 rows) of a table's data for the interactive table
  // browser. loadTablePreview caches rows into global state and appends when
  // page > 1, so re-opening a table reuses cached rows with no refetch.
  const handleLoadTablePage = useCallback(
    (tableId: string, page: number) => appState.loadTablePreview(tableId, page, TABLE_PAGE_SIZE),
    [appState],
  );

  const handleDownloadReport = useCallback((format: ReportFormat) => {
    const report = reports[reports.length - 1];
    if (!report) return;
    const path = report.downloadUrls?.[format] || (report.format === format ? report.downloadUrl : undefined);
    if (!path) return;
    const url = /^https?:\/\//i.test(path) ? path : `${AGENT_URL}${path.startsWith('/') ? path : `/${path}`}`;
    const safeName = report.name.replace(/[^a-z0-9_-]+/gi, '-').replace(/^-|-$/g, '') || 'eventhorizon-report';
    void downloadBlob(url, `${safeName}.${format.toLowerCase()}`);
  }, [reports]);
  const handleSelectFolder = useCallback(
    (folderId: string) => {
      void appState.loadFolderContext(folderId);
    },
    [appState],
  );

  const handleCreateProject = useCallback(
    (name: string, description: string) => appState.createProject(name, description, 'Active'),
    [appState],
  );

  const handleCreateFolder = useCallback(
    (projectId: string, name: string, description: string) =>
      appState.createFolder(name, description, projectId),
    [appState],
  );

  const hasFolder = Boolean(selectedFolder);

  return (
    <div
      className="relative flex h-full min-h-0 w-full overflow-hidden"
      style={{ backgroundColor: SPACE.bg }}
    >
      {/* Center column: topbar + mode switcher + chat/empty-state + composer. */}
      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <WorkspaceTopbar
          projects={projectList}
          folders={folderList}
          selectedProject={selectedProject}
          selectedFolder={selectedFolder}
          activeSession={activeSession}
          artifactOpen={panelOpen}
          onToggleArtifact={() => setPanelOpen((open) => !open)}
          onSelectFolder={handleSelectFolder}
          onCreateProject={handleCreateProject}
          onCreateFolder={handleCreateFolder}
        />

        {/* Mode switcher row â€” horizontally scrollable pills on small screens
            (R10.4) with no horizontal overflow of the layout (R10.5). */}
        <div
          className="flex-shrink-0 overflow-x-auto px-3 py-2"
          style={{ borderBottom: `1px solid ${SPACE.border}` }}
        >
          <div className="flex w-max items-center">
            <ModeSwitcher mode={mode} pipeline={pipeline} onModeChange={setMode} />
          </div>
        </div>

        {/* Primary surface: the chat thread, or onboarding when no folder. */}
        {hasFolder ? (
          <ChatThread
            messages={chat.messages}
            isGenerating={chat.isGenerating}
            savedCharts={charts}
            onSaveChart={appState.saveChart}
          />
        ) : (
          <div className="flex flex-1 overflow-y-auto">
            <EmptyState onExampleSelect={handleSend} />
          </div>
        )}

        {/* Mobile-only artifact button near the composer (R10.4). On `lg`+ the
            panel is in-flow so the button is hidden. */}
        {hasFolder && (
          <div className="flex flex-shrink-0 justify-end px-4 lg:hidden">
            <button
              type="button"
              onClick={() => setPanelOpen(true)}
              aria-label="Open artifact panel"
              className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors"
              style={{
                borderColor: SPACE.border,
                color: SPACE.muted,
                backgroundColor: SPACE.panel,
              }}
            >
              <PanelRight className="h-3.5 w-3.5" strokeWidth={2} />
              View artifact
            </button>
          </div>
        )}

        <Composer
          mode={mode}
          disabled={!hasFolder}
          isGenerating={chat.isGenerating}
          folderName={selectedFolder?.name}
          onSend={handleSend}
          onStop={chat.stop}
          onUpload={upload.upload}
        />
      </main>

      {/* Right artifact panel: in-flow at `lg`+, overlay drawer below (the
          ArtifactPanel owns its own responsive positioning). */}
      <ArtifactPanel
        mode={mode}
        open={panelOpen && hasFolder}
        onClose={() => setPanelOpen(false)}
        artifact={artifact}
        hasFolder={hasFolder}
        files={fileList}
        session={activeSession}
        uploadProgress={upload.progress}
        uploadStage={upload.stage}
        uploadError={upload.error}
        onUpload={upload.upload}
        onDeleteFile={appState.removeFile}
        pipeline={pipeline}
        isGenerating={chat.isGenerating}
        onLoadTablePage={handleLoadTablePage}
        selectedTableId={selectedTableId}
        onSelectPreparedTable={appState.selectPreparedTable}
        onAddChart={() => {
          void chat.send('Analyze the selected prepared table and create one useful chart or KPI preview.', 'visualize');
        }}
        onDeleteChart={appState.removeChart}
        onDownloadReport={handleDownloadReport}
      />

      {/* When the panel is closed on desktop, a slim affordance keeps it
          reachable without consuming layout width below `lg`. */}
      {hasFolder && !panelOpen && isDesktop && (
        <button
          type="button"
          onClick={() => setPanelOpen(true)}
          aria-label="Show artifact panel"
          title="Show artifact panel"
          className="hidden h-full w-10 flex-shrink-0 items-center justify-center lg:flex"
          style={{
            backgroundColor: SPACE.panelAlt,
            borderLeft: `1px solid ${SPACE.border}`,
            color: SPACE.muted,
          }}
        >
          <PanelRight className="h-[18px] w-[18px]" strokeWidth={2} />
        </button>
      )}
    </div>
  );
}

export default WorkspaceView;


