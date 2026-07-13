import { useState } from 'react';
import { Send, Square } from 'lucide-react';
import type { WorkspaceMode } from '../../types';
import { AttachButton, UploadAffordance } from './UploadAffordance';
import { SPACE } from './theme';

/**
 * Composer - the shared chat input pinned to the bottom of the center column.
 *
 * One composer is used in every mode (Requirement 2.7). It keeps the existing
 * rounded dark input + send-button styling, and folds the upload entry points
 * into the conversation via {@link UploadAffordance} (drag-drop) and
 * {@link AttachButton} (attach), both wired to the `useFolderUpload` handler
 * passed as `onUpload` (Requirements 6.1, 6.4).
 *
 * Mode awareness:
 *   - The placeholder changes by mode (Requirement 2.7).
 *   - Mode-specific quick-action chips seed the input on click.
 *
 * Disabled state: when no folder is selected the textarea, send, attach, and
 * drag-drop are all inert and the placeholder prompts the user to pick a
 * folder (Requirement 6.2). While generating, the send button becomes a stop
 * button. Uses only monochrome SPACE tokens.
 */

/** Mode-specific composer placeholders (Requirement 2.7). */
const PLACEHOLDERS: Record<WorkspaceMode, string> = {
  sources: 'Ask about uploaded files or schema…',
  prepare: 'Ask how to clean, join, or transform this data…',
  visualize: 'Ask for charts, KPIs, or dashboard changes…',
  publish: 'Ask to draft, rewrite, or export report sections…',
};

/** Mode-specific quick-action chips shown above the input. */
const QUICK_ACTIONS: Record<WorkspaceMode, string[]> = {
  sources: ['Summarize the uploaded files', 'What columns are in this data?'],
  prepare: ['Clean and combine these tables', 'Remove duplicate rows', 'Fix column types'],
  visualize: ['Show revenue by region as a bar chart', 'Trend of signups over time'],
  publish: ['Generate a report of key metrics', 'Summarize findings into sections'],
};

export interface ComposerProps {
  /** The active mode - drives placeholder and quick-action chips. */
  mode: WorkspaceMode;
  /** True when no folder is selected: disables input, send, attach, drag-drop. */
  disabled: boolean;
  /** True while the agent is streaming: shows the stop button. */
  isGenerating: boolean;
  /** Folder name shown as a chip inside the composer, when present. */
  folderName?: string;
  /** Invoked with the trimmed query when the user sends a message. */
  onSend: (query: string) => void;
  /** Aborts the in-flight stream; only used while generating. */
  onStop?: () => void;
  /** Receives allowed files from the attach button and drag-drop. */
  onUpload: (files: File[]) => void;
  /** Override the upload allowlist validator (defaults to the hook's). */
  isAllowedUploadFile?: (fileName: string) => boolean;
}

export function Composer({
  mode,
  disabled,
  isGenerating,
  folderName,
  onSend,
  onStop,
  onUpload,
  isAllowedUploadFile,
}: ComposerProps) {
  const [value, setValue] = useState('');

  const submit = () => {
    const query = value.trim();
    if (!query || disabled || isGenerating) return;
    onSend(query);
    setValue('');
  };

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };

  const quickActions = QUICK_ACTIONS[mode];
  const placeholder = disabled
    ? 'Select a folder to start chatting…'
    : PLACEHOLDERS[mode];

  return (
    <div className="flex-shrink-0 px-4 pb-4">
      <div className="mx-auto w-full max-w-[820px]">
        {/* Mode-specific quick-action chips (hidden when disabled). */}
        {!disabled && !isGenerating && quickActions.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1.5">
            {quickActions.map((action) => (
              <button
                key={action}
                type="button"
                onClick={() => setValue(action)}
                className="rounded-full border px-2.5 py-1 text-xs transition-colors"
                style={{
                  borderColor: SPACE.border,
                  color: SPACE.muted,
                  backgroundColor: SPACE.panel,
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.color = SPACE.text;
                  e.currentTarget.style.backgroundColor = SPACE.hover;
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.color = SPACE.muted;
                  e.currentTarget.style.backgroundColor = SPACE.panel;
                }}
              >
                {action}
              </button>
            ))}
          </div>
        )}

        <UploadAffordance
          disabled={disabled}
          onUpload={onUpload}
          isAllowedUploadFile={isAllowedUploadFile}
        >
          <div
            className="rounded-2xl border p-2.5"
            style={{ borderColor: SPACE.border, backgroundColor: SPACE.panel }}
          >
            {folderName && (
              <div className="mb-2 flex items-center gap-1.5">
                <span
                  className="rounded-md border px-2 py-0.5 text-[11px]"
                  style={{ borderColor: SPACE.border, color: SPACE.muted }}
                >
                  @{folderName}
                </span>
              </div>
            )}
            <div className="flex items-end gap-2">
              <AttachButton
                disabled={disabled}
                onUpload={onUpload}
                isAllowedUploadFile={isAllowedUploadFile}
              />
              <textarea
                value={value}
                onChange={(e) => setValue(e.target.value)}
                onKeyDown={handleKeyDown}
                rows={1}
                disabled={disabled}
                placeholder={placeholder}
                className="max-h-40 min-h-[24px] flex-1 resize-none bg-transparent px-1 py-1.5 text-sm outline-none disabled:opacity-50"
                style={{ color: SPACE.text }}
              />
              {isGenerating ? (
                <button
                  type="button"
                  onClick={onStop}
                  aria-label="Stop generating"
                  title="Stop"
                  className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full"
                  style={{ backgroundColor: SPACE.hover, color: SPACE.text }}
                >
                  <Square className="h-3.5 w-3.5" />
                </button>
              ) : (
                <button
                  type="button"
                  onClick={submit}
                  disabled={disabled || !value.trim()}
                  aria-label="Send message"
                  title="Send"
                  className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full transition-[filter,opacity] hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
                  style={{ backgroundColor: SPACE.brand, color: SPACE.onBrand }}
                >
                  <Send className="h-4 w-4" />
                </button>
              )}
            </div>
          </div>
        </UploadAffordance>
      </div>
    </div>
  );
}

export default Composer;
