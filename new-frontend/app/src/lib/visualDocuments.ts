import { apiDelete, apiGet, apiPost } from '@/lib/api';
import type { Commit, Rect, VisualDocument, VisualOp } from '@/types/visualDocument.generated';

export interface VisualDocumentListItem {
  id: string;
  title: string;
  revision: number;
  updated_at: string;
  created_by?: string | null;
  element_count: number;
  project_id?: string;
  folder_id?: string;
}

interface DocumentResponse { document: VisualDocument; }
interface DocumentListResponse { documents: VisualDocumentListItem[]; }

export interface CommitResponse extends DocumentResponse { commit: Commit | null; }
export interface CanvasReadability {
  score?: number;
  overlaps?: Array<Record<string, unknown>>;
  crowding?: Array<Record<string, unknown>>;
  out_of_bounds?: string[];
  missing_labels?: string[];
  [key: string]: unknown;
}
export interface CanvasOutlineItem {
  id?: string;
  type?: string;
  label?: string;
  layer_id?: string;
  hidden?: boolean;
  [key: string]: unknown;
}
export interface CanvasOutlineResponse { outline: CanvasOutlineItem[]; summary: Record<string, unknown>; }

export type CanvasLayoutAlgorithm = 'layered' | 'tree' | 'grid' | 'timeline' | 'radial';
export type CanvasLayoutDirection = 'right' | 'down' | 'left' | 'up';

export interface CreateVisualDocumentInput {
  project_id: string;
  folder_id: string;
  title: string;
  session_id?: string | null;
  source_table_ids?: string[];
}
export interface CommitVisualDocumentInput { ops: VisualOp[]; base_revision: number; label: string; }
export interface LayoutVisualDocumentInput {
  algorithm: CanvasLayoutAlgorithm;
  direction?: CanvasLayoutDirection;
  node_spacing?: number;
  rank_spacing?: number;
  columns?: number;
  element_ids?: string[];
  base_revision: number;
}

export const listVisualDocuments = (folderId: string) =>
  apiGet<DocumentListResponse>('/visual-documents', { folder_id: folderId });
export const createVisualDocument = (input: CreateVisualDocumentInput) =>
  apiPost<DocumentResponse>('/visual-documents', input as unknown as Record<string, unknown>);
export const getVisualDocument = (documentId: string) =>
  apiGet<DocumentResponse>(`/visual-documents/${encodeURIComponent(documentId)}`);
export const commitVisualDocument = (documentId: string, input: CommitVisualDocumentInput) =>
  apiPost<CommitResponse>(`/visual-documents/${encodeURIComponent(documentId)}/commit`, input as unknown as Record<string, unknown>);
export const undoVisualDocument = (documentId: string) =>
  apiPost<CommitResponse>(`/visual-documents/${encodeURIComponent(documentId)}/undo`, {});
export const redoVisualDocument = (documentId: string) =>
  apiPost<CommitResponse>(`/visual-documents/${encodeURIComponent(documentId)}/redo`, {});
export const layoutVisualDocument = (documentId: string, input: LayoutVisualDocumentInput) =>
  apiPost<CommitResponse>(`/visual-documents/${encodeURIComponent(documentId)}/layout`, input as unknown as Record<string, unknown>);
export const alignVisualDocument = (
  documentId: string,
  input: { element_ids: string[]; axis: 'left' | 'right' | 'top' | 'bottom' | 'center-x' | 'center-y'; base_revision: number },
) => apiPost<CommitResponse>(`/visual-documents/${encodeURIComponent(documentId)}/align`, input);
export const getVisualDocumentReadability = (documentId: string) =>
  apiGet<CanvasReadability>(`/visual-documents/${encodeURIComponent(documentId)}/readability`);
export const getVisualDocumentOutline = (documentId: string) =>
  apiGet<CanvasOutlineResponse>(`/visual-documents/${encodeURIComponent(documentId)}/outline`);
export const deleteVisualDocument = (documentId: string) =>
  apiDelete<{ message: string }>(`/visual-documents/${encodeURIComponent(documentId)}`, null);

export const resizeElementOp = (elementId: string, rect: Rect): VisualOp => ({
  op: 'resize_element', element_id: elementId, rect,
});
export const removeElementOp = (elementId: string): VisualOp => ({
  op: 'remove_element', element_id: elementId,
});
export const setSelectionOp = (elementIds: string[]): VisualOp => ({
  op: 'set_selection', element_ids: elementIds,
});
