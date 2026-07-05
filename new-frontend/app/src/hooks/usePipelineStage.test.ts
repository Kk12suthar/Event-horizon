import { describe, expect, it } from 'vitest';
import fc from 'fast-check';
import {
  derivePipelineState,
  requestModeChange,
  streamUrlForMode,
} from './usePipelineStage';
import type { DataTable, WorkspaceMode } from '../types';

// ---------------------------------------------------------------------------
// Generators
// ---------------------------------------------------------------------------

/**
 * Smart generator for a single DataTable. Only `source` influences the pure
 * pipeline derivation under test, so the other fields are kept minimal but
 * type-valid. `source` is drawn from the full domain ('uploaded' |
 * 'agent_created') so generated arrays exercise every gating combination.
 */
const tableArb: fc.Arbitrary<DataTable> = fc.record({
  id: fc.string(),
  name: fc.string(),
  source: fc.constantFrom<'uploaded' | 'agent_created'>(
    'uploaded',
    'agent_created',
  ),
  columns: fc.array(fc.string(), { maxLength: 4 }),
  rowCount: fc.nat(),
}).map((t) => ({
  ...t,
  rows: [] as Record<string, string | number>[],
}));

const tablesArb: fc.Arbitrary<DataTable[]> = fc.array(tableArb, {
  maxLength: 8,
});

const modeArb: fc.Arbitrary<WorkspaceMode> = fc.constantFrom<WorkspaceMode>(
  'sources',
  'prepare',
  'visualize',
  'publish',
);

// ---------------------------------------------------------------------------
// Property 1: Gating soundness
// Validates: Requirements 3.5
// ---------------------------------------------------------------------------
describe('Property 1: Gating soundness', () => {
  it('visualize === publish === hasTransformTable for any DataTable[]', () => {
    fc.assert(
      fc.property(tablesArb, (tables) => {
        const state = derivePipelineState(tables);
        const expected = tables.some((t) => t.source === 'agent_created');
        expect(state.hasTransformTable).toBe(expected);
        expect(state.enabledModes.visualize).toBe(expected);
        expect(state.enabledModes.publish).toBe(expected);
        // The three values must all agree with one another.
        expect(state.enabledModes.visualize).toBe(state.enabledModes.publish);
        expect(state.enabledModes.visualize).toBe(state.hasTransformTable);
      }),
    );
  });
});

// ---------------------------------------------------------------------------
// Property 2: Sources and Prepare stay available
// Validates: Requirements 3.3
// ---------------------------------------------------------------------------
describe('Property 2: Sources and Prepare availability', () => {
  it('enabledModes.sources and enabledModes.prepare stay true for any DataTable[]', () => {
    fc.assert(
      fc.property(tablesArb, (tables) => {
        const state = derivePipelineState(tables);
        expect(state.enabledModes.sources).toBe(true);
        expect(state.enabledModes.prepare).toBe(true);
      }),
    );
  });
});

// ---------------------------------------------------------------------------
// Property 7: Stage determinism
// Validates: Requirements 3.7
// ---------------------------------------------------------------------------
describe('Property 7: Stage determinism', () => {
  it('equal table inputs yield equal stage/enabledModes (pure)', () => {
    fc.assert(
      fc.property(tablesArb, (tables) => {
        // Same reference invoked twice must be identical.
        const a = derivePipelineState(tables);
        const b = derivePipelineState(tables);
        expect(b).toEqual(a);

        // A structurally-equal but distinct copy must also yield equal output,
        // proving the result depends only on the input value (no side effects /
        // hidden state).
        const copy = tables.map((t) => ({ ...t }));
        const c = derivePipelineState(copy);
        expect(c).toEqual(a);
      }),
    );
  });
});

// ---------------------------------------------------------------------------
// Property 3: No navigation to locked mode
// Validates: Requirements 3.6
// ---------------------------------------------------------------------------
describe('Property 3: No navigation to locked mode', () => {
  it('returns current when target is disabled and target when enabled', () => {
    fc.assert(
      fc.property(tablesArb, modeArb, modeArb, (tables, target, current) => {
        const state = derivePipelineState(tables);
        const next = requestModeChange(target, state, current);

        if (state.enabledModes[target]) {
          expect(next).toBe(target);
        } else {
          expect(next).toBe(current);
        }

        // A *navigation* (the result differs from where we started) can only
        // ever land on an enabled mode. When `next === current` no navigation
        // happened, so a locked `current` is allowed to pass through unchanged.
        if (next !== current) {
          expect(state.enabledModes[next]).toBe(true);
        }
      }),
    );
  });
});

// ---------------------------------------------------------------------------
// Property 6: Endpoint mapping
// Validates: Requirements 2.4
// ---------------------------------------------------------------------------
describe('Property 6: Endpoint mapping', () => {
  it("streamUrlForMode('visualize') resolves to the dashboard stream", () => {
    expect(streamUrlForMode('visualize').endsWith('/agent/dashboard/stream')).toBe(
      true,
    );
  });
  it('sources and prepare resolve to the chat stream', () => {
    fc.assert(
      fc.property(
        fc.constantFrom<WorkspaceMode>('sources', 'prepare'),
        (mode) => {
          expect(streamUrlForMode(mode).endsWith('/agent/chat/stream')).toBe(true);
        },
      ),
    );
  });

  it("streamUrlForMode('publish') resolves to the report stream with folder scope", () => {
    expect(streamUrlForMode('publish', 'folder 1')).toContain(
      '/report/chat/stream?folder_id=folder%201',
    );
  });
});


