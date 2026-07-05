import { useEffect, useRef } from 'react';
import type { ChatMessage } from '../../types';
import { AgentActivityTrail, groupChatMessages } from '../AgentActivityTrail';
import { MessageRow } from './MessageRow';
import { SPACE } from './theme';

/**
 * ChatThread - the shared, mode-independent chat surface.
 *
 * It renders a single centered column (`max-w-[820px]`, Requirement 2.1) that
 * stays identical across every workspace mode. Final/visible messages
 * (`user`, `agent`, `error`) are rendered with {@link MessageRow}; intermediate
 * streamed events (`activity`, `tool_call`, `tool_response`, …) are grouped
 * into the existing {@link AgentActivityTrail} via {@link groupChatMessages}
 * so the agent's process shows in one collapsible container instead of
 * scattered pills (Requirement 2.4).
 *
 * The trail belonging to the most recent group is marked `running` while the
 * agent is generating, so it auto-expands during a run and collapses (but
 * stays inspectable) once the stream completes (Requirement 2.2 / 2.4).
 *
 * Uses only the monochrome SPACE tokens - no new colors, gradients, or
 * marketing chrome.
 */
export interface ChatThreadProps {
  /** The full ordered chat history for the active folder/session. */
  messages: ChatMessage[];
  /** True while the agent stream is in flight. */
  isGenerating: boolean;
}

export function ChatThread({ messages, isGenerating }: ChatThreadProps) {
  const items = groupChatMessages(messages);
  const lastGroupIndex = findLastGroupIndex(items);

  // Auto-scroll to the newest content as messages stream in.
  const bottomRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages.length, isGenerating]);

  return (
    <div className="flex-1 overflow-y-auto" style={{ backgroundColor: SPACE.bg }}>
      <div className="mx-auto flex w-full max-w-[820px] flex-col gap-4 px-4 py-6">
        {items.map((item, index) =>
          item.kind === 'group' ? (
            <AgentActivityTrail
              key={item.id}
              steps={item.steps}
              running={isGenerating && index === lastGroupIndex}
            />
          ) : (
            <MessageRow key={item.msg.id} message={item.msg} />
          )
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

/** Index of the last activity group in the render list, or -1 if none. */
function findLastGroupIndex(
  items: ReturnType<typeof groupChatMessages>
): number {
  for (let i = items.length - 1; i >= 0; i--) {
    if (items[i].kind === 'group') return i;
  }
  return -1;
}

export default ChatThread;
