import { useCallback, useEffect, useRef, useState } from 'react';
import { AGENT_URL, streamSse } from '@/lib/api';
import {
  getSseEventType,
  isTerminalSseEvent,
  mapSseEventToMessage,
  terminalFinalOutput,
} from '@/hooks/useAgentChat';
import type { ChatMessage, DataTable, Folder, Session, User } from '@/types';

interface CanvasAgentContext {
  folder: Folder | null;
  session: Session | null;
  user: User | null;
  selectedTable?: DataTable | null;
  documentId: string | null;
  ensureSession: () => Promise<Session | null>;
  onVisualArtifact: (documentId?: string) => void;
}

function visualArtifactId(event: Record<string, unknown>): string | undefined {
  const raw = event.artifact ?? event.data ?? event.response;
  const payload =
    raw && typeof raw === 'object' && !Array.isArray(raw)
      ? (raw as Record<string, unknown>)
      : {};
  const nested =
    payload.result && typeof payload.result === 'object' && !Array.isArray(payload.result)
      ? (payload.result as Record<string, unknown>)
      : {};
  const artifactType = String(
    event.artifact_type || payload.artifact_type || payload.type || nested.artifact_type || '',
  );
  const eventType = getSseEventType(event);
  if (
    artifactType !== 'visual_document' &&
    artifactType !== 'visual_patch' &&
    !eventType.startsWith('visual_') &&
    !String(event.tool_name || '').startsWith('canvas_')
  ) {
    return undefined;
  }
  const id =
    event.document_id ||
    event.visual_document_id ||
    payload.document_id ||
    payload.visual_document_id ||
    payload.id ||
    nested.document_id ||
    nested.visual_document_id;
  return id ? String(id) : '';
}

export function useCanvasAgent({
  folder,
  session,
  user,
  selectedTable,
  documentId,
  ensureSession,
  onVisualArtifact,
}: CanvasAgentContext) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const sequenceRef = useRef(0);
  const answerIdRef = useRef<string | null>(null);
  const contextRef = useRef({
    folder,
    session,
    user,
    selectedTable,
    documentId,
    ensureSession,
    onVisualArtifact,
  });
  contextRef.current = {
    folder,
    session,
    user,
    selectedTable,
    documentId,
    ensureSession,
    onVisualArtifact,
  };

  const append = useCallback((draft: Omit<ChatMessage, 'id' | 'timestamp'>) => {
    const id = `canvas_msg_${Date.now()}_${sequenceRef.current++}`;
    setMessages((current) => [
      ...current,
      { ...draft, id, timestamp: new Date().toISOString() },
    ]);
    return id;
  }, []);

  const update = useCallback((id: string, updater: (message: ChatMessage) => ChatMessage) => {
    setMessages((current) =>
      current.map((message) => (message.id === id ? updater(message) : message)),
    );
  }, []);

  useEffect(() => {
    abortRef.current?.abort();
    setMessages([]);
    setIsGenerating(false);
    answerIdRef.current = null;
  }, [folder?.id, documentId]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const send = useCallback(
    async (query: string) => {
      const trimmed = query.trim();
      const context = contextRef.current;
      if (!trimmed || isGenerating || !context.folder || !context.user || !context.documentId) return;
      append({ type: 'user', content: trimmed });
      setIsGenerating(true);
      answerIdRef.current = null;
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        const ensured = await context.ensureSession();
        const activeSession = ensured || context.session;
        await streamSse(
          `${AGENT_URL}/agent/canvas/stream`,
          {
            user_id: context.user.id,
            session_id: activeSession?.id || '',
            folder_id: context.folder.id,
            project_id: context.folder.projectId,
            query: trimmed,
            surface: 'canvas',
            selected_table_id: context.selectedTable?.id || null,
            selected_table_name: context.selectedTable?.name || null,
            selected_tables: context.selectedTable ? [context.selectedTable.id] : [],
            visual_document_id: context.documentId,
          },
          {
            onEvent: (event) => {
              const type = getSseEventType(event);
              const artifactDocumentId = visualArtifactId(event);
              if (artifactDocumentId !== undefined) {
                contextRef.current.onVisualArtifact(artifactDocumentId || undefined);
              }
              if (isTerminalSseEvent(event)) {
                const final = terminalFinalOutput(event);
                if (answerIdRef.current) {
                  update(answerIdRef.current, (message) => ({
                    ...message,
                    content: final || message.content,
                    metadata: { ...message.metadata, streaming: false },
                  }));
                } else if (final) {
                  append({ type: 'agent', content: final });
                }
                contextRef.current.onVisualArtifact(contextRef.current.documentId || undefined);
                setIsGenerating(false);
                answerIdRef.current = null;
                return;
              }
              if (type === 'answer_delta') {
                const delta = String(event.delta || '');
                if (!delta) return;
                if (!answerIdRef.current) {
                  answerIdRef.current = append({
                    type: 'agent',
                    content: '',
                    metadata: { streaming: true },
                  });
                }
                update(answerIdRef.current, (message) => ({
                  ...message,
                  content: message.content + delta,
                }));
                return;
              }
              if (type === 'final_response') {
                const text = String(event.text || event.message || '');
                if (answerIdRef.current) {
                  update(answerIdRef.current, (message) => ({
                    ...message,
                    content: text || message.content,
                    metadata: { ...message.metadata, streaming: false },
                  }));
                } else if (text) {
                  answerIdRef.current = append({ type: 'agent', content: text });
                }
                return;
              }
              const draft = mapSseEventToMessage(event);
              if (draft) append(draft);
            },
            onError: (streamError) => {
              if (streamError.name !== 'AbortError') {
                append({ type: 'error', content: streamError.message });
              }
              setIsGenerating(false);
            },
          },
          controller.signal,
        );
      } catch (streamError) {
        if (streamError instanceof Error && streamError.name !== 'AbortError') {
          append({ type: 'error', content: streamError.message });
        }
      } finally {
        if (abortRef.current === controller) abortRef.current = null;
        setIsGenerating(false);
      }
    },
    [append, isGenerating, update],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setIsGenerating(false);
  }, []);

  return { messages, isGenerating, send, stop, clear: () => setMessages([]) };
}
