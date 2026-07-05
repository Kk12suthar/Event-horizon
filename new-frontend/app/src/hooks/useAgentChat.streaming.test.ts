// @vitest-environment jsdom
//
// Verifies the sophisticated streaming contract end-to-end through the REAL
// useAgentChat hook: agent transitions, a collapsible thinking block streamed
// from deltas, minimal tool req/response, a token-streamed final answer, and
// token usage attached from the completion event.

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useAgentChat } from './useAgentChat';
import type { Folder, Session, User, WorkspaceMode } from '../types';

let scriptedEvents: Record<string, unknown>[] = [];

const streamSseMock = vi.fn(
  async (
    _url: string,
    _body: Record<string, unknown>,
    handlers: { onEvent: (e: Record<string, unknown>) => void },
  ) => {
    for (const event of scriptedEvents) handlers.onEvent(event);
  },
);

vi.mock('../lib/api', () => ({
  streamSse: (...args: unknown[]) =>
    (streamSseMock as unknown as (...a: unknown[]) => Promise<void>)(...args),
  getAgentStreamUrl: (surface: 'transform' | 'dashboard') =>
    surface === 'dashboard' ? 'http://test/agent/dashboard/stream' : 'http://test/agent/chat/stream',
}));

const user: User = { id: 'user-1', name: 'Ada', email: 'ada@example.com', role: 'Analyst', status: 'active', createdAt: '2024-01-01' };
const folder: Folder = { id: 'folder-1', name: 'Q1', description: '', status: 'Active', projectId: 'p1', projectName: 'Demo', createdBy: 'user-1', createdAt: '2024-01-01', accessLevel: 'full', entities: { tables: {}, files: {} } };
const session: Session = { id: 'session-1', folderId: 'folder-1', folderName: 'Q1', projectName: 'Demo', status: 'active', createdAt: '2024-01-01' };

function useChat() {
  return useAgentChat({ folder, session, user, ensureSession: async () => session, onCompletion: () => {} });
}

describe('useAgentChat sophisticated streaming', () => {
  beforeEach(() => {
    streamSseMock.mockClear();
    scriptedEvents = [];
  });

  it('renders thinking, transitions, tools, a token-streamed answer, and token usage', async () => {
    scriptedEvents = [
      { type: 'stream_start' },
      { type: 'agent_transition', from_agent: 'orchestrator', to_agent: 'data_agent', label: 'Data Agent' },
      { type: 'thinking_start', agent_name: 'data_agent' },
      { type: 'thinking_delta', delta: 'Let me ' },
      { type: 'thinking_delta', delta: 'inspect the tables.' },
      { type: 'thinking_end' },
      { type: 'function_request', tool_name: 'data_list_tables', tool_args: { folder: 'x' } },
      { type: 'function_response', tool_name: 'data_list_tables', response: { result: '{"table_count":2}' } },
      { type: 'agent_transition', from_agent: 'data_agent', to_agent: 'responder', label: 'Responder' },
      { type: 'answer_delta', delta: 'The folder ' },
      { type: 'answer_delta', delta: 'has 2 ' },
      { type: 'answer_delta', delta: 'tables.' },
      { type: 'final_response', text: 'The folder has 2 tables.' },
      { type: 'completion', final_output: 'The folder has 2 tables.', time_taken: 0.42, token_usage: { prompt_tokens: 120, completion_tokens: 30, total_tokens: 150 } },
    ];

    const { result } = renderHook(() => useChat());

    await act(async () => {
      await result.current.send('how many tables?', 'prepare' as WorkspaceMode);
    });

    const messages = result.current.messages;
    const byType = (t: string) => messages.filter((m) => m.type === t);

    // Exactly one final answer, assembled from the streamed answer deltas and
    // reconciled by final_response/completion.
    expect(byType('agent')).toHaveLength(1);
    expect(byType('agent')[0].content).toBe('The folder has 2 tables.');

    // Token usage + timing attached from the completion event.
    expect(byType('agent')[0].metadata?.tokenUsage?.total_tokens).toBe(150);
    expect(byType('agent')[0].metadata?.timeTaken).toBe(0.42);
    expect(byType('agent')[0].metadata?.streaming).toBe(false);

    // One thinking block accumulated from its deltas.
    expect(byType('thinking')).toHaveLength(1);
    expect(byType('thinking')[0].content).toBe('Let me inspect the tables.');

    // Both agent transitions captured.
    expect(byType('transition')).toHaveLength(2);
    expect(byType('transition')[1].content).toBe('Responder');

    // Minimal tool request/response with inspectable payloads.
    expect(byType('tool_call')).toHaveLength(1);
    expect(byType('tool_call')[0].metadata?.toolArgs).toEqual({ folder: 'x' });
    expect(byType('tool_response')).toHaveLength(1);
    expect(byType('tool_response')[0].metadata?.toolResponse).toBe('{"table_count":2}');

    expect(result.current.isGenerating).toBe(false);
  });
});
