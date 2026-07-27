import { useCallback, useEffect, useRef, useState } from 'react';
import type { VisualDocument, VisualElement, VisualOp } from '@/types/visualDocument.generated';
import {
  createVisualDocument,
  deleteVisualDocument,
  getVisualDocument,
  getVisualDocumentOutline,
  getVisualDocumentReadability,
  layoutVisualDocument,
  listVisualDocuments,
  redoVisualDocument,
  undoVisualDocument,
  commitVisualDocument,
  type CanvasLayoutAlgorithm,
  type CanvasOutlineResponse,
  type CanvasReadability,
  type VisualDocumentListItem,
} from '@/lib/visualDocuments';

interface UseVisualDocumentContext {
  folderId: string | null;
  projectId: string | null;
  sessionId?: string | null;
  sourceTableIds?: string[];
  requestedDocumentId?: string | null;
}

function optimisticDocument(document: VisualDocument, ops: VisualOp[]): VisualDocument {
  let elements = [...(document.elements || [])];
  let viewport = { ...(document.viewport || {}) };
  let metadata = { ...document.metadata };

  for (const op of ops) {
    if (op.op === 'remove_element') {
      elements = elements.filter((element) => element.id !== op.element_id);
    } else if (op.op === 'resize_element') {
      elements = elements.map((element) =>
        element.id === op.element_id && 'rect' in element
          ? ({ ...element, rect: op.rect } as VisualElement)
          : element,
      );
    } else if (op.op === 'move_elements') {
      const ids = new Set(op.element_ids);
      elements = elements.map((element) =>
        ids.has(element.id) && 'rect' in element
          ? ({
              ...element,
              rect: {
                ...element.rect,
                x: element.rect.x + (op.dx || 0),
                y: element.rect.y + (op.dy || 0),
              },
            } as VisualElement)
          : element,
      );
    } else if (op.op === 'set_selection') {
      viewport = { ...viewport, selected_ids: op.element_ids || [] };
    } else if (op.op === 'set_title') {
      metadata = { ...metadata, title: op.title };
    } else if (op.op === 'update_element') {
      elements = elements.map((element) =>
        element.id === op.element_id
          ? ({ ...element, ...op.patch, id: element.id } as VisualElement)
          : element,
      );
    }
  }
  return { ...document, metadata, viewport, elements };
}

export function useVisualDocument({
  folderId,
  projectId,
  sessionId,
  sourceTableIds = [],
  requestedDocumentId,
}: UseVisualDocumentContext) {
  const [documents, setDocuments] = useState<VisualDocumentListItem[]>([]);
  const [document, setDocument] = useState<VisualDocument | null>(null);
  const [outline, setOutline] = useState<CanvasOutlineResponse | null>(null);
  const [readability, setReadability] = useState<CanvasReadability | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const documentRef = useRef<VisualDocument | null>(null);
  const mutationQueueRef = useRef<Promise<unknown>>(Promise.resolve());

  useEffect(() => {
    documentRef.current = document;
  }, [document]);

  const loadDetails = useCallback(async (documentId: string, quiet = false) => {
    if (!quiet) setIsLoading(true);
    try {
      const [result, outlineResult, readabilityResult] = await Promise.all([
        getVisualDocument(documentId),
        getVisualDocumentOutline(documentId),
        getVisualDocumentReadability(documentId),
      ]);
      documentRef.current = result.document;
      setDocument(result.document);
      setOutline(outlineResult);
      setReadability(readabilityResult);
      setError(null);
      return result.document;
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Unable to load this canvas.');
      return null;
    } finally {
      if (!quiet) setIsLoading(false);
    }
  }, []);

  const refreshList = useCallback(async () => {
    if (!folderId) {
      setDocuments([]);
      return [];
    }
    const result = await listVisualDocuments(folderId);
    setDocuments(result.documents);
    return result.documents;
  }, [folderId]);

  useEffect(() => {
    let cancelled = false;
    setDocument(null);
    setOutline(null);
    setReadability(null);
    setError(null);
    if (!folderId) {
      setDocuments([]);
      return;
    }
    setIsLoading(true);
    void listVisualDocuments(folderId)
      .then(async ({ documents: nextDocuments }) => {
        if (cancelled) return;
        setDocuments(nextDocuments);
        const target =
          nextDocuments.find((item) => item.id === requestedDocumentId)?.id ||
          nextDocuments[0]?.id;
        if (target) await loadDetails(target, true);
      })
      .catch((loadError) => {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : 'Unable to list canvases.');
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [folderId, loadDetails, requestedDocumentId]);

  const create = useCallback(
    async (title = 'Untitled canvas') => {
      if (!folderId || !projectId) throw new Error('Select a project folder before creating a canvas.');
      setIsSaving(true);
      try {
        const result = await createVisualDocument({
          folder_id: folderId,
          project_id: projectId,
          session_id: sessionId || null,
          source_table_ids: sourceTableIds,
          title,
        });
        documentRef.current = result.document;
        setDocument(result.document);
        setError(null);
        await refreshList();
        await loadDetails(result.document.metadata.id, true);
        return result.document;
      } finally {
        setIsSaving(false);
      }
    },
    [folderId, loadDetails, projectId, refreshList, sessionId, sourceTableIds],
  );

  const select = useCallback((documentId: string) => loadDetails(documentId), [loadDetails]);

  const commit = useCallback(
    (ops: VisualOp[], label: string) => {
      if (!ops.length) return Promise.resolve(documentRef.current);
      const task = mutationQueueRef.current
        .catch(() => undefined)
        .then(async () => {
          const current = documentRef.current;
          if (!current) throw new Error('Open a canvas before editing it.');
          const documentId = current.metadata.id;
          const optimistic = optimisticDocument(current, ops);
          documentRef.current = optimistic;
          setDocument(optimistic);
          setIsSaving(true);
          try {
            const result = await commitVisualDocument(documentId, {
              ops,
              base_revision: current.metadata.revision || 0,
              label,
            });
            documentRef.current = result.document;
            setDocument(result.document);
            setError(null);
            void refreshList();
            void Promise.all([
              getVisualDocumentOutline(documentId).then(setOutline),
              getVisualDocumentReadability(documentId).then(setReadability),
            ]);
            return result.document;
          } catch (commitError) {
            await loadDetails(documentId, true);
            setError(
              commitError instanceof Error
                ? `${commitError.message}. The latest canvas was reloaded so no work is silently overwritten.`
                : 'The edit conflicted with a newer revision.',
            );
            throw commitError;
          } finally {
            setIsSaving(false);
          }
        });
      mutationQueueRef.current = task;
      return task;
    },
    [loadDetails, refreshList],
  );

  const runServerMutation = useCallback(
    (mutate: (documentId: string, revision: number) => Promise<{ document: VisualDocument }>) => {
      const task = mutationQueueRef.current
        .catch(() => undefined)
        .then(async () => {
          const current = documentRef.current;
          if (!current) throw new Error('Open a canvas first.');
          setIsSaving(true);
          try {
            const result = await mutate(current.metadata.id, current.metadata.revision || 0);
            documentRef.current = result.document;
            setDocument(result.document);
            setError(null);
            await refreshList();
            void loadDetails(result.document.metadata.id, true);
            return result.document;
          } catch (mutationError) {
            await loadDetails(current.metadata.id, true);
            setError(mutationError instanceof Error ? mutationError.message : 'Canvas update failed.');
            throw mutationError;
          } finally {
            setIsSaving(false);
          }
        });
      mutationQueueRef.current = task;
      return task;
    },
    [loadDetails, refreshList],
  );

  const undo = useCallback(
    () => runServerMutation((documentId) => undoVisualDocument(documentId)),
    [runServerMutation],
  );
  const redo = useCallback(
    () => runServerMutation((documentId) => redoVisualDocument(documentId)),
    [runServerMutation],
  );
  const layout = useCallback(
    (algorithm: CanvasLayoutAlgorithm, elementIds?: string[]) =>
      runServerMutation((documentId, revision) =>
        layoutVisualDocument(documentId, {
          algorithm,
          direction: algorithm === 'timeline' ? 'right' : 'right',
          element_ids: elementIds?.length ? elementIds : undefined,
          base_revision: revision,
        }),
      ),
    [runServerMutation],
  );

  const removeCurrent = useCallback(async () => {
    const current = documentRef.current;
    if (!current) return;
    setIsSaving(true);
    try {
      await deleteVisualDocument(current.metadata.id);
      const remaining = await refreshList();
      const nextId = remaining.find((item) => item.id !== current.metadata.id)?.id;
      if (nextId) await loadDetails(nextId);
      else {
        documentRef.current = null;
        setDocument(null);
        setOutline(null);
        setReadability(null);
      }
    } finally {
      setIsSaving(false);
    }
  }, [loadDetails, refreshList]);

  return {
    documents,
    document,
    outline,
    readability,
    isLoading,
    isSaving,
    error,
    create,
    select,
    refresh: () => (documentRef.current ? loadDetails(documentRef.current.metadata.id, true) : Promise.resolve(null)),
    commit,
    undo,
    redo,
    layout,
    removeCurrent,
    canUndo: Boolean(document?.history?.length),
    canRedo: Boolean(document?.redo_stack?.length),
  };
}
