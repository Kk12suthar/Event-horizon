import { Sparkles } from 'lucide-react';
import type { ChatMessage } from '../../types';
import { SPACE } from './theme';

/**
 * MessageRow - renders a single chat message according to its type.
 *
 * The visual treatment differs by message type (Requirement 2.6):
 * - `user`  → right-aligned dark rounded bubble (raised panel surface).
 * - `agent` → left-aligned readable text with a small attribution label and
 *             no heavy bubble, so final responses read like prose.
 * - `error` → coral left-border panel reserved for failed states.
 *
 * Intermediate streamed events (`activity`, `tool_call`, `tool_response`,
 * `chart_result`, `typing`) are grouped inside the existing
 * `AgentActivityTrail` rather than rendered here, so this component returns
 * `null` for them. Uses only the monochrome SPACE tokens - white/light-gray
 * accent, coral for errors only, no purple/blue.
 */
export interface MessageRowProps {
  message: ChatMessage;
}

export function MessageRow({ message }: MessageRowProps) {
  // User: right-aligned dark rounded bubble.
  if (message.type === 'user') {
    return (
      <div className="flex justify-end">
        <div
          className="max-w-[82%] rounded-2xl rounded-br-md px-4 py-2.5"
          style={{
            backgroundColor: SPACE.panel,
            border: `1px solid ${SPACE.border}`,
          }}
        >
          <p
            className="whitespace-pre-line text-sm leading-6"
            style={{ color: SPACE.text }}
          >
            {message.content}
          </p>
        </div>
      </div>
    );
  }

  // Error: coral left-border panel, reserved for failed states only.
  if (message.type === 'error') {
    return (
      <div
        className="max-w-[90%] rounded-r-lg border-l-2 px-4 py-3"
        style={{
          borderColor: SPACE.danger,
          backgroundColor: 'rgba(249,112,102,0.08)',
        }}
      >
        <p className="text-sm leading-6" style={{ color: SPACE.danger }}>
          {message.content}
        </p>
      </div>
    );
  }

  // Agent: left-aligned readable text, no heavy bubble.
  if (message.type === 'agent') {
    const usage = message.metadata?.tokenUsage;
    const timeTaken = message.metadata?.timeTaken;
    const streaming = message.metadata?.streaming;
    const showFooter = Boolean((usage && usage.total_tokens > 0) || timeTaken);
    return (
      <div className="max-w-[90%]">
        <div
          className="mb-1 flex items-center gap-1.5 text-xs"
          style={{ color: SPACE.subtle }}
        >
          <Sparkles className="h-3 w-3" /> EventHorizon AI
        </div>
        <p
          className="whitespace-pre-line text-sm leading-6"
          style={{ color: SPACE.text }}
        >
          {message.content}
          {streaming && (
            <span
              className="ml-0.5 inline-block h-3.5 w-[2px] translate-y-0.5 animate-pulse"
              style={{ backgroundColor: SPACE.muted }}
              aria-hidden="true"
            />
          )}
        </p>
        {showFooter && !streaming && (
          <div className="mt-1.5 flex items-center gap-2 text-[11px]" style={{ color: SPACE.subtle }}>
            {usage && usage.total_tokens > 0 && (
              <span title={`prompt ${usage.prompt_tokens.toLocaleString()} · completion ${usage.completion_tokens.toLocaleString()}`}>
                {usage.total_tokens.toLocaleString()} tokens
              </span>
            )}
            {usage && usage.total_tokens > 0 && timeTaken ? <span aria-hidden="true">·</span> : null}
            {timeTaken ? <span>{timeTaken}s</span> : null}
          </div>
        )}
      </div>
    );
  }

  // Intermediate streamed events are rendered by AgentActivityTrail, not here.
  return null;
}

export default MessageRow;
