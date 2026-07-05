import { useCallback, useEffect, useRef, useState } from 'react';
import { streamSse } from '../lib/api';
import { streamUrlForMode } from './usePipelineStage';
import type { ChatMessage, Folder, MessageType, Session, TokenUsage, User, WorkspaceMode } from '../types';

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
    case 'artifact':
      return null;

    case 'tool_call':
    case 'function_request': {
      const toolName = String(event.tool_name || 'Tool');
      return {
        type: 'tool_call',
        content: `${toolName} requested`,
        metadata: {
          toolName,
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
          toolStatus: 'complete',
          toolResponse: response,
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
  messages: ChatMessage[];
  isGenerating: boolean;
  /** Stream a query in the given mode. No-op when already generating or missing folder/user. */
  send: (query: string, mode: WorkspaceMode) => Promise<void>;
  /** Abort the in-flight request (user-initiated). Does not fire `onCompletion`. */
  stop: () => void;
  /** Clear the thread and abort any in-flight request. */
  reset: () => void;
}

/**
 * Shared, mode-independent chat streaming hook.
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
 */
export function useAgentChat(ctx: UseAgentChatContext): UseAgentChat {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isGenerating, setIsGenerating] = useState(false);

  // Keep the latest context in a ref so the returned callbacks stay stable
  // (referentially identical) across renders without going stale.
  const ctxRef = useRef(ctx);
  ctxRef.current = ctx;

  const abortRef = useRef<AbortController | null>(null);
  const generatingRef = useRef(false);
  const hasFinalRef = useRef(false);
  const completedRef = useRef(false);
  const seqRef = useRef(0);
  // Ids of the in-flight streaming messages so deltas can mutate them in place.
  const answerIdRef = useRef<string | null>(null);
  const thinkingIdRef = useRef<string | null>(null);

  // Abort any in-flight request when the component using the hook unmounts.
  useEffect(() => () => abortRef.current?.abort(), []);

  const appendMessage = useCallback((draft: ChatMessageDraft): string => {
    const id = `msg_${Date.now()}_${seqRef.current++}`;
    setMessages((prev) => [
      ...prev,
      { ...draft, id, timestamp: new Date().toISOString() },
    ]);
    return id;
  }, []);

  const updateMessage = useCallback(
    (id: string, updater: (message: ChatMessage) => ChatMessage) => {
      setMessages((prev) => prev.map((message) => (message.id === id ? updater(message) : message)));
    },
    [],
  );

  // Backwards-compatible append (ignores the returned id).
  const pushDraft = useCallback(
    (draft: ChatMessageDraft) => {
      appendMessage(draft);
    },
    [appendMessage],
  );

  const stopGenerating = useCallback(() => {
    generatingRef.current = false;
    setIsGenerating(false);
  }, []);

  const send = useCallback(
    async (query: string, mode: WorkspaceMode) => {
      const trimmed = query.trim();
      const { folder, user, session, ensureSession, onCompletion } = ctxRef.current;
      if (!trimmed || generatingRef.current || !folder || !user) return;

      // Append the user's message immediately, then reset per-request guards.
      pushDraft({ type: 'user', content: trimmed });
      generatingRef.current = true;
      setIsGenerating(true);
      hasFinalRef.current = false;
      completedRef.current = false;
      answerIdRef.current = null;
      thinkingIdRef.current = null;

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
        const streamBody: Record<string, unknown> = mode === 'publish'
          ? {
              user_id: user.id,
              session_id: sessionId,
              project_id: folder.projectId,
              query: trimmed,
              mode: 'specific',
              format: 'pdf',
              selected_tables: [],
            }
          : {
              user_id: user.id,
              session_id: sessionId,
              folder_id: folder.id,
              project_id: folder.projectId,
              query: trimmed,
            };
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
                  updateMessage(id, (m) => ({
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
                  appendMessage({ type: 'agent', content: finalOutput, metadata: { tokenUsage: usage, timeTaken } });
                }
                hasFinalRef.current = true;
                answerIdRef.current = null;
                thinkingIdRef.current = null;
                stopGenerating();
                fireCompletion();
                return;
              }

              switch (type) {
                // Agent hand-off marker rendered in the activity trail.
                case 'agent_transition': {
                  appendMessage({
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
                  thinkingIdRef.current = appendMessage({
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
                    thinkingIdRef.current = appendMessage({
                      type: 'thinking',
                      content: '',
                      metadata: { agentName: String(event.agent_name || ''), streaming: true },
                    });
                  }
                  updateMessage(thinkingIdRef.current, (m) => ({ ...m, content: m.content + delta }));
                  return;
                }
                case 'thinking_end': {
                  if (thinkingIdRef.current) {
                    updateMessage(thinkingIdRef.current, (m) => ({
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
                    answerIdRef.current = appendMessage({ type: 'agent', content: '', metadata: { streaming: true } });
                    hasFinalRef.current = true;
                  }
                  updateMessage(answerIdRef.current, (m) => ({ ...m, content: m.content + delta }));
                  return;
                }
                // Full final text: reconcile the streamed bubble (or create one).
                case 'final_response': {
                  const text = String(event.text || event.message || '');
                  if (answerIdRef.current) {
                    updateMessage(answerIdRef.current, (m) => ({ ...m, content: text || m.content }));
                  } else if (!hasFinalRef.current) {
                    hasFinalRef.current = true;
                    answerIdRef.current = appendMessage({ type: 'agent', content: text });
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
                  if (draft.type === 'error') stopGenerating();
                  appendMessage(draft);
                }
              }
            },
            onError: (error) => {
              pushDraft({ type: 'error', content: error.message });
              stopGenerating();
            },
          },
          controller.signal,
        );
      } finally {
        stopGenerating();
        if (abortRef.current === controller) abortRef.current = null;
      }
    },
    [appendMessage, pushDraft, stopGenerating, updateMessage],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    stopGenerating();
  }, [stopGenerating]);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    stopGenerating();
    hasFinalRef.current = false;
    completedRef.current = false;
    answerIdRef.current = null;
    thinkingIdRef.current = null;
    setMessages([]);
  }, [stopGenerating]);

  return { messages, isGenerating, send, stop, reset };
}
