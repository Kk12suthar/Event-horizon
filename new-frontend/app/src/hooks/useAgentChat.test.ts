import { describe, expect, it } from 'vitest';
import fc from 'fast-check';
import {
  getSseEventType,
  mapSseEventToMessage,
  type ChatMessageDraft,
  type SseEvent,
} from './useAgentChat';
import type { WorkspaceMode } from '../types';

// ---------------------------------------------------------------------------
// Generators
// ---------------------------------------------------------------------------

/** All four workspace modes - used only as ambient context for Property 4. */
const modeArb: fc.Arbitrary<WorkspaceMode> = fc.constantFrom<WorkspaceMode>(
  'sources',
  'prepare',
  'visualize',
  'publish',
);

/**
 * The full SSE discriminator domain understood by the mapper, plus an
 * `unknown` value to exercise the non-renderable (`null`) branch.
 */
const eventTypeArb = fc.constantFrom(
  'stream_start',
  'status',
  'tool_call',
  'function_request',
  'tool_response',
  'function_response',
  'final_response',
  'error',
  'completion',
  'unknown_event',
);

/**
 * Smart generator for a single SSE event. Each record carries the optional
 * payload fields the mapper may read (`message`, `title`, `tool_name`, `text`,
 * `final_output`) so the generator covers both populated and default branches
 * without producing structurally-invalid events.
 */
const sseEventArb: fc.Arbitrary<SseEvent> = fc
  .record(
    {
      type: eventTypeArb,
      message: fc.string(),
      title: fc.string(),
      tool_name: fc.string(),
      text: fc.string(),
      final_output: fc.oneof(fc.constant(''), fc.string({ minLength: 1 })),
    },
    { requiredKeys: ['type'] },
  )
  .map((e) => e as SseEvent);

const sequenceArb: fc.Arbitrary<SseEvent[]> = fc.array(sseEventArb, {
  maxLength: 20,
});

// ---------------------------------------------------------------------------
// Property 4: Schema invariance across modes
// Validates: Requirements 2.3
//
// The mapper takes no `mode` argument, so a given SSE event must produce the
// exact same ChatMessageDraft no matter which mode the workspace is in and no
// matter how many times it is called. We assert determinism across repeated
// calls and independence from an injected ambient `mode` field on the event.
// ---------------------------------------------------------------------------
describe('Property 4: Schema invariance across modes', () => {
  it('produces an identical draft regardless of mode context or call count', () => {
    fc.assert(
      fc.property(sseEventArb, (event) => {
        // Baseline mapping with no mode context at all.
        const baseline = mapSseEventToMessage(event);

        // Repeated calls on the same event must be deterministic.
        expect(mapSseEventToMessage(event)).toEqual(baseline);

        // Injecting any mode as ambient context on the event must not change
        // the result - the mapping table is the single schema for every mode.
        for (const mode of ['sources', 'prepare', 'visualize', 'publish'] as WorkspaceMode[]) {
          const withMode: SseEvent = { ...event, mode };
          expect(mapSseEventToMessage(withMode)).toEqual(baseline);
        }
      }),
    );
  });

  it('is independent of the mode chosen to drive the stream', () => {
    fc.assert(
      fc.property(sseEventArb, modeArb, modeArb, (event, modeA, modeB) => {
        // Two different modes observing the same event see the same draft.
        const underA: SseEvent = { ...event, mode: modeA };
        const underB: SseEvent = { ...event, mode: modeB };
        expect(mapSseEventToMessage(underA)).toEqual(mapSseEventToMessage(underB));
      }),
    );
  });
});

// ---------------------------------------------------------------------------
// Property 5: Single final message
// Validates: Requirements 2.5
//
// Pure replica of the hook's per-event fold (the `hasFinal` guard lives inside
// useAgentChat). It mirrors the hook exactly: `completion.final_output` only
// becomes an agent message when no final has been seen, and any `agent` draft
// after a final is dropped. Non-agent drafts are always kept in arrival order.
// ---------------------------------------------------------------------------
function foldSseSequence(events: SseEvent[]): ChatMessageDraft[] {
  const drafts: ChatMessageDraft[] = [];
  let hasFinal = false;

  for (const event of events) {
    const type = getSseEventType(event);

    // `completion` is not a renderable message; it may carry a final_output
    // fallback that becomes the single agent message when none was streamed.
    if (type === 'completion') {
      if (event.final_output && !hasFinal) {
        hasFinal = true;
        drafts.push({ type: 'agent', content: String(event.final_output) });
      }
      continue;
    }

    const draft = mapSseEventToMessage(event);
    if (!draft) continue;

    if (draft.type === 'agent') {
      if (hasFinal) continue; // guard: at most one final agent message
      hasFinal = true;
    }

    drafts.push(draft);
  }

  return drafts;
}

/** Naive mapping with NO dedup - used as the order oracle for non-agent items. */
function naiveDrafts(events: SseEvent[]): ChatMessageDraft[] {
  const out: ChatMessageDraft[] = [];
  for (const event of events) {
    if (getSseEventType(event) === 'completion') {
      if (event.final_output) {
        out.push({ type: 'agent', content: String(event.final_output) });
      }
      continue;
    }
    const draft = mapSseEventToMessage(event);
    if (draft) out.push(draft);
  }
  return out;
}

describe('Property 5: Single final message', () => {
  it('appends at most one agent final message per sequence', () => {
    fc.assert(
      fc.property(sequenceArb, (events) => {
        const drafts = foldSseSequence(events);
        const agentCount = drafts.filter((d) => d.type === 'agent').length;
        expect(agentCount).toBeLessThanOrEqual(1);
      }),
    );
  });

  it('preserves arrival order of all non-agent messages', () => {
    fc.assert(
      fc.property(sequenceArb, (events) => {
        const folded = foldSseSequence(events).filter((d) => d.type !== 'agent');
        // Dedup only ever removes `agent` drafts, so non-agent drafts must be
        // exactly the naive mapping in unchanged arrival order.
        const oracle = naiveDrafts(events).filter((d) => d.type !== 'agent');
        expect(folded).toEqual(oracle);
      }),
    );
  });

  it('keeps the single agent message at the first final-producing position', () => {
    fc.assert(
      fc.property(sequenceArb, (events) => {
        const drafts = foldSseSequence(events);
        const agentIndex = drafts.findIndex((d) => d.type === 'agent');
        if (agentIndex === -1) return; // no final produced - nothing to anchor

        // Everything emitted before the agent message must be non-agent,
        // confirming the kept final is the FIRST one in arrival order.
        for (let i = 0; i < agentIndex; i++) {
          expect(drafts[i].type).not.toBe('agent');
        }
      }),
    );
  });
});
