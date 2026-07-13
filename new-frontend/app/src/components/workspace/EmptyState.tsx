import { FolderOpen, Plus, Sparkles } from 'lucide-react';
import { SPACE } from './theme';

/**
 * EmptyState - workspace onboarding shown in the center chat column when no
 * folder is selected (Requirement 6.2: the center chat says "Select a folder
 * to begin.").
 *
 * It guides the user toward the two entry points into folder work - picking an
 * existing folder or creating a new one (both reuse the WorkspaceSwitcher /
 * appState create flows via the supplied callbacks) - and surfaces a few
 * example prompt chips so the conversation has an obvious starting point once a
 * folder is chosen.
 *
 * This is the workspace-specific empty state and is intentionally separate from
 * the generic `components/EmptyState.tsx`. It uses only the monochrome SPACE
 * tokens - white/light-gray is the only accent, with no gradients, orbs, hero
 * blocks, or marketing copy.
 */
export interface EmptyStateProps {
  /** Title text. Defaults to the Requirement 6.2 copy. */
  title?: string;
  /** Supporting description under the title. */
  description?: string;
  /** Open the project/folder picker (WorkspaceSwitcher). */
  onPickFolder?: () => void;
  /** Start the inline create-folder flow. */
  onCreateFolder?: () => void;
  /** Example prompt chips to display. */
  exampleChips?: string[];
  /** Called when an example chip is activated. */
  onExampleSelect?: (example: string) => void;
}

const DEFAULT_EXAMPLES = [
  'Clean and combine these tables',
  'Show revenue by region as a bar chart',
  'Summarize key metrics into a report',
];

export function EmptyState({
  title = 'Select a folder to begin.',
  description = 'Pick an existing folder or create a new one to start uploading data, preparing tables, and exploring insights in one conversation.',
  onPickFolder,
  onCreateFolder,
  exampleChips = DEFAULT_EXAMPLES,
  onExampleSelect,
}: EmptyStateProps) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-4 py-16 text-center">
      <div
        className="mb-5 flex h-14 w-14 items-center justify-center rounded-2xl"
        style={{
          backgroundColor: SPACE.panel,
          border: `1px solid ${SPACE.border}`,
        }}
      >
        <FolderOpen className="h-7 w-7" style={{ color: SPACE.muted }} />
      </div>

      <h2 className="text-lg font-semibold" style={{ color: SPACE.text }}>
        {title}
      </h2>
      <p
        className="mt-2 max-w-[420px] text-sm leading-6"
        style={{ color: SPACE.muted }}
      >
        {description}
      </p>

      {/* Pick / create folder affordances */}
      <div className="mt-6 flex flex-wrap items-center justify-center gap-2.5">
        {onPickFolder && (
          <button
            type="button"
            onClick={onPickFolder}
            className="inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold transition-[filter] hover:brightness-110"
            style={{ backgroundColor: SPACE.brand, color: SPACE.onBrand }}
          >
            <FolderOpen className="h-4 w-4" />
            Pick a folder
          </button>
        )}
        {onCreateFolder && (
          <button
            type="button"
            onClick={onCreateFolder}
            className="inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors"
            style={{
              border: `1px solid ${SPACE.border}`,
              color: SPACE.muted,
              backgroundColor: 'transparent',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = SPACE.hover;
              e.currentTarget.style.color = SPACE.text;
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = 'transparent';
              e.currentTarget.style.color = SPACE.muted;
            }}
          >
            <Plus className="h-4 w-4" />
            Create folder
          </button>
        )}
      </div>

      {/* Example prompt chips */}
      {exampleChips.length > 0 && (
        <div className="mt-8 w-full max-w-[480px]">
          <div
            className="mb-3 flex items-center justify-center gap-1.5 text-xs uppercase tracking-wide"
            style={{ color: SPACE.subtle }}
          >
            <Sparkles className="h-3 w-3" /> Try an example
          </div>
          <div className="flex flex-wrap justify-center gap-2">
            {exampleChips.map((example) => (
              <button
                key={example}
                type="button"
                onClick={() => onExampleSelect?.(example)}
                className="rounded-full px-3.5 py-1.5 text-xs transition-colors"
                style={{
                  border: `1px solid ${SPACE.border}`,
                  backgroundColor: SPACE.panelAlt,
                  color: SPACE.muted,
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor = SPACE.hover;
                  e.currentTarget.style.color = SPACE.text;
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = SPACE.panelAlt;
                  e.currentTarget.style.color = SPACE.muted;
                }}
              >
                {example}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default EmptyState;
