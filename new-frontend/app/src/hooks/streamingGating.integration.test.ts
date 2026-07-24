// @vitest-environment jsdom
//
// Integration tests for streaming + pipeline gating (task 10.3).
//
// These exercise the REAL hooks (useAgentChat, usePipelineStage, useFolderUpload)
// wired together the way WorkspaceView wires them, with only the transports
// mocked: `streamSse` (SSE) and the upload `WebSocket`. They assert the
// observable, end-to-end behavior rather than re-implementing hook internals:
//
//   - A scripted SSE sequence renders the activity trail (activity + tool
//     call/response) plus exactly ONE final agent message, and a `completion`
//     that adds an `agent_created` table unlocks Visualize + Publish without a
//     reload (Requirements 2.2, 2.3, 3.8).
//   - A scripted upload WebSocket streams progress and produces tables, flipping
//     gating from sources-only to prepare-enabled (Requirements 6.4, 6.5).

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useState } from 'react';
import { useAgentChat } from './useAgentChat';
import { usePipelineStage } from './usePipelineStage';
import { useFolderUpload } from './useFolderUpload';
import type {
  ChatMessage,
  DataTable,
  Folder,
  Session,
  User,
  WorkspaceMode,
} from '../types';

// ---------------------------------------------------------------------------
// Transport mocks (the only things stubbed - hook logic is exercised for real)
// ---------------------------------------------------------------------------

/** Scripted SSE events the mocked `streamSse` will replay into `onEvent`. */
let scriptedEvents: Record<string, unknown>[] = [];

const streamSseMock = vi.fn(
  async (
    _url: string,
    _body: Record<string, unknown>,
    handlers: { onEvent: (e: Record<string, unknown>) => void; onError?: (e: Error) => void },
  ) => {
    for (const event of scriptedEvents) handlers.onEvent(event);
  },
);

let idCounter = 0;

vi.mock('../lib/api', () => ({
  streamSse: (...args: unknown[]) =>
    (streamSseMock as unknown as (...a: unknown[]) => Promise<void>)(...args),
  getAgentStreamUrl: (surface: 'transform' | 'dashboard') =>
    surface === 'dashboard'
      ? 'http://test/agent/dashboard/stream'
      : 'http://test/agent/chat/stream',
  getUploadWebSocketUrl: () => 'ws://test/upload',
  createId: () => `id_${idCounter++}`,
  getUploadAccessToken: () => 'signed-test-token',
  fetchUploadQuota: vi.fn(async () => ({
    limits: {
      storage_capacity_bytes: 60 * 1024 ** 3,
      storage_reserve_bytes: 15 * 1024 ** 3,
      planned_users: 50,
      storage_expansion_factor: 5,
      max_files: 3,
      max_file_bytes: 60 * 1024 ** 2,
      max_total_bytes: 180 * 1024 ** 2,
    },
    usage: { file_count: 0, total_bytes: 0 },
    remaining: { file_count: 3, total_bytes: 180 * 1024 ** 2 },
  })),
  createFileRecord: vi.fn(async () => ({})),
  updateFileStatus: vi.fn(async () => ({})),
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const user: User = {
  id: 'user-1',
  name: 'Ada',
  email: 'ada@example.com',
  role: 'Analyst',
  status: 'active',
  createdAt: '2024-01-01',
};

const folder: Folder = {
  id: 'folder-1',
  name: 'Q1 Sales',
  description: '',
  status: 'Active',
  projectId: 'project-1',
  projectName: 'Demo',
  createdBy: 'user-1',
  createdAt: '2024-01-01',
  accessLevel: 'full',
  entities: { tables: {}, files: {} },
};

const session: Session = {
  id: 'session-1',
  folderId: 'folder-1',
  folderName: 'Q1 Sales',
  projectName: 'Demo',
  status: 'active',
  createdAt: '2024-01-01',
};

const uploadedTable: DataTable = {
  id: 'tbl-uploaded',
  name: 'sales',
  source: 'uploaded',
  columns: ['a', 'b'],
  rows: [],
  rowCount: 0,
};

const agentTable: DataTable = {
  id: 'tbl-agent',
  name: 'sales_clean',
  source: 'agent_created',
  columns: ['a', 'b'],
  rows: [],
  rowCount: 0,
};

// ---------------------------------------------------------------------------
// Streaming + gating-unlock integration
// ---------------------------------------------------------------------------

describe('Integration: SSE streaming renders the trail + single final message and unlocks downstream modes', () => {
  beforeEach(() => {
    streamSseMock.mockClear();
    scriptedEvents = [];
  });

  /**
   * Harness mirroring WorkspaceView: pipeline gating derived from a live
   * `tables` list, and a chat whose `onCompletion` refreshes tables (here, by
   * appending the freshly created `agent_created` transform table).
   */
  function useStreamingHarness() {
    const [tables, setTables] = useState<DataTable[]>([uploadedTable]);
    const pipeline = usePipelineStage(tables);
    const chat = useAgentChat({
      folder,
      session,
      user,
      mode: 'prepare' as WorkspaceMode,
      ensureSession: async () => session,
      onCompletion: () => {
        // Simulate "transform completed -> refresh folder tables" without reload.
        setTables((prev) =>
          prev.some((t) => t.source === 'agent_created') ? prev : [...prev, agentTable],
        );
      },
    });
    return { tables, pipeline, chat };
  }

  it('maps a scripted sequence to one activity trail + exactly one agent message, then unlocks visualize/publish', async () => {
    // A realistic Prepare-mode stream: status -> tool request -> tool response
    // -> streamed final answer -> completion (which also carries a final_output
    // fallback to prove the single-final guard holds end to end).
    scriptedEvents = [
      { type: 'stream_start', message: 'Starting transform' },
      { type: 'status', message: 'Analyzing tables' },
      { type: 'function_request', tool_name: 'join_tables', tool_args: { left: 'raw_a', right: 'raw_b' } },
      { type: 'function_response', tool_name: 'join_tables', response: { result: { table: 'clean_table' } } },
      { type: 'final_response', text: 'Created a cleaned table.' },
      { type: 'completion', final_output: 'Created a cleaned table.' },
    ];

    const { result } = renderHook(() => useStreamingHarness());

    // Before streaming: an uploaded table exists, so Prepare is enabled but the
    // transform-gated modes are still locked.
    expect(result.current.pipeline.enabledModes.sources).toBe(true);
    expect(result.current.pipeline.enabledModes.prepare).toBe(true);
    expect(result.current.pipeline.enabledModes.visualize).toBe(false);
    expect(result.current.pipeline.enabledModes.publish).toBe(false);

    await act(async () => {
      await result.current.chat.send('clean and combine these tables', 'prepare' as WorkspaceMode);
    });

    const messages = result.current.chat.messages;
    const byType = (t: string) => messages.filter((m) => m.type === t);
    // The user's message was appended, noisy lifecycle events were suppressed,
    // tool events carry inspectable metadata, and the stream produced exactly one
    // final agent message despite final_response AND a completion fallback.
    expect(byType('user')).toHaveLength(1);
    expect(byType('activity')).toHaveLength(0);
    expect(byType('tool_call')).toHaveLength(0);
    expect(byType('tool_response')).toHaveLength(1);
    expect(byType('tool_response')[0].metadata?.toolArgs).toEqual({ left: 'raw_a', right: 'raw_b' });
    expect(byType('tool_response')[0].metadata?.toolResponse).toEqual({ table: 'clean_table' });    expect(byType('agent')).toHaveLength(1);
    expect(byType('agent')[0].content).toBe('Created a cleaned table.');

    // Arrival order is preserved: the single agent message lands after the trail.
    const agentIdx = messages.findIndex((m) => m.type === 'agent');
    const lastToolIdx = messages.map((m) => m.type).lastIndexOf('tool_response');
    expect(agentIdx).toBeGreaterThan(lastToolIdx);

    // Streaming has stopped and the stream endpoint for Prepare was the chat stream.
    expect(result.current.chat.isGenerating).toBe(false);
    expect(streamSseMock).toHaveBeenCalledTimes(1);
    expect(streamSseMock.mock.calls[0][0]).toBe('http://test/agent/chat/stream');

    // The completion refreshed tables with an agent_created table, so Visualize
    // and Publish are now unlocked - no reload required (Requirement 3.8).
    expect(result.current.tables.some((t) => t.source === 'agent_created')).toBe(true);
    expect(result.current.pipeline.hasTransformTable).toBe(true);
    expect(result.current.pipeline.enabledModes.visualize).toBe(true);
    expect(result.current.pipeline.enabledModes.publish).toBe(true);
  });

  it('routes Visualize through the dashboard stream', async () => {
    scriptedEvents = [{ type: 'completion' }];
    // Seed with a transform table so Visualize is reachable.
    function useVizHarness() {
      const [tables] = useState<DataTable[]>([uploadedTable, agentTable]);
      const pipeline = usePipelineStage(tables);
      const chat = useAgentChat({
        folder,
        session,
        user,
        mode: 'visualize' as WorkspaceMode,
        ensureSession: async () => session,
        onCompletion: () => {},
      });
      return { pipeline, chat };
    }

    const { result } = renderHook(() => useVizHarness());
    expect(result.current.pipeline.enabledModes.visualize).toBe(true);

    await act(async () => {
      await result.current.chat.send('show revenue by region', 'visualize' as WorkspaceMode);
    });

    expect(streamSseMock).toHaveBeenCalledTimes(1);
    expect(streamSseMock.mock.calls[0][0]).toBe('http://test/agent/dashboard/stream');
  });
});

// ---------------------------------------------------------------------------
// Upload WebSocket + gating-flip integration
// ---------------------------------------------------------------------------

/**
 * Minimal scripted WebSocket that drives the existing upload protocol: it
 * auto-opens, records sent frames, and once it sees `process_files` replays
 * progress + `session_created` + `all_tables_created` back to the hook.
 */
class FakeUploadSocket {
  static OPEN = 1;
  static instances: FakeUploadSocket[] = [];

  readyState = 0;
  sent: Array<Record<string, unknown>> = [];
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;

  constructor() {
    FakeUploadSocket.instances.push(this);
    // Open on a later tick so the hook has wired all handlers first.
    setTimeout(() => {
      this.readyState = FakeUploadSocket.OPEN;
      this.onopen?.();
    }, 0);
  }

  private emit(obj: Record<string, unknown>) {
    this.onmessage?.({ data: JSON.stringify(obj) });
  }

  send(raw: string) {
    const frame = JSON.parse(raw) as Record<string, unknown>;
    this.sent.push(frame);
    if (frame.type === 'process_files') {
      setTimeout(() => {
        this.emit({ type: 'table_progress', progress: 50 });
        this.emit({ type: 'table_progress', progress: 100 });
        this.emit({
          type: 'session_created',
          sessionId: 'session-1',
          createdTables: { sales: 'tbl-uploaded' },
          files: { 'sales.csv': 'file-1' },
        });
        this.emit({ type: 'all_tables_created' });
      }, 0);
    }
  }

  close() {
    this.readyState = 3;
  }
}

describe('Integration: upload WebSocket streams progress while Prepare stays available', () => {
  beforeEach(() => {
    idCounter = 0;
    FakeUploadSocket.instances = [];
    vi.stubGlobal('WebSocket', FakeUploadSocket as unknown as typeof WebSocket);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  /** Harness mirroring WorkspaceView's upload wiring with live gating. */
  function useUploadHarness() {
    const [tables, setTables] = useState<DataTable[]>([]);
    const [activity, setActivity] = useState<ChatMessage[]>([]);
    const pipeline = usePipelineStage(tables);
    const uploader = useFolderUpload({
      folder,
      user,
      ensureSession: async () => session,
      updateFolder: async () => {},
      loadTablesForFolder: async () => {
        const next = [uploadedTable];
        setTables(next);
        return next;
      },
      addFiles: () => {},
      onActivity: (m) => setActivity((prev) => [...prev, m]),
    });
    return { tables, activity, pipeline, uploader };
  }

  it('streams progress, creates tables, and keeps Visualize/Publish locked until transform', async () => {
    const { result } = renderHook(() => useUploadHarness());

    // Empty folder: Prepare is already available for upload/source work.
    expect(result.current.pipeline.stage).toBe('empty');
    expect(result.current.pipeline.enabledModes.sources).toBe(true);
    expect(result.current.pipeline.enabledModes.prepare).toBe(true);

    const file = new File(['a,b\n1,2\n'], 'sales.csv', { type: 'text/csv' });

    await act(async () => {
      await result.current.uploader.upload([file]);
    });

    // Progress streamed to 100% and the upload reached the terminal stage.
    expect(result.current.uploader.stage).toBe('complete');
    expect(result.current.uploader.progress).toBe(100);
    expect(result.current.uploader.error).toBeNull();

    // Progress/status streamed into the shared activity trail.
    const activityText = result.current.activity.map((m) => m.content);
    expect(activityText.some((t) => /Uploading sales\.csv/i.test(t))).toBe(true);
    expect(activityText.some((t) => /Creating tables/i.test(t))).toBe(true);
    expect(activityText.some((t) => /complete/i.test(t))).toBe(true);

    // The protocol was driven correctly over the (fake) socket.
    const frameTypes = FakeUploadSocket.instances[0].sent.map((f) => f.type);
    expect(frameTypes).toContain('start_upload');
    expect(frameTypes).toContain('metadata');
    expect(frameTypes).toContain('process_files');

    // Tables now exist, flipping gating from sources-only to prepare-enabled;
    // the transform-gated modes remain locked until a transform runs.
    expect(result.current.tables).toHaveLength(1);
    expect(result.current.pipeline.stage).toBe('uploaded');
    expect(result.current.pipeline.enabledModes.prepare).toBe(true);
    expect(result.current.pipeline.enabledModes.visualize).toBe(false);
    expect(result.current.pipeline.enabledModes.publish).toBe(false);
  });

  it('rejects unsupported file types before opening a socket', async () => {
    const { result } = renderHook(() => useUploadHarness());
    const bad = new File(['nope'], 'notes.txt', { type: 'text/plain' });

    await act(async () => {
      await result.current.uploader.upload([bad]);
    });

    expect(result.current.uploader.error).toMatch(/Unsupported file type/i);
    expect(FakeUploadSocket.instances).toHaveLength(0);
    expect(result.current.pipeline.enabledModes.prepare).toBe(true);
  });
});


