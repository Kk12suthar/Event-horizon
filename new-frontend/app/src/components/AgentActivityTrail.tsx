import { useState } from 'react';
import { ArrowRight, Brain, Check, ChevronDown, Loader2 } from 'lucide-react';
import type { ChatMessage, MessageType } from '@/types';

/** Message types that represent the agent's intermediate process steps. */
export const PROCESS_TYPES: ReadonlySet<MessageType> = new Set<MessageType>([
  'activity',
  'tool_call',
  'tool_response',
  'thinking',
  'transition',
]);

type RenderItem =
  | { kind: 'group'; id: string; steps: ChatMessage[] }
  | { kind: 'message'; msg: ChatMessage };

/**
 * Collapse a flat message list into render items, merging consecutive process
 * steps (status / tool_call / tool_response / thinking / transition) into a
 * single collapsible container instead of scattered pills.
 */
export function groupChatMessages(messages: ChatMessage[]): RenderItem[] {
  const items: RenderItem[] = [];
  for (const msg of messages) {
    if (PROCESS_TYPES.has(msg.type)) {
      const last = items[items.length - 1];
      if (last && last.kind === 'group') {
        last.steps.push(msg);
      } else {
        items.push({ kind: 'group', id: `trail_${msg.id}`, steps: [msg] });
      }
    } else {
      items.push({ kind: 'message', msg });
    }
  }
  return items;
}

function stepColor(type: MessageType): string {
  if (type === 'tool_response') return '#22C55E';
  if (type === 'tool_call') return '#D4D4D8';
  if (type === 'thinking') return '#A78BFA';
  if (type === 'transition') return '#60A5FA';
  return '#6C6C6C';
}

function formatToolPayload(value: unknown): string {
  if (value === undefined || value === null || value === '') return '';
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

/** A short, safe one-line label for a step (used in the collapsed summary). */
function stepSummary(step: ChatMessage): string {
  if (step.type === 'thinking') return step.metadata?.streaming ? 'Thinking…' : 'Thought through the problem';
  if (step.type === 'transition') return step.content || 'Agent hand-off';
  return step.content || 'Working…';
}

/** Renders the agent's reasoning as a collapsible block that streams in. */
function ThinkingRow({ step }: { step: ChatMessage }) {
  const streaming = step.metadata?.streaming;
  const [open, setOpen] = useState(false);
  const text = step.content.trim();
  return (
    <div className="py-1">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 text-left"
      >
        {streaming ? (
          <Loader2 className="h-3 w-3 shrink-0 animate-spin" style={{ color: stepColor('thinking') }} />
        ) : (
          <Brain className="h-3 w-3 shrink-0" style={{ color: stepColor('thinking') }} />
        )}
        <span className="text-xs leading-5 text-[#C9B8F5]">{streaming ? 'Thinking…' : 'Thinking'}</span>
        {text && (
          <ChevronDown
            className={`ml-auto h-3 w-3 shrink-0 text-[#71717A] transition-transform ${open ? 'rotate-180' : ''}`}
          />
        )}
      </button>
      {open && text && (
        <pre className="mt-1 ml-5 max-h-56 overflow-auto whitespace-pre-wrap break-words border-l border-[#3A3350] pl-2 text-[11px] leading-4 text-[#B9AEd0]">
          {text}
        </pre>
      )}
    </div>
  );
}

/** Renders an agent-to-agent hand-off as a compact divider row. */
function TransitionRow({ step }: { step: ChatMessage }) {
  const from = step.metadata?.fromAgent;
  const to = step.metadata?.toAgent || step.content;
  return (
    <div className="flex items-center gap-2 py-1">
      <ArrowRight className="h-3 w-3 shrink-0" style={{ color: stepColor('transition') }} />
      <span className="text-xs leading-5 text-[#93B7F0]">
        {from ? `${prettyAgent(from)} → ${prettyAgent(String(to))}` : prettyAgent(String(to))}
      </span>
    </div>
  );
}

function prettyAgent(name: string): string {
  return name
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .trim();
}

function StepRow({ step }: { step: ChatMessage }) {
  if (step.type === 'thinking') return <ThinkingRow step={step} />;
  if (step.type === 'transition') return <TransitionRow step={step} />;

  const payload = step.type === 'tool_call'
    ? formatToolPayload(step.metadata?.toolArgs)
    : step.type === 'tool_response'
      ? formatToolPayload(step.metadata?.toolResponse)
      : '';

  return (
    <div className="py-1">
      <div className="flex items-center gap-2">
        <span
          className="h-1.5 w-1.5 shrink-0 rounded-full"
          style={{ backgroundColor: stepColor(step.type) }}
        />
        <span className="text-xs leading-5 text-[#D4D4D8]">{step.content}</span>
        {step.timestamp && (
          <span className="ml-auto shrink-0 text-[10px] text-[#71717A]">{step.timestamp}</span>
        )}
      </div>
      {payload && (
        <details className="ml-3 mt-1 rounded-md border border-[#262626] bg-[#000000] px-2 py-1">
          <summary className="cursor-pointer select-none text-[11px] leading-5 text-[#A1A1AA]">
            {step.type === 'tool_call' ? 'View input arguments' : 'View tool response'}
          </summary>
          <pre className="max-h-56 overflow-auto whitespace-pre-wrap break-words pt-1 text-[11px] leading-4 text-[#E4E4E7]">
            {payload}
          </pre>
        </details>
      )}
    </div>
  );
}

interface AgentActivityTrailProps {
  steps: ChatMessage[];
  /** True while this trail is still receiving steps (last group, generating). */
  running?: boolean;
}

/**
 * A single, left-aligned, collapsible container that lists the agent's process
 * steps line by line as they stream in - thinking (collapsible), tool calls
 * with request/response, and agent hand-offs. Auto-expands while running and
 * collapses once finished, unless the user has toggled it manually.
 */
export function AgentActivityTrail({ steps, running = false }: AgentActivityTrailProps) {
  // `null` means "follow the running state automatically"; once the user
  // toggles, we honor their explicit choice instead.
  const [userOpen, setUserOpen] = useState<boolean | null>(null);
  const open = userOpen ?? running;

  if (steps.length === 0) return null;

  const last = steps[steps.length - 1];
  const summary = running
    ? stepSummary(last)
    : `${steps.length} step${steps.length > 1 ? 's' : ''}`;

  return (
    <div className="w-full max-w-[90%]">
      <div className="overflow-hidden rounded-xl border border-[#262626] bg-[#161616]">
        <button
          type="button"
          onClick={() => {
            setUserOpen(!open);
          }}
          className="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-[#191919]"
        >
          {running ? (
            <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-[#E4E4E7]" />
          ) : (
            <Check className="h-3.5 w-3.5 shrink-0 text-[#22C55E]" />
          )}
          <span className="shrink-0 text-xs font-medium text-[#E6E6E6]">
            {running ? 'Agent working' : 'Agent steps'}
          </span>
          <span className="truncate text-xs text-[#8C8C8C]">· {summary}</span>
          <ChevronDown
            className={`ml-auto h-3.5 w-3.5 shrink-0 text-[#8C8C8C] transition-transform ${open ? 'rotate-180' : ''}`}
          />
        </button>
        {open && (
          <div className="border-t border-[#262626] px-3 py-2">
            {steps.map(step => (
              <StepRow key={step.id} step={step} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
