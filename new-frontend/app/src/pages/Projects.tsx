import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowUpRight,
  BarChart3,
  ChevronRight,
  Database,
  FileSpreadsheet,
  FileText,
  FolderOpen,
  Info,
  Layers3,
  Lock,
  Pencil,
  Plus,
  Search,
  Table2,
  Trash2,
  Upload,
  Wand2,
  type LucideIcon,
} from 'lucide-react';
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type CoordinateExtent,
  type Edge,
  type Node,
  type NodeProps,
  type ReactFlowInstance,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { EmptyState } from '@/components/EmptyState';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { InlineFolderUpload } from '@/components/data/InlineFolderUpload';
import { usePipelineStage } from '@/hooks/usePipelineStage';
import { useFolderUpload } from '@/hooks/useFolderUpload';
import { useAppState } from '@/hooks/useAppState';
import { useAuth } from '@/hooks/useAuth';
import { fetchAllFolderTables } from '@/lib/api';
import type { DataTable, Folder, PipelineState, Project, WorkspaceMode } from '@/types';

const WORKFLOW_MODES: { id: WorkspaceMode; label: string; icon: LucideIcon }[] = [
  { id: 'prepare', label: 'Prepare', icon: Wand2 },
  { id: 'visualize', label: 'Visualize', icon: BarChart3 },
  { id: 'publish', label: 'Publish', icon: FileText },
];

const LOCKED_REASON: Record<WorkspaceMode, string> = {
  sources: 'You need upload permission to add sources.',
  prepare: 'Prepare is always available.',
  visualize: 'Create a transformed table in Prepare first.',
  publish: 'Create a transformed table in Prepare first.',
};

function statusClass(status: string) {
  if (status === 'Active') return 'bg-[#22C55E]/10 text-[#5FD38A]';
  if (status === 'Archived') return 'bg-[#8C8C8C]/10 text-[#A3A3A3]';
  return 'bg-[#F97066]/10 text-[#F97066]';
}

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
    // Cached entities keep the page usable while the table endpoint recovers.
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

function useFolderWorkspaceData(folder: Folder, canUpload: boolean): {
  tables: DataTable[];
  pipeline: PipelineState;
} {
  const [tables, setTables] = useState<DataTable[]>(() => folderEntitiesToTables(folder));

  useEffect(() => {
    let cancelled = false;
    setTables(folderEntitiesToTables(folder));
    void (async () => {
      const next = await loadFolderTablesLocal(folder);
      if (!cancelled) setTables(next);
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [folder.id, folder.entities?.tables]);

  const pipeline = usePipelineStage(tables);
  const gatedPipeline = useMemo(
    () => ({
      ...pipeline,
      enabledModes: { ...pipeline.enabledModes, prepare: canUpload && pipeline.enabledModes.prepare },
    }),
    [pipeline, canUpload],
  );

  return { tables, pipeline: gatedPipeline };
}

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
        return (
          <div key={id} className="group relative flex">
            <button
              type="button"
              disabled={!enabled}
              onClick={() => enabled && onOpen(folder.id, id)}
              aria-label={enabled ? `Open ${folder.name} in ${label}` : LOCKED_REASON[id]}
              title={enabled ? label : LOCKED_REASON[id]}
              className={`relative flex ${box} items-center justify-center rounded-md transition-colors ${
                enabled ? 'text-[#E7E7E7] hover:bg-[#252525]' : 'cursor-not-allowed text-[#717171] opacity-40'
              }`}
            >
              <Icon className={glyph} strokeWidth={2} />
              {!enabled && <Lock className="absolute -right-0.5 -top-0.5 h-2.5 w-2.5" strokeWidth={2.5} />}
              {enabled && completed[id] && (
                <span className="absolute -right-0.5 -top-0.5 h-1.5 w-1.5 rounded-full bg-[#5FD38A]" />
              )}
            </button>
            {!enabled && (
              <span
                role="tooltip"
                className="pointer-events-none absolute left-1/2 top-full z-50 mt-1.5 -translate-x-1/2 whitespace-nowrap rounded-md border border-[#333] bg-[#171717] px-2 py-1 text-xs font-medium text-[#E7E7E7] opacity-0 shadow-md transition-opacity group-hover:opacity-100"
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

type CanvasNodeKind = 'project' | 'folder' | 'source' | 'prepared' | 'visualize' | 'publish';

type HierarchyNodeData = {
  kind: CanvasNodeKind;
  eyebrow: string;
  label: string;
  meta: string;
  active?: boolean;
  locked?: boolean;
  folderId?: string;
  actionMode?: WorkspaceMode;
};

type HierarchyNode = Node<HierarchyNodeData, 'hierarchy'>;

const NODE_ICONS: Record<CanvasNodeKind, LucideIcon> = {
  project: Layers3,
  folder: FolderOpen,
  source: Database,
  prepared: Table2,
  visualize: BarChart3,
  publish: FileText,
};

function HierarchyNodeView({ data, selected }: NodeProps<HierarchyNode>) {
  const Icon = NODE_ICONS[data.kind];
  const interactive = Boolean(data.folderId || data.actionMode);

  return (
    <div
      className={`group relative w-full rounded-lg border bg-[#0D0D0D] px-3.5 py-3 shadow-[0_10px_30px_rgba(0,0,0,0.28)] transition-all ${
        data.active || selected
          ? 'border-[#C16E43] shadow-[0_0_0_1px_rgba(193,110,67,0.22),0_14px_36px_rgba(0,0,0,0.34)]'
          : data.locked
            ? 'border-[#292929] opacity-55'
            : 'border-[#343434] hover:border-[#555]'
      } ${interactive && (!data.locked || data.actionMode === 'prepare') ? 'cursor-pointer' : ''}`}
    >
      {data.kind !== 'project' && (
        <Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-2 !border-[#0A0A0A] !bg-[#777]" />
      )}
      <div className="flex items-start gap-3">
        <div
          className={`flex h-9 w-9 flex-none items-center justify-center rounded-md border ${
            data.active
              ? 'border-[#C16E43]/50 bg-[#C16E43]/12 text-[#D88A5F]'
              : 'border-[#303030] bg-[#1C1C1C] text-[#BDBDBD]'
          }`}
        >
          <Icon className="h-4 w-4" strokeWidth={1.8} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[10px] font-semibold uppercase text-[#777]">{data.eyebrow}</span>
            {data.locked ? (
              <Lock className="h-3 w-3 flex-none text-[#777]" />
            ) : interactive ? (
              <ArrowUpRight className="h-3 w-3 flex-none text-[#666] transition-colors group-hover:text-[#D88A5F]" />
            ) : null}
          </div>
          <p className="mt-1 truncate text-sm font-semibold text-[#F2F2F2]">{data.label}</p>
          <p className="mt-1 truncate text-[11px] text-[#8D8D8D]">{data.meta}</p>
        </div>
      </div>
      {data.kind !== 'visualize' && data.kind !== 'publish' && (
        <Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-2 !border-[#0A0A0A] !bg-[#C16E43]" />
      )}
    </div>
  );
}

const NODE_TYPES = { hierarchy: HierarchyNodeView };

function ProjectCanvas({
  project,
  folders,
  selectedFolder,
  canUpload,
  canDelete,
  onSelectFolder,
  onOpenWorkspace,
  upload,
  uploadPanelOpen,
  onRequestUpload,
  onCloseUpload,
  onInfo,
  onDelete,
}: {
  project: Project;
  folders: Folder[];
  selectedFolder: Folder;
  canUpload: boolean;
  canDelete: boolean;
  onSelectFolder: (folder: Folder) => void;
  onOpenWorkspace: (folderId: string, mode: WorkspaceMode) => void;
  upload: ReturnType<typeof useFolderUpload>;
  uploadPanelOpen: boolean;
  onRequestUpload: () => void;
  onCloseUpload: () => void;
  onInfo: () => void;
  onDelete: () => void;
}) {
  const { tables, pipeline } = useFolderWorkspaceData(selectedFolder, canUpload);
  const uploadedTables = tables.filter((table) => table.source === 'uploaded');
  const preparedTables = tables.filter((table) => table.source === 'agent_created');
  const canvasRef = useRef<HTMLDivElement>(null);
  const [flowInstance, setFlowInstance] = useState<ReactFlowInstance<HierarchyNode, Edge> | null>(null);

  const { nodes, edges } = useMemo(() => {
    const folderGap = 142;
    const selectedIndex = Math.max(0, folders.findIndex((folder) => folder.id === selectedFolder.id));
    const selectedY = selectedIndex * folderGap;
    const sourceCount = Math.max(uploadedTables.length, 1);
    const sourceStartY = selectedY - ((sourceCount - 1) * 104) / 2;
    const projectY = Math.max(0, ((Math.max(folders.length, 1) - 1) * folderGap) / 2);
    const nextNodes: HierarchyNode[] = [
      {
        id: `project-${project.id}`,
        type: 'hierarchy',
        position: { x: 0, y: projectY },
        style: { width: 226 },
        data: {
          kind: 'project',
          eyebrow: 'Project',
          label: project.name,
          meta: `${folders.length} ${folders.length === 1 ? 'folder' : 'folders'}`,
        },
      },
    ];
    const nextEdges: Edge[] = [];

    const edge = (id: string, source: string, target: string, active = false): Edge => ({
      id,
      source,
      target,
      type: 'smoothstep',
      animated: active,
      markerEnd: { type: MarkerType.ArrowClosed, color: active ? '#C16E43' : '#4A4A4A' },
      style: { stroke: active ? '#C16E43' : '#3A3A3A', strokeWidth: active ? 1.8 : 1.2 },
    });

    folders.forEach((folder, index) => {
      const isActive = folder.id === selectedFolder.id;
      nextNodes.push({
        id: `folder-${folder.id}`,
        type: 'hierarchy',
        position: { x: 330, y: index * folderGap },
        style: { width: 232 },
        data: {
          kind: 'folder',
          eyebrow: 'Folder',
          label: folder.name,
          meta: isActive
            ? `${uploadedTables.length} sources · ${preparedTables.length} prepared`
            : `${Object.keys(folder.entities?.tables || {}).length} cached sources`,
          active: isActive,
          folderId: folder.id,
        },
      });
      nextEdges.push(edge(`project-${folder.id}`, `project-${project.id}`, `folder-${folder.id}`, isActive));
    });

    if (uploadedTables.length) {
      uploadedTables.forEach((table, index) => {
        nextNodes.push({
          id: `source-${table.id}`,
          type: 'hierarchy',
          position: { x: 650, y: sourceStartY + index * 104 },
          style: { width: 220 },
          data: {
            kind: 'source',
            eyebrow: 'Source table',
            label: table.name,
            meta: table.rowCount ? `${table.rowCount.toLocaleString()} rows` : 'Uploaded data',
            actionMode: 'prepare',
          },
        });
        nextEdges.push(edge(`folder-source-${table.id}`, `folder-${selectedFolder.id}`, `source-${table.id}`, true));
      });
    } else {
      nextNodes.push({
        id: 'source-empty',
        type: 'hierarchy',
        position: { x: 650, y: sourceStartY },
        style: { width: 220 },
        data: {
          kind: 'source',
          eyebrow: 'Source',
          label: canUpload ? 'Upload first source' : 'No source available',
          meta: canUpload ? 'Add files beside the canvas' : 'Upload access required',
          locked: !canUpload,
          actionMode: canUpload ? 'sources' : undefined,
        },
      });
      nextEdges.push(edge('folder-source-empty', `folder-${selectedFolder.id}`, 'source-empty'));
    }

    const preparedId = 'prepared-stage';
    nextNodes.push({
      id: preparedId,
      type: 'hierarchy',
      position: { x: 970, y: selectedY },
      style: { width: 236 },
      data: {
        kind: 'prepared',
        eyebrow: preparedTables.length > 1 ? 'Prepared tables' : 'Prepared table',
        label: preparedTables.length === 1
          ? preparedTables[0].name
          : preparedTables.length > 1
            ? `${preparedTables.length} clean tables`
            : 'Not created yet',
        meta: preparedTables.length ? 'Choose the active table in Prepare' : 'Complete a transformation first',
        locked: !pipeline.hasTransformTable,
        actionMode: 'prepare',
      },
    });
    const sourceIds = uploadedTables.length ? uploadedTables.map((table) => `source-${table.id}`) : ['source-empty'];
    sourceIds.forEach((sourceId, index) => {
      nextEdges.push(edge(`source-prepared-${index}`, sourceId, preparedId, pipeline.hasTransformTable));
    });

    (['visualize', 'publish'] as const).forEach((mode, index) => {
      const enabled = pipeline.enabledModes[mode];
      nextNodes.push({
        id: `mode-${mode}`,
        type: 'hierarchy',
        position: { x: 1300, y: selectedY - 64 + index * 128 },
        style: { width: 205 },
        data: {
          kind: mode,
          eyebrow: 'Workspace mode',
          label: mode === 'visualize' ? 'Visualize' : 'Publish',
          meta: enabled ? 'Ready to open' : 'Waiting for prepared table',
          locked: !enabled,
          actionMode: mode,
        },
      });
      nextEdges.push(edge(`prepared-${mode}`, preparedId, `mode-${mode}`, enabled));
    });

    return { nodes: nextNodes, edges: nextEdges };
  }, [canUpload, folders, pipeline.enabledModes, pipeline.hasTransformTable, preparedTables, project.id, project.name, selectedFolder.id, uploadedTables]);

  const canvasExtent = useMemo<CoordinateExtent>(() => {
    const folderHeight = Math.max(folders.length * 142, 620);
    const sourceHeight = Math.max(uploadedTables.length * 104, 620);
    return [[-160, -320], [1900, Math.max(folderHeight, sourceHeight) + 320]];
  }, [folders.length, uploadedTables.length]);

  useEffect(() => {
    if (!flowInstance) return;
    const frame = window.requestAnimationFrame(() => {
      void flowInstance.fitView({ padding: 0.2, minZoom: 0.42, maxZoom: 1, duration: 280 });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [flowInstance, nodes]);

  useEffect(() => {
    if (!flowInstance || !canvasRef.current) return;
    const observer = new ResizeObserver(() => {
      void flowInstance.fitView({ padding: 0.2, minZoom: 0.42, maxZoom: 1 });
    });
    observer.observe(canvasRef.current);
    return () => observer.disconnect();
  }, [flowInstance]);

  const openFromNode = (node: HierarchyNode) => {
    if (node.data.folderId) {
      const folder = folders.find((item) => item.id === node.data.folderId);
      if (folder) onSelectFolder(folder);
      return;
    }
    if (node.data.actionMode === 'sources' && !node.data.locked) {
      onRequestUpload();
      return;
    }
    if (node.data.actionMode && (!node.data.locked || node.data.actionMode === 'prepare')) {
      onOpenWorkspace(selectedFolder.id, node.data.actionMode);
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col border-t border-[#252525]">
      <div className="grid min-h-[570px] flex-1 grid-cols-1 lg:grid-cols-[minmax(0,1fr)_304px]">
        <div ref={canvasRef} className="relative min-h-[510px] overflow-hidden bg-[#090909]">
          <ReactFlow<HierarchyNode, Edge>
            nodes={nodes}
            edges={edges}
            nodeTypes={NODE_TYPES}
            onInit={setFlowInstance}
            onNodeClick={(_, node) => openFromNode(node)}
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable
            panOnDrag={false}
            panOnScroll={false}
            zoomOnScroll={false}
            zoomOnDoubleClick={false}
            zoomOnPinch
            translateExtent={canvasExtent}
            preventScrolling={false}
            onlyRenderVisibleElements
            fitView
            fitViewOptions={{ padding: 0.2, minZoom: 0.42, maxZoom: 1 }}
            minZoom={0.28}
            maxZoom={1.5}
            colorMode="dark"
            proOptions={{ hideAttribution: true }}
          >
            <Background color="#242424" gap={24} size={1} />
            <Controls
              position="bottom-right"
              showInteractive={false}
              className="!overflow-hidden !rounded-md !border !border-[#333] !bg-[#171717] !shadow-xl [&>button]:!border-[#333] [&>button]:!bg-[#171717] [&>button]:!fill-[#BDBDBD] hover:[&>button]:!bg-[#242424]"
            />
          </ReactFlow>
        </div>

        <aside className="flex min-w-0 flex-col border-t border-[#242424] bg-[#121212] lg:border-l lg:border-t-0">
          <div className="border-b border-[#242424] px-5 py-5">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-[10px] font-semibold uppercase text-[#777]">Selected folder</p>
                <h2 className="mt-1 truncate text-base font-semibold text-white">{selectedFolder.name}</h2>
              </div>
              <button
                type="button"
                onClick={onInfo}
                className="flex h-8 w-8 flex-none items-center justify-center rounded-md text-[#8D8D8D] transition-colors hover:bg-[#242424] hover:text-white"
                title="Folder info"
                aria-label="Folder info"
              >
                <Info className="h-4 w-4" />
              </button>
            </div>
            <p className="mt-3 line-clamp-3 text-xs leading-5 text-[#999]">
              {selectedFolder.description || 'No description provided.'}
            </p>
          </div>

          <div className="border-b border-[#242424] px-4 py-3">
            <InlineFolderUpload
              folderName={selectedFolder.name}
              open={uploadPanelOpen}
              canUpload={canUpload}
              stage={upload.stage}
              progress={upload.progress}
              error={upload.error}
              onUpload={upload.upload}
              onOpen={onRequestUpload}
              onClose={onCloseUpload}
            />
          </div>

          <div className="grid grid-cols-2 border-b border-[#242424]">
            <div className="border-r border-[#242424] px-5 py-4">
              <p className="text-xl font-semibold text-white">{uploadedTables.length}</p>
              <p className="mt-1 text-[11px] text-[#777]">Sources</p>
            </div>
            <div className="px-5 py-4">
              <p className="text-xl font-semibold text-white">{preparedTables.length}</p>
              <p className="mt-1 text-[11px] text-[#777]">Prepared</p>
            </div>
          </div>

          <div className="border-b border-[#242424] px-5 py-4">
            <div className="flex items-center justify-between">
              <p className="text-[10px] font-semibold uppercase text-[#777]">Workflow</p>
              <WorkflowActions folder={selectedFolder} pipeline={pipeline} onOpen={onOpenWorkspace} />
            </div>
            <div className="mt-4 flex items-center gap-2 text-[11px] text-[#8A8A8A]">
              <span className={`h-2 w-2 rounded-full ${pipeline.hasTransformTable ? 'bg-[#5FD38A]' : pipeline.hasUploadedTables ? 'bg-[#C16E43]' : 'bg-[#555]'}`} />
              {pipeline.hasTransformTable ? 'Ready for visualization and publishing' : pipeline.hasUploadedTables ? 'Sources ready for preparation' : 'Empty workspace'}
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
            <p className="text-[10px] font-semibold uppercase text-[#777]">Prepared data</p>
            <div className="mt-3 space-y-2">
              {preparedTables.length ? preparedTables.map((table) => (
                <button
                  type="button"
                  key={table.id}
                  onClick={() => onOpenWorkspace(selectedFolder.id, 'prepare')}
                  className="flex w-full items-center gap-3 rounded-md border border-[#2D2D2D] bg-[#171717] px-3 py-2.5 text-left transition-colors hover:border-[#4A4A4A]"
                >
                  <Table2 className="h-4 w-4 flex-none text-[#D88A5F]" />
                  <span className="min-w-0 flex-1 truncate text-xs font-medium text-[#E7E7E7]">{table.name}</span>
                  <ChevronRight className="h-3.5 w-3.5 text-[#666]" />
                </button>
              )) : (
                <div className="rounded-md border border-dashed border-[#303030] px-3 py-4 text-xs text-[#777]">
                  No prepared table
                </div>
              )}
            </div>
          </div>

          <div className="space-y-2 border-t border-[#242424] p-4">
            <Button
              onClick={() => pipeline.hasUploadedTables ? onOpenWorkspace(selectedFolder.id, 'prepare') : onRequestUpload()}
              disabled={pipeline.hasUploadedTables ? !pipeline.enabledModes.prepare : !canUpload}
              className="h-9 w-full bg-[#C16E43] text-[#090909] hover:bg-[#D07A4E]"
            >
              {pipeline.hasUploadedTables ? <Wand2 className="mr-2 h-4 w-4" /> : <Upload className="mr-2 h-4 w-4" />}
              {pipeline.hasUploadedTables ? 'Open Prepare' : 'Add source files'}
            </Button>
            <div className="grid grid-cols-2 gap-2">
              <Button
                variant="outline"
                onClick={() => pipeline.enabledModes.visualize && onOpenWorkspace(selectedFolder.id, 'visualize')}
                disabled={!pipeline.enabledModes.visualize}
                className="h-8 border-[#333] bg-transparent text-xs text-[#BDBDBD] hover:bg-[#222] hover:text-white"
              >
                <BarChart3 className="mr-1.5 h-3.5 w-3.5" /> Visualize
              </Button>
              <Button
                variant="outline"
                onClick={() => pipeline.enabledModes.publish && onOpenWorkspace(selectedFolder.id, 'publish')}
                disabled={!pipeline.enabledModes.publish}
                className="h-8 border-[#333] bg-transparent text-xs text-[#BDBDBD] hover:bg-[#222] hover:text-white"
              >
                <FileText className="mr-1.5 h-3.5 w-3.5" /> Publish
              </Button>
            </div>
            {canDelete && (
              <button
                type="button"
                onClick={onDelete}
                className="flex h-8 w-full items-center justify-center gap-2 rounded-md text-xs text-[#A56A68] transition-colors hover:bg-[#F97066]/8 hover:text-[#F97066]"
              >
                <Trash2 className="h-3.5 w-3.5" /> Delete folder
              </button>
            )}
          </div>
        </aside>
      </div>

      <div className="border-t border-[#292929] bg-[#0E0E0E] px-4 py-3">
        <div className="flex items-center gap-3 overflow-x-auto pb-1">
          <div className="flex w-28 flex-none items-center gap-2 text-xs font-medium text-[#8A8A8A]">
            <FileSpreadsheet className="h-4 w-4" /> Artifacts
          </div>
          {tables.length ? tables.slice(0, 8).map((table) => (
            <button
              type="button"
              key={table.id}
              onClick={() => onOpenWorkspace(selectedFolder.id, 'prepare')}
              className="flex min-w-[170px] max-w-[220px] flex-none items-center gap-2 rounded-md border border-[#2C2C2C] bg-[#0D0D0D] px-3 py-2 text-left transition-colors hover:border-[#4A4A4A]"
            >
              {table.source === 'agent_created' ? <Table2 className="h-3.5 w-3.5 flex-none text-[#D88A5F]" /> : <Database className="h-3.5 w-3.5 flex-none text-[#999]" />}
              <span className="min-w-0 flex-1 truncate text-xs text-[#D5D5D5]">{table.name}</span>
              <span className="text-[9px] uppercase text-[#666]">{table.source === 'agent_created' ? 'Clean' : 'Source'}</span>
            </button>
          )) : (
            <span className="text-xs text-[#666]">No artifacts in this folder</span>
          )}
        </div>
      </div>
    </div>
  );
}

export function Projects() {
  const navigate = useNavigate();
  const appState = useAppState();
  const { isAdmin, isAnalyst, user } = useAuth();
  const [searchQuery, setSearchQuery] = useState('');
  const [folderQuery, setFolderQuery] = useState('');
  const [selectedFolderId, setSelectedFolderId] = useState<string | null>(null);
  const [uploadPanelOpen, setUploadPanelOpen] = useState(false);
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

  const filteredProjects = useMemo(
    () => appState.projectList.filter((project) => project.name.toLowerCase().includes(searchQuery.toLowerCase())),
    [appState.projectList, searchQuery],
  );
  const projectFolders = useMemo(
    () => appState.selectedProject
      ? appState.folderList.filter((folder) => folder.projectId === appState.selectedProject?.id)
      : [],
    [appState.folderList, appState.selectedProject],
  );
  const visibleFolders = useMemo(
    () => projectFolders.filter((folder) => folder.name.toLowerCase().includes(folderQuery.toLowerCase())),
    [folderQuery, projectFolders],
  );
  const folderIdentity = projectFolders.map((folder) => folder.id).join('|');

  useEffect(() => {
    if (!projectFolders.length) {
      setSelectedFolderId(null);
      return;
    }
    if (!projectFolders.some((folder) => folder.id === selectedFolderId)) {
      setSelectedFolderId(projectFolders[0].id);
    }
  }, [folderIdentity, projectFolders, selectedFolderId]);

  const selectedFolder = visibleFolders.find((folder) => folder.id === selectedFolderId) || visibleFolders[0] || null;
  const canCreateProject = isAdmin || isAnalyst;
  const canUpload = isAdmin || isAnalyst;
  const canDeleteFolder = isAdmin || isAnalyst;
  const infoFolder = showFolderInfoId ? appState.folderList.find((folder) => folder.id === showFolderInfoId) : null;
  const upload = useFolderUpload({
    folder: selectedFolder,
    user,
    ensureSession: appState.ensureSession,
    updateFolder: appState.updateFolder,
    loadTablesForFolder: appState.loadTablesForFolder,
    addFiles: appState.addFiles,
    onTablesCreated: (folder) => {
      appState.selectFolder(folder);
      setSelectedFolderId(folder.id);
      void appState.refreshWorkspace();
    },
  });

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
        const project = await appState.createProject(
          projectForm.name,
          projectForm.description,
          projectForm.status as 'Active' | 'Archived' | 'Published' | 'Deleted',
        );
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
      const folder = await appState.createFolder(folderForm.name, folderForm.description, appState.selectedProject.id);
      if (folder) {
        appState.selectFolder(folder);
        setSelectedFolderId(folder.id);
        setUploadPanelOpen(true);
      }
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

  const openWorkspace = (folderId: string, mode: WorkspaceMode) => {
    const folder = appState.folderList.find((item) => item.id === folderId);
    if (folder) {
      appState.selectFolder(folder);
      setSelectedFolderId(folder.id);
    }
    if (mode === 'sources') {
      setUploadPanelOpen(true);
      return;
    }
    navigate(`/app/workspace?folderId=${folderId}&mode=${mode}`);
  };

  const selectCanvasFolder = (folder: Folder) => {
    appState.selectFolder(folder);
    setSelectedFolderId(folder.id);
    setUploadPanelOpen(true);
  };

  return (
    <div className="flex h-full min-h-0 overflow-hidden bg-black max-md:flex-col">
      <aside className="flex min-h-0 w-[244px] flex-none flex-col border-r border-[#292929] bg-[#111]/95 max-md:h-[142px] max-md:w-full max-md:border-b max-md:border-r-0">
        <div className="border-b border-[#292929] p-3.5">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-[#BDBDBD]">Data projects</h2>
            {canCreateProject && (
              <button
                type="button"
                onClick={() => { resetProjectForm(); setShowCreateProject(true); }}
                className="flex h-7 w-7 flex-none items-center justify-center rounded-md bg-[#C16E43] text-[#090909] transition-colors hover:bg-[#D07A4E]"
                title="New project"
                aria-label="New project"
              >
                <Plus className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[#717171]" />
            <Input
              placeholder="Search projects"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              className="h-8 border-[#303030] bg-[#090909] pl-8 text-xs text-white placeholder:text-[#666]"
            />
          </div>
        </div>
        <div className="flex-1 space-y-1 overflow-y-auto p-2 max-md:flex max-md:space-x-1 max-md:space-y-0 max-md:overflow-x-auto">
          {filteredProjects.length ? filteredProjects.map((project) => {
            const selected = appState.selectedProject?.id === project.id;
            const folderCount = appState.folderList.filter((folder) => folder.projectId === project.id).length;
            return (
              <button
                type="button"
                key={project.id}
                onClick={() => appState.selectProject(project)}
                className={`group w-full rounded-md border px-3 py-3 text-left transition-colors max-md:min-w-[190px] ${
                  selected ? 'border-[#C16E43]/45 bg-[#181818]' : 'border-transparent hover:border-[#2F2F2F] hover:bg-[#181818]'
                }`}
              >
                <div className="flex items-center gap-2.5">
                  <div className={`flex h-7 w-7 flex-none items-center justify-center rounded-md ${selected ? 'bg-[#C16E43]/15 text-[#D88A5F]' : 'bg-[#202020] text-[#8D8D8D]'}`}>
                    <Layers3 className="h-3.5 w-3.5" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs font-medium text-[#E7E7E7]">{project.name}</p>
                    <p className="mt-0.5 text-[10px] text-[#6F6F6F]">{folderCount} {folderCount === 1 ? 'folder' : 'folders'}</p>
                  </div>
                  {selected && <span className="h-1.5 w-1.5 flex-none rounded-full bg-[#C16E43]" />}
                </div>
              </button>
            );
          }) : <p className="px-3 py-6 text-center text-xs text-[#777]">No projects found</p>}
        </div>
      </aside>

      <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto bg-[#090909]">
        {!appState.selectedProject ? (
          <EmptyState
            icon="folder"
            title={appState.projectList.length ? 'Select a project' : 'Create your first data project'}
            description={appState.projectList.length ? 'Choose a project to manage its folders and source data.' : 'Projects keep related folders, uploads, prepared tables, and canvases together.'}
            action={canCreateProject ? { label: 'Create your first project', onClick: () => { resetProjectForm(); setShowCreateProject(true); } } : undefined}
          />
        ) : (
          <>
            <header className="flex flex-wrap items-center gap-4 bg-[#0D0D0D] px-4 py-3 sm:px-5">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 text-[10px] uppercase text-[#666]">
                  <span>Data</span><ChevronRight className="h-3 w-3" /><span className="truncate text-[#999]">{appState.selectedProject.name}</span>
                </div>
                <div className="mt-1.5 flex items-center gap-2.5">
                  <h1 className="truncate text-lg font-semibold text-white">{appState.selectedProject.name}</h1>
                  <span className={`rounded-full px-2 py-0.5 text-[9px] font-semibold ${statusClass(appState.selectedProject.status)}`}>
                    {appState.selectedProject.status}
                  </span>
                  <span className="hidden text-xs text-[#707070] sm:inline">{projectFolders.length} folders</span>
                </div>
              </div>

              <div className="order-3 flex w-full items-center gap-2 sm:order-none sm:w-auto">
                <div className="relative min-w-0 flex-1 sm:w-[210px]">
                  <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[#6F6F6F]" />
                  <Input
                    placeholder="Find a folder"
                    value={folderQuery}
                    onChange={(event) => setFolderQuery(event.target.value)}
                    className="h-8 border-[#303030] bg-[#111] pl-8 text-xs text-white placeholder:text-[#666]"
                  />
                </div>
              </div>

              <div className="flex flex-none items-center gap-1.5">
                <button type="button" onClick={() => setShowProjectInfo(true)} className="flex h-8 w-8 items-center justify-center rounded-md text-[#888] hover:bg-[#222] hover:text-white" title="Project info" aria-label="Project info">
                  <Info className="h-4 w-4" />
                </button>
                {isAdmin && (
                  <button
                    type="button"
                    onClick={() => {
                      setProjectForm({
                        name: appState.selectedProject!.name,
                        description: appState.selectedProject!.description,
                        status: appState.selectedProject!.status,
                      });
                      setEditingProjectId(appState.selectedProject!.id);
                      setShowCreateProject(true);
                    }}
                    className="flex h-8 w-8 items-center justify-center rounded-md text-[#888] hover:bg-[#222] hover:text-white"
                    title="Edit project"
                    aria-label="Edit project"
                  >
                    <Pencil className="h-4 w-4" />
                  </button>
                )}
                {isAdmin && (
                  <button type="button" onClick={() => setShowDeleteProject(true)} className="flex h-8 w-8 items-center justify-center rounded-md text-[#8F6664] hover:bg-[#F97066]/10 hover:text-[#F97066]" title="Delete project" aria-label="Delete project">
                    <Trash2 className="h-4 w-4" />
                  </button>
                )}
                {canUpload && (
                  <button
                    type="button"
                    onClick={() => { resetFolderForm(); setShowCreateFolder(true); }}
                    className="flex h-7 w-7 items-center justify-center rounded-md bg-[#C16E43] text-[#090909] transition hover:bg-[#D07A4E]"
                    title="New folder"
                    aria-label="New folder"
                  >
                    <Plus className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            </header>

            {!projectFolders.length ? (
              <EmptyState
                icon="folder"
                title="No folders yet"
                description="This project does not have any data folders."
                action={canUpload ? { label: 'Create Folder', onClick: () => { resetFolderForm(); setShowCreateFolder(true); } } : undefined}
              />
            ) : !visibleFolders.length ? (
              <EmptyState icon="folder" title="No matching folders" description="Try a different folder name." />
            ) : selectedFolder ? (
              <ProjectCanvas
                key={appState.selectedProject.id}
                project={appState.selectedProject}
                folders={visibleFolders}
                selectedFolder={selectedFolder}
                canUpload={canUpload}
                canDelete={canDeleteFolder}
                onSelectFolder={selectCanvasFolder}
                onOpenWorkspace={openWorkspace}
                upload={upload}
                uploadPanelOpen={uploadPanelOpen}
                onRequestUpload={() => setUploadPanelOpen(true)}
                onCloseUpload={() => setUploadPanelOpen(false)}
                onInfo={() => setShowFolderInfoId(selectedFolder.id)}
                onDelete={() => setShowDeleteFolder(selectedFolder.id)}
              />
            ) : null}
          </>
        )}
      </main>

      <Dialog open={showCreateProject} onOpenChange={(open) => { setShowCreateProject(open); if (!open) resetProjectForm(); }}>
        <DialogContent className="max-w-md border-[#262626] bg-[#0D0D0D]">
          <DialogHeader><DialogTitle className="text-lg font-semibold text-white">{editingProjectId ? 'Edit Project' : 'Create Project'}</DialogTitle></DialogHeader>
          <div className="mt-2 space-y-4">
            <div>
              <label className="text-xs uppercase text-[#B8B8B8]">Project Name *</label>
              <Input value={projectForm.name} onChange={(event) => setProjectForm((form) => ({ ...form, name: event.target.value }))} placeholder="Enter project name" className="mt-1 border-[#262626] bg-black text-white" />
            </div>
            <div>
              <label className="text-xs uppercase text-[#B8B8B8]">Description</label>
              <textarea value={projectForm.description} onChange={(event) => setProjectForm((form) => ({ ...form, description: event.target.value }))} placeholder="Enter description" className="mt-1 h-20 w-full resize-none rounded-lg border border-[#262626] bg-black p-3 text-sm text-white placeholder:text-[#8C8C8C] focus:border-[#C16E43] focus:outline-none" />
            </div>
            <div>
              <label className="text-xs uppercase text-[#B8B8B8]">Status</label>
              <select value={projectForm.status} onChange={(event) => setProjectForm((form) => ({ ...form, status: event.target.value }))} className="mt-1 h-10 w-full rounded-lg border border-[#262626] bg-black px-3 text-sm text-white">
                <option>Active</option><option>Archived</option><option>Published</option><option>Deleted</option>
              </select>
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <Button variant="outline" onClick={() => { setShowCreateProject(false); resetProjectForm(); }} className="border-[#262626] text-[#B8B8B8] hover:bg-[#181818]">Cancel</Button>
              <Button onClick={handleCreateProject} disabled={!projectForm.name.trim() || isSubmitting} className="bg-[#C16E43] text-[#0A0A0A] hover:bg-[#D07A4E]">
                {isSubmitting ? (editingProjectId ? 'Saving...' : 'Creating...') : (editingProjectId ? 'Save Changes' : 'Create Project')}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={showCreateFolder} onOpenChange={setShowCreateFolder}>
        <DialogContent className="max-w-md border-[#262626] bg-[#0D0D0D]">
          <DialogHeader><DialogTitle className="text-lg font-semibold text-white">Create Folder</DialogTitle></DialogHeader>
          <div className="mt-2 space-y-4">
            <div>
              <label className="text-xs uppercase text-[#B8B8B8]">Folder Name *</label>
              <Input value={folderForm.name} onChange={(event) => setFolderForm((form) => ({ ...form, name: event.target.value }))} placeholder="Enter folder name" className="mt-1 border-[#262626] bg-black text-white" />
            </div>
            <div>
              <label className="text-xs uppercase text-[#B8B8B8]">Description</label>
              <textarea value={folderForm.description} onChange={(event) => setFolderForm((form) => ({ ...form, description: event.target.value }))} placeholder="Enter description" className="mt-1 h-20 w-full resize-none rounded-lg border border-[#262626] bg-black p-3 text-sm text-white placeholder:text-[#8C8C8C] focus:border-[#C16E43] focus:outline-none" />
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <Button variant="outline" onClick={() => setShowCreateFolder(false)} className="border-[#262626] text-[#B8B8B8] hover:bg-[#181818]">Cancel</Button>
              <Button onClick={handleCreateFolder} disabled={!folderForm.name.trim() || isSubmitting} className="bg-[#C16E43] text-[#0A0A0A] hover:bg-[#D07A4E]">{isSubmitting ? 'Creating...' : 'Create Folder'}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={showProjectInfo} onOpenChange={setShowProjectInfo}>
        <DialogContent className="max-w-md border-[#262626] bg-[#0D0D0D]">
          <DialogHeader><DialogTitle className="text-lg font-semibold text-white">Project Info</DialogTitle></DialogHeader>
          {appState.selectedProject && (
            <div className="mt-2 space-y-3 text-sm">
              <p className="font-medium text-white">{appState.selectedProject.name}</p>
              <p className="text-[#B8B8B8]">{appState.selectedProject.description}</p>
              <div className="flex flex-wrap gap-4 text-xs text-[#8C8C8C]">
                <span>Status: {appState.selectedProject.status}</span><span>Created: {appState.selectedProject.createdAt}</span><span>By: {appState.selectedProject.createdBy}</span>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={!!showFolderInfoId} onOpenChange={() => setShowFolderInfoId(null)}>
        <DialogContent className="max-w-md border-[#262626] bg-[#0D0D0D]">
          <DialogHeader><DialogTitle className="text-lg font-semibold text-white">Folder Info</DialogTitle></DialogHeader>
          {infoFolder && (
            <div className="mt-2 space-y-3 text-sm">
              <p className="font-medium text-white">{infoFolder.name}</p>
              <p className="text-[#B8B8B8]">{infoFolder.description}</p>
              <div className="flex flex-wrap gap-4 text-xs text-[#8C8C8C]">
                <span>Status: {infoFolder.status}</span><span>Created: {infoFolder.createdAt}</span><span>By: {infoFolder.createdBy}</span>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <ConfirmDialog open={showDeleteProject} onOpenChange={setShowDeleteProject} title="Delete Project?" description={`This will permanently delete "${appState.selectedProject?.name}" and all its folders. This action cannot be undone.`} onConfirm={handleDeleteProject} isLoading={isSubmitting} />
      <ConfirmDialog open={!!showDeleteFolder} onOpenChange={() => setShowDeleteFolder(null)} title="Delete Folder?" description="This will permanently delete this folder. This action cannot be undone." onConfirm={() => showDeleteFolder && handleDeleteFolder(showDeleteFolder)} isLoading={isSubmitting} />
    </div>
  );
}
