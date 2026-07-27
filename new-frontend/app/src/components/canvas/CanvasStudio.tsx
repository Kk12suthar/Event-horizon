import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import type { Edge, ReactFlowInstance } from '@xyflow/react';
import {
  ArrowLeft,
  Bot,
  Check,
  ChevronDown,
  CircleAlert,
  Maximize2,
  Grid3X3,
  Layers3,
  Loader2,
  MessageSquare,
  PanelRight,
  Plus,
  Redo2,
  RefreshCw,
  Send,
  Sparkles,
  SquareStack,
  StopCircle,
  Trash2,
  Undo2,
  X,
} from 'lucide-react';
import { useAppState } from '@/hooks/useAppState';
import { useAuth } from '@/hooks/useAuth';
import { useVisualDocument } from '@/hooks/useVisualDocument';
import { useCanvasAgent } from '@/hooks/useCanvasAgent';
import { removeElementOp, resizeElementOp, type CanvasLayoutAlgorithm } from '@/lib/visualDocuments';
import type { VisualElement } from '@/types/visualDocument.generated';
import type { ChatMessage } from '@/types';
import { VisualCanvas } from './VisualCanvas';
import type { CanvasFlowNode } from './VisualElementNode';

const layoutOptions: Array<{ id: CanvasLayoutAlgorithm; label: string }> = [
  { id: 'layered', label: 'Layered flow' },
  { id: 'tree', label: 'Decision tree' },
  { id: 'grid', label: 'Balanced grid' },
  { id: 'timeline', label: 'Timeline' },
  { id: 'radial', label: 'Radial map' },
];

const promptIdeas = [
  'Map the current process and highlight bottlenecks',
  'Create a KPI board from the selected table',
  'Build a decision tree with alternate paths',
  'Turn this into a clear project Gantt',
];

function iconButtonClass(active = false) {
  return [
    'inline-flex h-8 w-8 flex-none items-center justify-center rounded-lg border text-[#A1A1AA] transition',
    active
      ? 'border-[#6A422D] bg-[#2A1911] text-[#E2A56F]'
      : 'border-[#2D2D2D] bg-[#121212] hover:border-[#464646] hover:bg-[#1B1B1B] hover:text-white',
    'disabled:cursor-not-allowed disabled:opacity-35',
  ].join(' ');
}

function AgentMessages({ messages, isGenerating }: { messages: ChatMessage[]; isGenerating: boolean }) {
  const endRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => endRef.current?.scrollIntoView({ behavior: 'smooth' }), [messages, isGenerating]);
  return (
    <div className="flex-1 space-y-3 overflow-y-auto px-3 py-4">
      {!messages.length && (
        <div className="rounded-xl border border-[#292929] bg-[#0D0D0D] p-4">
          <div className="flex items-center gap-2 text-xs font-semibold text-[#E4E4E7]">
            <Sparkles className="h-3.5 w-3.5 text-[#C16E43]" /> Describe the outcome
          </div>
          <p className="mt-2 text-[11px] leading-relaxed text-[#7F7F7F]">
            The canvas agent can inspect the current visual, add mixed diagram types, ground charts in your selected table, and repair the layout.
          </p>
        </div>
      )}
      {messages.map((message) => {
        if (message.type === 'tool_call' || message.type === 'tool_response' || message.type === 'transition' || message.type === 'thinking') {
          return (
            <div key={message.id} className="flex items-center gap-2 px-1 text-[10px] text-[#777]">
              {message.type === 'tool_call' ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
              <span className="truncate">{message.content || message.metadata?.toolName || 'Agent activity'}</span>
            </div>
          );
        }
        const isUser = message.type === 'user';
        const isError = message.type === 'error';
        return (
          <div key={message.id} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
            <div
              className={[
                'max-w-[92%] whitespace-pre-wrap rounded-xl px-3 py-2.5 text-[12px] leading-relaxed',
                isUser ? 'rounded-br-sm bg-[#C16E43] text-[#080808]' :
                isError ? 'border border-[#4A3434] bg-[#211313] text-[#D6A1A1]' :
                'rounded-bl-sm border border-[#292929] bg-[#141414] text-[#D4D4D8]',
              ].join(' ')}
            >
              {message.content || (message.metadata?.streaming ? 'Thinking…' : '')}
            </div>
          </div>
        );
      })}
      {isGenerating && !messages.some((message) => message.metadata?.streaming) && (
        <div className="flex items-center gap-2 px-1 text-[10px] text-[#8A8A8A]">
          <Loader2 className="h-3 w-3 animate-spin text-[#C16E43]" /> Agent is composing the canvas…
        </div>
      )}
      <div ref={endRef} />
    </div>
  );
}

function AgentPanel({
  messages,
  isGenerating,
  onSend,
  onStop,
  onClose,
}: {
  messages: ChatMessage[];
  isGenerating: boolean;
  onSend: (query: string) => void;
  onStop: () => void;
  onClose?: () => void;
}) {
  const [query, setQuery] = useState('');
  const submit = () => {
    if (!query.trim() || isGenerating) return;
    onSend(query);
    setQuery('');
  };
  return (
    <section className="flex h-full min-h-0 flex-col bg-[#090909]" aria-label="Canvas agent">
      <header className="flex h-12 flex-none items-center justify-between border-b border-[#262626] px-3">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg border border-[#3A2A21] bg-[#1F140E]">
            <Bot className="h-3.5 w-3.5 text-[#D38A60]" />
          </span>
          <div>
            <div className="text-xs font-semibold text-[#F4F4F5]">Canvas agent</div>
            <div className="text-[9px] text-[#6F6F6F]">Creates and revises live</div>
          </div>
        </div>
        {onClose && <button className={iconButtonClass()} onClick={onClose} aria-label="Close agent panel"><X className="h-3.5 w-3.5" /></button>}
      </header>
      <AgentMessages messages={messages} isGenerating={isGenerating} />
      {!messages.length && (
        <div className="flex flex-wrap gap-1.5 px-3 pb-3">
          {promptIdeas.map((idea) => (
            <button key={idea} onClick={() => setQuery(idea)} className="rounded-full border border-[#2C2C2C] px-2.5 py-1.5 text-left text-[9px] leading-tight text-[#8A8A8A] transition hover:border-[#4A3428] hover:text-[#D4D4D8]">
              {idea}
            </button>
          ))}
        </div>
      )}
      <div className="flex-none border-t border-[#262626] p-3">
        <div className="rounded-xl border border-[#343434] bg-[#111] p-2 focus-within:border-[#6A422D]">
          <textarea
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                submit();
              }
            }}
            rows={3}
            placeholder="Create or change anything on this canvas…"
            className="w-full resize-none bg-transparent px-1 text-xs leading-relaxed text-[#E4E4E7] outline-none placeholder:text-[#5D5D5D]"
          />
          <div className="flex items-center justify-between pt-1">
            <span className="px-1 text-[9px] text-[#5E5E5E]">Enter to send · Shift+Enter for line</span>
            {isGenerating ? (
              <button onClick={onStop} className="flex h-7 items-center gap-1.5 rounded-lg border border-[#3A3A3A] px-2 text-[10px] text-[#C4C4C4] hover:bg-[#1A1A1A]">
                <StopCircle className="h-3 w-3" /> Stop
              </button>
            ) : (
              <button onClick={submit} disabled={!query.trim()} className="flex h-7 items-center gap-1.5 rounded-lg bg-[#C16E43] px-2.5 text-[10px] font-semibold text-black transition hover:bg-[#D07A4E] disabled:opacity-35">
                <Send className="h-3 w-3" /> Send
              </button>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

function InspectorPanel({
  element,
  documentTitle,
  revision,
  outline,
  readability,
  layers,
  onSelect,
  onClose,
}: {
  element: VisualElement | null;
  documentTitle: string;
  revision: number;
  outline: Array<Record<string, unknown>>;
  readability: Record<string, unknown> | null;
  layers: Array<{ id: string; name: string; visible?: boolean; kind?: string }>;
  onSelect: (id: string) => void;
  onClose?: () => void;
}) {
  const provenance = element && 'provenance' in element ? element.provenance : null;
  return (
    <aside className="flex h-full min-h-0 flex-col bg-[#090909]" aria-label="Canvas inspector">
      <header className="flex h-12 flex-none items-center justify-between border-b border-[#262626] px-3">
        <div className="flex items-center gap-2 text-xs font-semibold text-[#F4F4F5]"><PanelRight className="h-3.5 w-3.5 text-[#999]" /> Inspector</div>
        {onClose && <button className={iconButtonClass()} onClick={onClose} aria-label="Close inspector"><X className="h-3.5 w-3.5" /></button>}
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        <section className="rounded-xl border border-[#292929] bg-[#101010] p-3">
          <div className="truncate text-xs font-semibold text-[#E4E4E7]">{documentTitle}</div>
          <div className="mt-1 flex items-center justify-between text-[9px] text-[#71717A]">
            <span>Revision {revision}</span>
            {typeof readability?.score === 'number' && <span>Readability {Math.round(Number(readability.score))}%</span>}
          </div>
        </section>

        {element ? (
          <section className="mt-3 rounded-xl border border-[#292929] bg-[#101010] p-3">
            <div className="flex items-center justify-between">
              <span className="rounded-md bg-[#232323] px-1.5 py-1 text-[9px] uppercase tracking-wider text-[#B7B7B7]">{element.type}</span>
              <span className="max-w-[145px] truncate font-mono text-[8px] text-[#5E5E5E]">{element.id}</span>
            </div>
            {'label' in element && <div className="mt-3 text-xs font-medium text-[#E4E4E7]">{String(element.label)}</div>}
            {'title' in element && <div className="mt-3 text-xs font-medium text-[#E4E4E7]">{String(element.title)}</div>}
            {'text' in element && element.text && <div className="mt-3 whitespace-pre-wrap text-[11px] text-[#A1A1AA]">{String(element.text)}</div>}
            {'rect' in element && (
              <div className="mt-3 grid grid-cols-2 gap-1.5 text-[9px] text-[#858585]">
                {Object.entries(element.rect).map(([key, value]) => <div key={key} className="rounded bg-[#171717] px-2 py-1.5"><span className="uppercase text-[#5E5E5E]">{key}</span> {Math.round(value)}</div>)}
              </div>
            )}
            {provenance && (
              <div className="mt-3 border-t border-[#272727] pt-3">
                <div className="text-[9px] font-medium uppercase tracking-wider text-[#6F6F6F]">Data provenance</div>
                <div className="mt-1 truncate text-[10px] text-[#A1A1AA]">{provenance.source_table_id}</div>
                <div className="mt-1 text-[9px] text-[#707070]">{provenance.aggregation || 'none'} · revision {provenance.transform_revision ?? 'current'}</div>
              </div>
            )}
          </section>
        ) : (
          <div className="mt-3 rounded-xl border border-dashed border-[#292929] p-5 text-center text-[10px] leading-relaxed text-[#6F6F6F]">Select an element to inspect its geometry, data source, and semantics.</div>
        )}

        <section className="mt-3">
          <div className="mb-2 flex items-center gap-2 text-[9px] font-medium uppercase tracking-[0.14em] text-[#707070]"><Layers3 className="h-3 w-3" /> Layers</div>
          <div className="space-y-1">
            {layers.map((layer) => (
              <div key={layer.id} className="flex items-center justify-between rounded-lg border border-[#252525] px-2.5 py-2 text-[10px]">
                <span className="truncate text-[#B4B4B4]">{layer.name}</span>
                <span className="text-[8px] uppercase text-[#5E5E5E]">{layer.kind}{layer.visible === false ? ' · hidden' : ''}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="mt-4">
          <div className="mb-2 flex items-center gap-2 text-[9px] font-medium uppercase tracking-[0.14em] text-[#707070]"><SquareStack className="h-3 w-3" /> Semantic outline</div>
          <div className="space-y-1">
            {outline.slice(0, 100).map((item, index) => {
              const id = String(item.id || '');
              return (
                <button key={id || index} onClick={() => id && onSelect(id)} className="flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-left text-[10px] text-[#8F8F8F] hover:bg-[#171717] hover:text-[#E4E4E7]">
                  <span className="truncate">{String(item.label || item.title || id || 'Canvas element')}</span>
                  <span className="ml-2 text-[8px] uppercase text-[#555]">{String(item.type || '')}</span>
                </button>
              );
            })}
            {!outline.length && <div className="text-[10px] text-[#5E5E5E]">No elements yet.</div>}
          </div>
        </section>
      </div>
    </aside>
  );
}

export function CanvasStudio() {
  const appState = useAppState();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedFolder = appState.selectedFolder;
  const selectedProject = appState.selectedProject;
  const selectedTable = appState.selectedTable;
  const requestedDocumentId = searchParams.get('documentId');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [agentOpen, setAgentOpen] = useState(() => typeof window === 'undefined' || window.innerWidth >= 1280);
  const [inspectorOpen, setInspectorOpen] = useState(() => typeof window !== 'undefined' && window.innerWidth >= 1280);
  const [newTitle, setNewTitle] = useState('');
  const [creating, setCreating] = useState(false);
  const flowRef = useRef<ReactFlowInstance<CanvasFlowNode, Edge> | null>(null);
  const sourceTableIds = useMemo(() => selectedTable ? [selectedTable.id] : [], [selectedTable]);

  const visual = useVisualDocument({
    folderId: selectedFolder?.id || null,
    projectId: selectedFolder?.projectId || selectedProject?.id || null,
    sessionId: appState.activeSession?.id,
    sourceTableIds,
    requestedDocumentId,
  });

  const { commit: commitVisual, refresh: refreshVisual, select: selectVisual } = visual;

  const handleSelectionChange = useCallback((ids: string[]) => {
    setSelectedIds((current) =>
      current.length === ids.length && current.every((id, index) => id === ids[index])
        ? current
        : ids,
    );
  }, []);

  const handleElementRectChange = useCallback(
    (elementId: string, rect: Parameters<typeof resizeElementOp>[1]) => {
      void commitVisual([resizeElementOp(elementId, rect)], 'Move or resize element');
    },
    [commitVisual],
  );
  const handleArtifact = useCallback(
    (documentId?: string) => {
      if (documentId && documentId !== visual.document?.metadata.id) {
        void selectVisual(documentId);
      } else {
        void refreshVisual();
      }
    },
    [refreshVisual, selectVisual, visual.document?.metadata.id],
  );

  const agent = useCanvasAgent({
    folder: selectedFolder,
    session: appState.activeSession,
    user,
    selectedTable,
    documentId: visual.document?.metadata.id || null,
    ensureSession: appState.ensureSession,
    onVisualArtifact: handleArtifact,
  });

  useEffect(() => {
    const id = visual.document?.metadata.id;
    if (!id || searchParams.get('documentId') === id) return;
    const next = new URLSearchParams(searchParams);
    next.set('documentId', id);
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams, visual.document?.metadata.id]);

  useEffect(() => setSelectedIds([]), [visual.document?.metadata.id]);

  const selectedElement = useMemo(
    () => visual.document?.elements?.find((element) => element.id === selectedIds[0]) || null,
    [selectedIds, visual.document?.elements],
  );

  const removeSelection = useCallback(() => {
    const document = visual.document;
    if (!document || !selectedIds.length || visual.isSaving) return;
    const selected = new Set(selectedIds);
    const connectedEdges = (document.elements || [])
      .filter((element) => element.type === 'edge' && (selected.has(element.source_id) || selected.has(element.target_id)))
      .map((element) => element.id);
    const edgeIds = [
      ...new Set([
        ...connectedEdges,
        ...(document.elements || []).filter((element) => element.type === 'edge' && selected.has(element.id)).map((element) => element.id),
      ]),
    ];
    const nodeIds = selectedIds.filter((id) => !edgeIds.includes(id));
    void visual.commit([...edgeIds, ...nodeIds].map(removeElementOp), `Delete ${edgeIds.length + nodeIds.length} element${edgeIds.length + nodeIds.length === 1 ? '' : 's'}`);
    setSelectedIds([]);
  }, [selectedIds, visual]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.matches('input, textarea, select, [contenteditable="true"]')) return;
      if ((event.key === 'Delete' || event.key === 'Backspace') && selectedIds.length) {
        event.preventDefault();
        removeSelection();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [removeSelection, selectedIds.length]);

  const createCanvas = async () => {
    setCreating(true);
    try {
      await visual.create(newTitle.trim() || `${selectedFolder?.name || 'Workspace'} canvas`);
      setNewTitle('');
    } finally {
      setCreating(false);
    }
  };

  if (!selectedFolder) {
    return (
      <div className="flex h-full items-center justify-center bg-black p-6">
        <div className="w-full max-w-md rounded-2xl border border-[#2B2B2B] bg-[#0C0C0C] p-7 text-center shadow-2xl">
          <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-xl border border-[#3B2B22] bg-[#1D130E]"><Grid3X3 className="h-5 w-5 text-[#C16E43]" /></div>
          <h1 className="mt-4 text-lg font-semibold text-[#F4F4F5]">Choose a workspace folder</h1>
          <p className="mt-2 text-sm leading-relaxed text-[#818181]">A canvas belongs to a folder so the agent can use the correct tables, session, history, and permissions.</p>
          <button onClick={() => navigate('/app/project')} className="mt-5 inline-flex h-9 items-center gap-2 rounded-lg bg-[#C16E43] px-4 text-xs font-semibold text-black hover:bg-[#D07A4E]"><ArrowLeft className="h-3.5 w-3.5" /> Choose folder</button>
        </div>
      </div>
    );
  }

  return (
    <div className="relative flex h-full min-h-0 w-full flex-col overflow-hidden bg-black">
      <header className="flex h-12 flex-none items-center gap-2 border-b border-[#262626] bg-[#0A0A0A] px-2 sm:px-3">
        <button className={iconButtonClass()} onClick={() => navigate(`/app/workspace?folderId=${selectedFolder.id}`)} title="Back to workspace" aria-label="Back to workspace"><ArrowLeft className="h-3.5 w-3.5" /></button>
        <div className="relative min-w-0 flex-1 sm:max-w-[280px]">
          <select
            value={visual.document?.metadata.id || ''}
            onChange={(event) => void visual.select(event.target.value)}
            disabled={!visual.documents.length}
            className="h-8 w-full appearance-none truncate rounded-lg border border-[#303030] bg-[#121212] pl-3 pr-8 text-xs font-medium text-[#E4E4E7] outline-none hover:border-[#454545] disabled:text-[#666]"
            aria-label="Open canvas"
          >
            {!visual.documents.length && <option value="">No canvases yet</option>}
            {visual.documents.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
          </select>
          <ChevronDown className="pointer-events-none absolute right-2.5 top-2 h-3.5 w-3.5 text-[#777]" />
        </div>
        <button className={iconButtonClass()} onClick={() => setCreating(true)} title="New canvas" aria-label="New canvas"><Plus className="h-4 w-4" /></button>
        <div className="hidden h-5 w-px bg-[#2B2B2B] sm:block" />
        <button className={iconButtonClass()} onClick={() => void visual.undo()} disabled={!visual.canUndo || visual.isSaving} title="Undo"><Undo2 className="h-3.5 w-3.5" /></button>
        <button className={iconButtonClass()} onClick={() => void visual.redo()} disabled={!visual.canRedo || visual.isSaving} title="Redo"><Redo2 className="h-3.5 w-3.5" /></button>
        <div className="relative hidden sm:block">
          <select
            defaultValue=""
            onChange={(event) => {
              if (event.target.value) void visual.layout(event.target.value as CanvasLayoutAlgorithm, selectedIds);
              event.target.value = '';
            }}
            disabled={!visual.document || visual.isSaving}
            className="h-8 appearance-none rounded-lg border border-[#303030] bg-[#121212] pl-8 pr-7 text-[10px] text-[#A1A1AA] outline-none hover:border-[#454545]"
            aria-label="Arrange canvas"
          >
            <option value="" disabled>Arrange</option>
            {layoutOptions.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
          </select>
          <Grid3X3 className="pointer-events-none absolute left-2.5 top-2.5 h-3 w-3 text-[#888]" />
          <ChevronDown className="pointer-events-none absolute right-2 top-2.5 h-3 w-3 text-[#666]" />
        </div>
        <button className={`${iconButtonClass()} hidden sm:inline-flex`} onClick={() => flowRef.current?.fitView({ padding: 0.2, duration: 300 })} title="Fit canvas"><Maximize2 className="h-3.5 w-3.5" /></button>
        <button className={`${iconButtonClass()} hidden sm:inline-flex`} onClick={() => void visual.refresh()} title="Refresh canvas"><RefreshCw className={`h-3.5 w-3.5 ${visual.isLoading ? 'animate-spin' : ''}`} /></button>
        <button className={iconButtonClass(agentOpen)} onClick={() => setAgentOpen((open) => !open)} title="Canvas agent"><MessageSquare className="h-3.5 w-3.5" /></button>
        <button className={iconButtonClass(inspectorOpen)} onClick={() => setInspectorOpen((open) => !open)} title="Inspector"><PanelRight className="h-3.5 w-3.5" /></button>
      </header>

      {visual.error && (
        <div className="flex flex-none items-center gap-2 border-b border-[#3A2D28] bg-[#1A100D] px-3 py-2 text-[10px] text-[#D5A28A]">
          <CircleAlert className="h-3.5 w-3.5 flex-none" /><span className="min-w-0 flex-1 truncate">{visual.error}</span>
          <button onClick={() => void visual.refresh()} className="font-medium text-[#E2A56F]">Reload</button>
        </div>
      )}

      <div className="relative flex min-h-0 flex-1">
        {agentOpen && (
          <div className="absolute inset-y-0 left-0 z-30 w-full border-r border-[#262626] sm:w-[340px] xl:static xl:z-auto xl:flex-none">
            <AgentPanel messages={agent.messages} isGenerating={agent.isGenerating} onSend={(query) => void agent.send(query)} onStop={agent.stop} onClose={() => setAgentOpen(false)} />
          </div>
        )}

        <main className="relative min-w-0 flex-1">
          {visual.document ? (
            <>
              <VisualCanvas
                document={visual.document}
                selectedIds={selectedIds}
                onSelectionChange={handleSelectionChange}
                onElementRectChange={handleElementRectChange}
                onReady={(instance) => { flowRef.current = instance; }}
              />
              <div className="pointer-events-none absolute left-3 top-3 flex items-center gap-2">
                <span className="rounded-md border border-[#2C2C2C] bg-[#0A0A0A]/85 px-2 py-1 text-[9px] text-[#737373] backdrop-blur">
                  {visual.document.elements?.length || 0} elements · rev {visual.document.metadata.revision || 0}
                </span>
                {visual.isSaving && <span className="flex items-center gap-1 rounded-md border border-[#3B2A22] bg-[#160F0B]/90 px-2 py-1 text-[9px] text-[#C58B6A]"><Loader2 className="h-2.5 w-2.5 animate-spin" /> Saving</span>}
              </div>
              {selectedIds.length > 0 && (
                <div className="absolute bottom-4 left-1/2 z-10 flex -translate-x-1/2 items-center gap-2 rounded-xl border border-[#333] bg-[#101010]/95 p-1.5 shadow-2xl backdrop-blur">
                  <span className="px-2 text-[10px] text-[#9A9A9A]">{selectedIds.length} selected</span>
                  <button onClick={removeSelection} disabled={visual.isSaving} className="flex h-7 items-center gap-1.5 rounded-lg border border-[#3A2E2E] px-2 text-[10px] text-[#C1A0A0] hover:bg-[#211414]"><Trash2 className="h-3 w-3" /> Delete</button>
                </div>
              )}
            </>
          ) : visual.isLoading ? (
            <div className="flex h-full items-center justify-center bg-[#050505] text-xs text-[#8A8A8A]"><Loader2 className="mr-2 h-4 w-4 animate-spin text-[#C16E43]" /> Loading canvas…</div>
          ) : (
            <div className="flex h-full items-center justify-center bg-[#050505] p-5">
              <div className="max-w-md rounded-2xl border border-[#2B2B2B] bg-[#0B0B0B] p-7 text-center shadow-2xl">
                <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-xl border border-[#3B2B22] bg-[#1D130E]"><Sparkles className="h-5 w-5 text-[#C16E43]" /></div>
                <h2 className="mt-4 text-base font-semibold text-[#F4F4F5]">Start a living visual document</h2>
                <p className="mt-2 text-xs leading-relaxed text-[#818181]">Every user drag and every agent change shares one revision-safe history. Create a canvas, then tell the agent what you want to see.</p>
                <button onClick={() => setCreating(true)} className="mt-5 inline-flex h-9 items-center gap-2 rounded-lg bg-[#C16E43] px-4 text-xs font-semibold text-black hover:bg-[#D07A4E]"><Plus className="h-3.5 w-3.5" /> Create canvas</button>
              </div>
            </div>
          )}
        </main>

        {inspectorOpen && visual.document && (
          <div className="absolute inset-y-0 right-0 z-30 w-full border-l border-[#262626] sm:w-[310px] xl:static xl:z-auto xl:flex-none">
            <InspectorPanel
              element={selectedElement}
              documentTitle={visual.document.metadata.title}
              revision={visual.document.metadata.revision || 0}
              outline={(visual.outline?.outline || []) as Array<Record<string, unknown>>}
              readability={visual.readability}
              layers={visual.document.layers || []}
              onSelect={(id) => setSelectedIds([id])}
              onClose={() => setInspectorOpen(false)}
            />
          </div>
        )}
      </div>

      {creating && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm" onMouseDown={(event) => { if (event.target === event.currentTarget) { setCreating(false); setNewTitle(''); } }}>
          <form onSubmit={(event) => { event.preventDefault(); void createCanvas(); }} className="w-full max-w-sm rounded-2xl border border-[#343434] bg-[#101010] p-5 shadow-2xl">
            <div className="flex items-center justify-between">
              <div><h2 className="text-sm font-semibold text-[#F4F4F5]">New visual document</h2><p className="mt-1 text-[10px] text-[#777]">You and the canvas agent will edit the same history.</p></div>
              <button type="button" onClick={() => { setCreating(false); setNewTitle(''); }} className={iconButtonClass()}><X className="h-3.5 w-3.5" /></button>
            </div>
            <label className="mt-4 block text-[10px] font-medium text-[#9A9A9A]">Canvas name</label>
            <input autoFocus value={newTitle} onChange={(event) => setNewTitle(event.target.value)} placeholder={`${selectedFolder.name} canvas`} maxLength={300} className="mt-1.5 h-10 w-full rounded-lg border border-[#343434] bg-[#090909] px-3 text-xs text-[#E4E4E7] outline-none placeholder:text-[#555] focus:border-[#6A422D]" />
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" onClick={() => { setCreating(false); setNewTitle(''); }} className="h-8 rounded-lg border border-[#333] px-3 text-[10px] text-[#A1A1AA] hover:bg-[#191919]">Cancel</button>
              <button type="submit" disabled={visual.isSaving} className="flex h-8 items-center gap-1.5 rounded-lg bg-[#C16E43] px-3 text-[10px] font-semibold text-black hover:bg-[#D07A4E] disabled:opacity-50">{visual.isSaving && <Loader2 className="h-3 w-3 animate-spin" />} Create</button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}

export default CanvasStudio;
