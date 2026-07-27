// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useAppState } from '@/hooks/useAppState';
import { useAuth } from '@/hooks/useAuth';
import { useVisualDocument } from '@/hooks/useVisualDocument';
import { useCanvasAgent } from '@/hooks/useCanvasAgent';
import { CanvasStudio } from './CanvasStudio';

const { observedProps } = vi.hoisted(() => ({ observedProps: [] as Array<Record<string, unknown>> }));

vi.mock('@/hooks/useAppState', () => ({ useAppState: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: vi.fn() }));
vi.mock('@/hooks/useVisualDocument', () => ({ useVisualDocument: vi.fn() }));
vi.mock('@/hooks/useCanvasAgent', () => ({ useCanvasAgent: vi.fn() }));
vi.mock('./VisualCanvas', () => ({
  VisualCanvas: (props: Record<string, unknown>) => {
    observedProps.push(props);
    return (
      <button
        type="button"
        onClick={() => (props.onSelectionChange as (ids: string[]) => void)(['node-1'])}
      >
        Select canvas node
      </button>
    );
  },
}));

describe('CanvasStudio chat navigation stability', () => {
  beforeEach(() => {
    observedProps.length = 0;
    vi.mocked(useAppState).mockReturnValue({
      selectedFolder: { id: 'folder-1', projectId: 'project-1', name: 'Folder' },
      selectedProject: { id: 'project-1', name: 'Project' },
      selectedTable: null,
      activeSession: null,
      ensureSession: vi.fn(),
    } as never);
    vi.mocked(useAuth).mockReturnValue({ user: { id: 'user-1' } } as never);
    vi.mocked(useVisualDocument).mockReturnValue({
      documents: [{ id: 'document-1', title: 'Canvas' }],
      document: {
        metadata: { id: 'document-1', title: 'Canvas', revision: 1 },
        viewport: {},
        layers: [{ id: 'layer-1', name: 'Main', visible: true }],
        elements: [],
        history: [],
        redo_stack: [],
      },
      outline: { outline: [] },
      readability: null,
      isLoading: false,
      isSaving: false,
      error: null,
      create: vi.fn(),
      select: vi.fn(),
      refresh: vi.fn(),
      commit: vi.fn(),
      undo: vi.fn(),
      redo: vi.fn(),
      layout: vi.fn(),
      removeCurrent: vi.fn(),
      canUndo: false,
      canRedo: false,
    } as never);
    vi.mocked(useCanvasAgent).mockReturnValue({
      messages: [],
      isGenerating: false,
      send: vi.fn(),
      stop: vi.fn(),
      clear: vi.fn(),
    });
  });

  it('keeps React Flow callbacks stable when selection sync rerenders the canvas', async () => {
    render(
      <MemoryRouter initialEntries={['/app/canvas?folderId=folder-1&documentId=document-1']}>
        <CanvasStudio />
      </MemoryRouter>,
    );

    const firstProps = observedProps.at(-1)!;
    fireEvent.click(screen.getByRole('button', { name: 'Select canvas node' }));

    await waitFor(() => expect(observedProps.length).toBeGreaterThan(1));
    const latestProps = observedProps.at(-1)!;
    expect(latestProps.onSelectionChange).toBe(firstProps.onSelectionChange);
    expect(latestProps.onElementRectChange).toBe(firstProps.onElementRectChange);
  });
});