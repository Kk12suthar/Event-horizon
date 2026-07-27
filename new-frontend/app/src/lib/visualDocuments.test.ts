import { beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiDelete: vi.fn(),
}));

vi.mock('@/lib/api', () => api);

import {
  commitVisualDocument,
  createVisualDocument,
  listVisualDocuments,
  removeElementOp,
  resizeElementOp,
} from './visualDocuments';

describe('visual document API client', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.apiGet.mockResolvedValue({ documents: [] });
    api.apiPost.mockResolvedValue({ document: {}, commit: null });
  });

  it('scopes document listings to the active folder', async () => {
    await listVisualDocuments('folder-1');

    expect(api.apiGet).toHaveBeenCalledWith('/visual-documents', {
      folder_id: 'folder-1',
    });
  });

  it('sends trusted project and folder context when creating a canvas', async () => {
    const input = {
      project_id: 'project-1',
      folder_id: 'folder-1',
      title: 'Order flow',
      session_id: 'session-1',
      source_table_ids: ['table-1'],
    };

    await createVisualDocument(input);

    expect(api.apiPost).toHaveBeenCalledWith('/visual-documents', input);
  });

  it('encodes document ids and preserves optimistic revision checks', async () => {
    const input = {
      ops: [removeElementOp('node-1')],
      base_revision: 7,
      label: 'delete selection',
    };

    await commitVisualDocument('canvas/one', input);

    expect(api.apiPost).toHaveBeenCalledWith(
      '/visual-documents/canvas%2Fone/commit',
      input,
    );
  });

  it('creates canonical resize operations for drag and resize commits', () => {
    expect(resizeElementOp('node-1', { x: 10, y: 20, w: 240, h: 120 })).toEqual({
      op: 'resize_element',
      element_id: 'node-1',
      rect: { x: 10, y: 20, w: 240, h: 120 },
    });
  });
});
