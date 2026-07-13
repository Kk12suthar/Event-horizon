import { useCallback, useEffect, useRef, useState } from 'react';
import { streamSse } from '../lib/api';
import { streamUrlForMode } from './usePipelineStage';
import type { ChartWidget, ChatMessage, DataTable, Folder, MessageType, Session, TokenUsage, User, WorkspaceMode } from '../types';

/**
 * Raw SSE event payload as delivered by `streamSse` (see `lib/api.ts`).
 * Agent events carry either a `type` or a `status` discriminator plus
 * event-specific fields (`message`, `tool_name`, `text`, `final_output`, ...).
 */
export type SseEvent = Record<string, unknown>;

/**
 * A chat message before it is committed to the thread. `id` and `timestamp`
 * are assigned by the hook when the draft is pushed, keeping the mapper a pure,
 * deterministic function that is trivial to test in isolation.
 */
export interface ChatMessageDraft {
  type: MessageType;
  content: string;
  metadata?: ChatMessage['metadata'];
}

/**
 * Normalize an SSE event to its logical type, accepting either the `type` or
 * the legacy `status` discriminator used by the agent stream.
 */
export function getSseEventType(event: SseEvent): string {
  return String(event.type ?? event.status ?? '');
}

export function isTerminalSseEvent(event: SseEvent): boolean {
  const type = getSseEventType(event);
  return type === 'completion' || type === 'result';
}

export function terminalFinalOutput(event: SseEvent): string {
  const type = getSseEventType(event);
  if (type === 'completion') return String(event.final_output || '');
  if (type === 'result') {
    return String(event.llm_response || event.final_output || event.text || event.message || '');
  }
  return '';
}

function chartArtifactFromEvent(event: SseEvent): ChartWidget | null {
  const raw = event.artifact ?? event.data;
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null;
  const artifact = raw as Record<string, unknown>;
  const artifactType = String(event.artifact_type || artifact.artifact_type || '');
  const type = String(artifact.type || '');
  if (artifactType !== 'chart' || !artifact.id || !['line', 'bar', 'area', 'pie', 'radial', 'kpi'].includes(type)) {
    return null;
  }
  const data = Array.isArray(artifact.data)
    ? artifact.data.map((value) => {
        const point = value && typeof value === 'object' && !Array.isArray(value)
          ? value as Record<string, unknown>
          : {};
        return { label: String(point.label || ''), value: Number(point.value || 0) };
      })
    : [];
  if (data.length === 0) return null;
  const config = artifact.config && typeof artifact.config === 'object' && !Array.isArray(artifact.config)
    ? artifact.config as Record<string, unknown>
    : {};
  const position = artifact.position && typeof artifact.position === 'object' && !Array.isArray(artifact.position)
    ? artifact.position as Record<string, unknown>
    : {};
  return {
    id: String(artifact.id),
    artifact_type: 'chart',
    name: String(artifact.name || artifact.title || 'Chart preview'),
    title: String(artifact.title || artifact.name || 'Chart preview'),
    type: type as ChartWidget['type'],
    data,
    config: {
      primaryColor: String(config.primaryColor || '#F4F4F5'),
      showGrid: config.showGrid !== false,
      showLegend: config.showLegend === true,
      showTooltip: config.showTooltip !== false,
    },
    position: {
      x: Number(position.x || 0),
      y: Number(position.y || 0),
      w: Number(position.w || (type === 'kpi' ? 4 : 12)),
      h: Number(position.h || (type === 'kpi' ? 3 : 6)),
    },
    sourceTableId: String(artifact.sourceTableId || artifact.source_table_id || ''),
    source_table_id: String(artifact.source_table_id || artifact.sourceTableId || ''),
    xField: String(artifact.xField || ''),
    yFields: Array.isArray(artifact.yFields) ? artifact.yFields.map(String) : [],
    transformRevision: Number(artifact.transformRevision || artifact.transform_revision || 0),
    transform_revision: Number(artifact.transform_revision || artifact.transformRevision || 0),
    status: String(artifact.status || 'draft') === 'ready' ? 'ready' : 'draft',
    createdAt: String(artifact.createdAt || artifact.created_at || ''),
  };
}
/**
 * Mode-independent mapping from an SSE event to a {@link ChatMessageDraft}.
 *
 * This is the single source of truth for how streamed agent events become chat
 * items, and it is **identical regardless of `mode`** - it does not take a
 * `mode` argument at all, so the same event always yields the same draft in
 * Sources / Prepare / Visualize / Publish (design Property 4: schema invariance).
 *
 * Mapping table (design.md "Reused streaming schema"):
 *   - `stream_start` | `status`              -> activity
 *   - `tool_call` | `function_request`       -> tool_call
 *   - `tool_response` | `function_response`  -> tool_response
 *   - `final_response`                       -> agent
 *   - `error`                                -> error
 *
 * Events that do not map to a renderable message (e.g. `completion`, which the
 * hook handles as stop + refresh artifacts) return `null`.
 */
export function mapSseEventToMessage(event: SseEvent): ChatMessageDraft | null {
  const type = getSseEventType(event);
  switch (type) {

    case 'stream_start':
    case 'status':
    case 'stream':
      return null;

    case 'artifact': {
      const artifact = chartArtifactFromEvent(event);
      if (!artifact) return null;
      return {
        type: 'chart_result',
        content: artifact.name,
        metadata: { artifact, artifactStatus: artifact.status === 'ready' ? 'saved' : 'draft' },
      };
    }

    case 'tool_call':
    case 'function_request': {
      const toolName = String(event.tool_name || 'Tool');
      return {
        type: 'tool_call',
        content: `${toolName} requested`,
        metadata: {
          toolName,
          callId: String(event.call_id || event.id || toolName),
          toolStatus: 'pending',
          toolArgs: event.tool_args,
        },
      };
    }

    case 'tool_response':
    case 'function_response': {
      const toolName = String(event.tool_name || 'Tool');
      const response = event.response && typeof event.response === 'object'
        ? (event.response as Record<string, unknown>).result ?? event.response
        : event.response;
      return {
        type: 'tool_response',
        content: `${toolName} completed`,
        metadata: {
          toolName,
          callId: String(event.call_id || event.id || toolName),
          toolStatus: 'complete',
          toolResponse: response,
          durationMs: typeof event.duration_ms === 'number' ? event.duration_ms : undefined,
          success: event.success !== false,
        },
      };
    }

    case 'final_response':
      return {
        type: 'agent',
        content: String(event.text || event.message || ''),
      };

    case 'error':
      return {
        type: 'error',
        content: String(event.message || 'Agent stream failed'),
      };

    default:
      return null;
  }
}

// ---------------------------------------------------------------------------
// useAgentChat hook
// ---------------------------------------------------------------------------

/** Context the hook needs to drive a stream. Mirrors the design's formal spec. */
export interface UseAgentChatContext {
  /** Currently selected folder; `send` is a no-op when null. */
  folder: Folder | null;
  /** Active session (used as a fallback when `ensureSession` returns null). */
  session: Session | null;
  /** Authenticated user; `send` is a no-op when null. */
  user: User | null;
  /** Prepared table selected for Visualize and Publish. */
  selectedTable?: DataTable | null;
  /** The currently active workspace mode - drives per-mode message isolation. */
  mode: WorkspaceMode;
  /** Lazily creates/returns the folder session before streaming. */
  ensureSession: () => Promise<Session | null>;
  /**
   * Called exactly once per successful stream, after a `completion` event.
   * The orchestrator wires this to refresh folder tables so pipeline gating
   * updates without a page reload (design: "refresh artifacts after completion").
   */
  onCompletion: (mode: WorkspaceMode) => void;
}

/** Public surface returned by {@link useAgentChat}. */
export interface UseAgentChat {
  /** Messages for the currently active mode only. */
  messages: ChatMessage[];
  /** Whether the currently active mode is generating. */
  isGenerating: boolean;
  /** Stream a query in the given mode. No-op when already generating or missing folder/user. */
  send: (query: string, mode: WorkspaceMode) => Promise<void>;
  /** Abort the in-flight request (user-initiated). Does not fire `onCompletion`. */
  stop: () => void;
  /** Clear the current mode's thread and abort any in-flight request for that mode. */
  reset: () => void;
  /** Clear ALL mode threads (used when switching folders). */
  resetAll: () => void;
}

/** Initial empty per-mode message store. */
function emptyModeMessages(): Record<WorkspaceMode, ChatMessage[]> {
  return { sources: [], prepare: [], visualize: [], publish: [] };
}

/** Initial empty per-mode generating flags. */
function emptyModeGenerating(): Record<WorkspaceMode, boolean> {
  return { sources: false, prepare: false, visualize: false, publish: false };
}

/**
 * Shared, mode-isolated chat streaming hook.
 *
 * Maintains separate message arrays and generating flags per mode so that
 * Prepare, Visualize, and Publish each have their own independent chat thread.
 * Switching modes instantly swaps the visible messages without losing history.
 *
 * Streams via {@link streamSse} to the endpoint chosen by {@link streamUrlForMode},
 * mapping every SSE event through the pure {@link mapSseEventToMessage} so the
 * thread schema is identical across modes (design Property 4).
 *
 * Invariants enforced here:
 *   - **At most one `agent` final message per request** - guarded by `hasFinal`
 *     so neither a `final_response` event nor a `completion.final_output`
 *     fallback can append a second final message (design Property 5).
 *   - **`onCompletion(mode)` is called exactly once per successful stream** -
 *     guarded by `completed` so a single `completion` event fires the refresh
 *     once, and aborts/errors never fire it.
 *   - **Abort via `AbortController`** - `stop()` aborts the in-flight request;
 *     the controller is also aborted on unmount.
 *   - **Per-mode isolation** - messages from mode A never appear in mode B's
 *     chat thread.
 */
export function useAgentChat(ctx: UseAgentChatContext): UseAgentChat {
  const [modeMessages, setModeMessages] = useState<Record<WorkspaceMode, ChatMessage[]>>(emptyModeMessages);
  const [modeGenerating, setModeGenerating] = useState<Record<WorkspaceMode, boolean>>(emptyModeGenerating);

  // Keep the latest context in a ref so the returned callbacks stay stable
  // (referentially identical) across renders without going stale.
  const ctxRef = useRef(ctx);
  ctxRef.current = ctx;

  const abortRef = useRef<AbortController | null>(null);
  const generatingRef = useRef(false);
  const hasFinalRef = useRef(false);
  const completedRef = useRef(false);
  const seqRef = useRef(0);
  // Track which mode the current in-flight stream belongs to.
  const activeModeRef = useRef<WorkspaceMode | null>(null);
  // Ids of the in-flight streaming messages so deltas can mutate them in place.
  const answerIdRef = useRef<string | null>(null);
  const thinkingIdRef = useRef<string | null>(null);
  const toolMessageIdsRef = useRef<Map<string, string>>(new Map());

  // Reset all mode threads when the folder changes.
  const prevFolderIdRef = useRef<string | null>(ctx.folder?.id ?? null);
  useEffect(() => {
    const currentFolderId = ctx.folder?.id ?? null;
    if (prevFolderIdRef.current !== currentFolderId) {
      prevFolderIdRef.current = currentFolderId;
      abortRef.current?.abort();
      abortRef.current = null;
      generatingRef.current = false;
      activeModeRef.current = null;
      toolMessageIdsRef.current.clear();
      setModeMessages(emptyModeMessages());
      setModeGenerating(emptyModeGenerating());
    }
  }, [ctx.folder?.id]);

  // Abort any in-flight request when the component using the hook unmounts.
  useEffect(() => () => abortRef.current?.abort(), []);

  const appendMessage = useCallback((targetMode: WorkspaceMode, draft: ChatMessageDraft): string => {
    const id = `msg_${Date.now()}_${seqRef.current++}`;
    setModeMessages((prev) => ({
      ...prev,
      [targetMode]: [...prev[targetMode], { ...draft, id, timestamp: new Date().toISOString() }],
    }));
    return id;
  }, []);

  const updateMessage = useCallback(
    (targetMode: WorkspaceMode, id: string, updater: (message: ChatMessage) => ChatMessage) => {
      setModeMessages((prev) => ({
        ...prev,
        [targetMode]: prev[targetMode].map((message) => (message.id === id ? updater(message) : message)),
      }));
    },
    [],
  );

  const stopGenerating = useCallback((targetMode: WorkspaceMode) => {
    generatingRef.current = false;
    activeModeRef.current = null;
    setModeGenerating((prev) => ({ ...prev, [targetMode]: false }));
  }, []);

  const send = useCallback(
    async (query: string, mode: WorkspaceMode) => {
      const trimmed = query.trim();
      const { folder, user, session, selectedTable, ensureSession, onCompletion } = ctxRef.current;
      if (!trimmed || generatingRef.current || !folder || !user) return;

      // Append the user's message to the correct mode's thread, then reset per-request guards.
      appendMessage(mode, { type: 'user', content: trimmed });
      generatingRef.current = true;
      activeModeRef.current = mode;
      setModeGenerating((prev) => ({ ...prev, [mode]: true }));
      hasFinalRef.current = false;
      completedRef.current = false;
      answerIdRef.current = null;
      thinkingIdRef.current = null;
      toolMessageIdsRef.current.clear();

      const controller = new AbortController();
      abortRef.current = controller;

      const fireCompletion = () => {
        if (completedRef.current) return;
        completedRef.current = true;
        onCompletion(mode);
      };

      try {
        const ensured = await ensureSession();
        const sessionId = ensured?.id || session?.id || '';
        const surface = mode === 'visualize' ? 'dashboard' : mode === 'publish' ? 'report' : 'chat';
        const baseBody: Record<string, unknown> = {
          user_id: user.id,
          session_id: sessionId,
          folder_id: folder.id,
          project_id: folder.projectId,
          query: trimmed,
          surface,
          selected_table_id: selectedTable?.id || null,
          selected_table_name: selectedTable?.name || null,
          selected_tables: selectedTable ? [selectedTable.id] : [],
        };
        const streamBody: Record<string, unknown> = mode === 'publish'
          ? { ...baseBody, mode: 'specific', format: 'pdf' }
          : baseBody;
        await streamSse(
          streamUrlForMode(mode, folder.id),
          streamBody,
          {
            onEvent: (event) => {
              const type = getSseEventType(event);

              // Terminal events (completion/result) finalize the streamed answer,
              // attach token usage, and stop the stream exactly once.
              if (isTerminalSseEvent(event)) {
                const finalOutput = terminalFinalOutput(event);
                const usage = event.token_usage as TokenUsage | undefined;
                const timeTaken = typeof event.time_taken === 'number' ? event.time_taken : undefined;
                if (answerIdRef.current) {
                  const id = answerIdRef.current;
                  updateMessage(mode, id, (m) => ({
                    ...m,
                    content: finalOutput || m.content,
                    metadata: {
                      ...m.metadata,
                      streaming: false,
                      tokenUsage: usage ?? m.metadata?.tokenUsage,
                      timeTaken: timeTaken ?? m.metadata?.timeTaken,
                    },
                  }));
                } else if (finalOutput && !hasFinalRef.current) {
                  hasFinalRef.current = true;
                  appendMessage(mode, { type: 'agent', content: finalOutput, metadata: { tokenUsage: usage, timeTaken } });
                }
                hasFinalRef.current = true;
                answerIdRef.current = null;
                thinkingIdRef.current = null;
                stopGenerating(mode);
                if (event.success !== false && !event.error) fireCompletion();
                return;
              }

              switch (type) {
                case 'tool_call':
                case 'function_request': {
                  const draft = mapSseEventToMessage(event);
                  if (!draft) return;
                  const callId = String(event.call_id || event.id || event.tool_name || 'tool');
                  const messageId = appendMessage(mode, draft);
                  toolMessageIdsRef.current.set(callId, messageId);
                  return;
                }
                case 'tool_response':
                case 'function_response': {
                  const draft = mapSseEventToMessage(event);
                  if (!draft) return;
                  const callId = String(event.call_id || event.id || event.tool_name || 'tool');
                  const messageId = toolMessageIdsRef.current.get(callId);
                  if (messageId) {
                    updateMessage(mode, messageId, (message) => ({
                      ...message,
                      type: 'tool_response',
                      content: draft.content,
                      metadata: {
                        ...message.metadata,
                        ...draft.metadata,
                        toolArgs: message.metadata?.toolArgs,
                      },
                    }));
                    toolMessageIdsRef.current.delete(callId);
                  } else {
                    appendMessage(mode, draft);
                  }
                  return;
                }
                // Agent hand-off marker rendered in the activity trail.
                case 'agent_transition': {
                  appendMessage(mode, {
                    type: 'transition',
                    content: String(event.label || event.to_agent || 'Agent'),
                    metadata: {
                      fromAgent: String(event.from_agent || ''),
                      toAgent: String(event.to_agent || ''),
                      agentLabel: String(event.label || ''),
                    },
                  });
                  return;
                }
                // Collapsible reasoning block, accumulated from streamed deltas.
                case 'thinking_start': {
                  thinkingIdRef.current = appendMessage(mode, {
                    type: 'thinking',
                    content: '',
                    metadata: { agentName: String(event.agent_name || ''), streaming: true },
                  });
                  return;
                }
                case 'thinking_delta': {
                  const delta = String(event.delta || '');
                  if (!delta) return;
                  if (!thinkingIdRef.current) {
                    thinkingIdRef.current = appendMessage(mode, {
                      type: 'thinking',
                      content: '',
                      metadata: { agentName: String(event.agent_name || ''), streaming: true },
                    });
                  }
                  updateMessage(mode, thinkingIdRef.current, (m) => ({ ...m, content: m.content + delta }));
                  return;
                }
                case 'thinking_end': {
                  if (thinkingIdRef.current) {
                    updateMessage(mode, thinkingIdRef.current, (m) => ({
                      ...m,
                      metadata: { ...m.metadata, streaming: false },
                    }));
                  }
                  thinkingIdRef.current = null;
                  return;
                }
                // Token-streamed final answer, appended into a live agent bubble.
                case 'answer_delta': {
                  const delta = String(event.delta || '');
                  if (!delta) return;
                  if (!answerIdRef.current) {
                    answerIdRef.current = appendMessage(mode, { type: 'agent', content: '', metadata: { streaming: true } });
                    hasFinalRef.current = true;
                  }
                  updateMessage(mode, answerIdRef.current, (m) => ({ ...m, content: m.content + delta }));
                  return;
                }
                // Full final text: reconcile the streamed bubble (or create one).
                case 'final_response': {
                  const text = String(event.text || event.message || '');
                  if (answerIdRef.current) {
                    updateMessage(mode, answerIdRef.current, (m) => ({ ...m, content: text || m.content }));
                  } else if (!hasFinalRef.current) {
                    hasFinalRef.current = true;
                    answerIdRef.current = appendMessage(mode, { type: 'agent', content: text });
                  }
                  return;
                }
                default: {
                  const draft = mapSseEventToMessage(event);
                  if (!draft) return;
                  // Guard: at most one `agent` final message per request.
                  if (draft.type === 'agent') {
                    if (hasFinalRef.current) return;
                    hasFinalRef.current = true;
                  }
                  if (draft.type === 'error') stopGenerating(mode);
                  appendMessage(mode, draft);
                }
              }
            },
            onError: (error) => {
              appendMessage(mode, { type: 'error', content: error.message });
              stopGenerating(mode);
            },
          },
          controller.signal,
        );
      } finally {
        stopGenerating(mode);
        if (abortRef.current === controller) abortRef.current = null;
      }
    },
    [appendMessage, stopGenerating, updateMessage],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    const activeMode = activeModeRef.current;
    if (activeMode) stopGenerating(activeMode);
    else {
      generatingRef.current = false;
      setModeGenerating(emptyModeGenerating());
    }
  }, [stopGenerating]);

  const reset = useCallback(() => {
    const currentMode = ctxRef.current.mode;
    if (activeModeRef.current === currentMode) {
      abortRef.current?.abort();
      abortRef.current = null;
      generatingRef.current = false;
      activeModeRef.current = null;
    }
    hasFinalRef.current = false;
    completedRef.current = false;
    answerIdRef.current = null;
    thinkingIdRef.current = null;
    toolMessageIdsRef.current.clear();
    setModeMessages((prev) => ({ ...prev, [currentMode]: [] }));
    setModeGenerating((prev) => ({ ...prev, [currentMode]: false }));
  }, []);

  const resetAll = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    generatingRef.current = false;
    activeModeRef.current = null;
    hasFinalRef.current = false;
    completedRef.current = false;
    answerIdRef.current = null;
    thinkingIdRef.current = null;
    toolMessageIdsRef.current.clear();
    setModeMessages(emptyModeMessages());
    setModeGenerating(emptyModeGenerating());
  }, []);

  // Expose only the current mode's messages and generating state.
  const currentMode = ctx.mode;
  const messages = modeMessages[currentMode];
  const isGenerating = modeGenerating[currentMode];

  return { messages, isGenerating, send, stop, reset, resetAll };
}
