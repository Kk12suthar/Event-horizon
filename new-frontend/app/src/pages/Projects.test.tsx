// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const mocks = vi.hoisted(() => {
  const project = {
    id: 'project-1',
    name: 'Operations project',
    description: 'Operational data',
    status: 'Active',
    createdAt: '2026-07-27',
    createdBy: 'user-1',
  };
  const folder = {
    id: 'folder-1',
    projectId: 'project-1',
    name: 'Orders folder',
    description: 'Order source files',
    status: 'Active',
    createdAt: '2026-07-27',
    createdBy: 'user-1',
    entities: { tables: {}, files: {} },
  };
  return {
    project,
    folder,
    upload: vi.fn(async () => undefined),
    selectFolder: vi.fn(),
    appState: {
      projectList: [project],
      folderList: [folder],
      selectedProject: project,
      selectedFolder: folder,
      activeSession: null,
      selectProject: vi.fn(),
      selectFolder: vi.fn(),
      createProject: vi.fn(),
      updateProject: vi.fn(),
      deleteProject: vi.fn(),
      createFolder: vi.fn(),
      updateFolder: vi.fn(),
      deleteFolder: vi.fn(),
      ensureSession: vi.fn(async () => null),
      loadTablesForFolder: vi.fn(async () => []),
      addFiles: vi.fn(),
      refreshWorkspace: vi.fn(async () => undefined),
    },
  };
});

mocks.appState.selectFolder = mocks.selectFolder;

vi.mock('@/hooks/useAppState', () => ({ useAppState: () => mocks.appState }));
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({
    isAdmin: false,
    isAnalyst: true,
    user: { id: 'user-1', name: 'Analyst', email: 'analyst@example.com', role: 'Analyst' },
  }),
}));
vi.mock('@/hooks/useFolderUpload', async () => {
  const actual = await vi.importActual<typeof import('@/hooks/useFolderUpload')>('@/hooks/useFolderUpload');
  return {
    ...actual,
    useFolderUpload: () => ({ upload: mocks.upload, progress: 0, stage: 'idle', error: null }),
  };
});
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return { ...actual, fetchAllFolderTables: vi.fn(async () => ({ tables: {}, table_types: {} })) };
});
vi.mock('@xyflow/react', async () => {
  const React = await vi.importActual<typeof import('react')>('react');
  return {
    Background: () => null,
    Controls: () => null,
    Handle: () => null,
    MarkerType: { ArrowClosed: 'arrowclosed' },
    Position: { Left: 'left', Right: 'right' },
    ReactFlow: ({ nodes, onNodeClick, children }: { nodes: Array<{ id: string; data: { folderId?: string; label: string } }>; onNodeClick: (event: unknown, node: unknown) => void; children?: React.ReactNode }) =>
      React.createElement(
        'div',
        { 'data-testid': 'project-canvas' },
        ...nodes.filter((node) => node.data.folderId).map((node) =>
          React.createElement('button', { key: node.id, type: 'button', onClick: () => onNodeClick({}, node) }, node.data.label),
        ),
        children,
      ),
  };
});

import { Projects } from './Projects';

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('Projects canvas-only data workspace', () => {
  it('uses compact project and folder controls without a list toggle', () => {
    render(<MemoryRouter><Projects /></MemoryRouter>);

    expect(screen.queryByRole('button', { name: 'List view' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Canvas view' })).toBeNull();
    expect(screen.getByRole('button', { name: 'New project' }).className).toContain('h-7 w-7');
    expect(screen.getByRole('button', { name: 'New folder' }).className).toContain('h-7 w-7');
    expect(screen.getByTestId('project-canvas')).toBeTruthy();
  });

  it('opens the nearby upload panel when a folder node is clicked', () => {
    render(<MemoryRouter><Projects /></MemoryRouter>);

    expect(screen.queryByLabelText('Upload files to Orders folder')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Orders folder' }));

    expect(mocks.selectFolder).toHaveBeenCalledWith(mocks.folder);
    expect(screen.getByLabelText('Upload files to Orders folder')).toBeTruthy();
    expect(screen.getByText('Drop files or browse')).toBeTruthy();
  });
});