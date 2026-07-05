import {
  Wand2,
  BarChart3,
  FileText,
  Lock,
  type LucideIcon,
} from 'lucide-react';
import type { PipelineState, WorkspaceMode } from '../../types';
import { requestModeChange } from '../../hooks/usePipelineStage';
import { SPACE } from './theme';

/**
 * ModeSwitcher â€” segmented control for the three workflow modes.
 *
 * Renders the three modes in pipeline order (Prepare Â· Visualize Â·
 * Publish) as a compact segmented control with 16â€“18px icons. The active mode
 * uses a faint `#E4E4E7`/10 background with `#E4E4E7` text; inactive modes use
 * muted `#8C8C8C` text with a `#1E1E1E` hover fill (Requirement 3.2).
 *
 * Gating (Requirement 3.6): a disabled mode renders at 40% opacity with
 * `cursor: not-allowed`, a lock glyph, and a tooltip explaining what is
 * missing. Clicking a disabled mode is a no-op â€” every click is routed through
 * the pure {@link requestModeChange} guard, which returns the current mode
 * unchanged when the target is locked, so the UI can never navigate to a
 * locked mode.
 *
 * Requirements: 3.1 (three modes in order, 16â€“18px icons), 3.2 (active/inactive
 * styling), 3.6 (disabled appearance + no-op click).
 */

/** Inactive (idle) text color, per Requirement 3.2. */
const INACTIVE_TEXT = '#8C8C8C';
/** Inactive hover fill, per Requirement 3.2. */
const INACTIVE_HOVER = '#1E1E1E';
/** Active background: orange at 12% opacity. */
const ACTIVE_BG = 'rgba(193, 110, 67, 0.12)';
/** Active text color (brand orange). */
const ACTIVE_TEXT = '#d08a5e';

interface ModeMeta {
  id: WorkspaceMode;
  label: string;
  icon: LucideIcon;
  /** Tooltip shown when the mode is locked, explaining what is missing. */
  lockedReason: string;
}

/**
 * The visible modes in pipeline order. Sources/upload is handled inside Prepare,
 * so the switcher only moves between Prepare, Visualize, and Publish. Visualize
 * and Publish need a transformed (agent-created) table.
 */
const MODES: ModeMeta[] = [
  {
    id: 'prepare',
    label: 'Prepare',
    icon: Wand2,
    lockedReason: 'Prepare is always available.',
  },
  {
    id: 'visualize',
    label: 'Visualize',
    icon: BarChart3,
    lockedReason: 'Create a transformed table in Prepare first.',
  },
  {
    id: 'publish',
    label: 'Publish',
    icon: FileText,
    lockedReason: 'Create a transformed table in Prepare first.',
  },
];

export interface ModeSwitcherProps {
  /** The currently active mode, highlighted in the control. */
  mode: WorkspaceMode;
  /** Derived pipeline state supplying `enabledModes` for gating. */
  pipeline: PipelineState;
  /**
   * Invoked with the next mode when the user activates an enabled mode.
   * Clicks on disabled modes never reach this callback.
   */
  onModeChange: (mode: WorkspaceMode) => void;
}

/** A single segmented-control pill for one mode. */
function ModePill({
  meta,
  active,
  enabled,
  onActivate,
}: {
  meta: ModeMeta;
  active: boolean;
  enabled: boolean;
  onActivate: () => void;
}) {
  const { label, icon: Icon, lockedReason } = meta;

  // Resolve colors for the three visual states: active, idle-enabled, disabled.
  const color = active ? ACTIVE_TEXT : INACTIVE_TEXT;
  const backgroundColor = active ? ACTIVE_BG : 'transparent';

  return (
    <div className="group relative flex">
      <button
        type="button"
        onClick={onActivate}
        disabled={!enabled}
        aria-label={label}
        aria-pressed={active}
        title={enabled ? label : lockedReason}
        className="relative flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium outline-none transition-colors focus-visible:ring-1"
        style={{
          color,
          backgroundColor,
          opacity: enabled ? 1 : 0.4,
          cursor: enabled ? 'pointer' : 'not-allowed',
        }}
        onMouseEnter={(e) => {
          // Hover fill only applies to inactive, enabled pills (Req 3.2).
          if (!enabled || active) return;
          e.currentTarget.style.backgroundColor = INACTIVE_HOVER;
          e.currentTarget.style.color = SPACE.text;
        }}
        onMouseLeave={(e) => {
          if (!enabled || active) return;
          e.currentTarget.style.backgroundColor = 'transparent';
          e.currentTarget.style.color = INACTIVE_TEXT;
        }}
      >
        <Icon className="h-[17px] w-[17px]" strokeWidth={2} />
        <span>{label}</span>
        {!enabled && (
          <Lock className="h-3 w-3" strokeWidth={2} aria-hidden="true" />
        )}
      </button>

      {/* Lock tooltip for disabled modes, positioned below the pill. */}
      {!enabled && (
        <span
          role="tooltip"
          className="pointer-events-none absolute left-1/2 top-full z-50 mt-1.5 -translate-x-1/2 whitespace-nowrap rounded-md px-2 py-1 text-xs font-medium opacity-0 shadow-md transition-opacity duration-150 group-hover:opacity-100"
          style={{
            backgroundColor: SPACE.panel,
            color: SPACE.text,
            border: `1px solid ${SPACE.border}`,
          }}
        >
          {lockedReason}
        </span>
      )}
    </div>
  );
}

export function ModeSwitcher({
  mode,
  pipeline,
  onModeChange,
}: ModeSwitcherProps) {
  const handleActivate = (target: WorkspaceMode) => {
    // Route every click through the pure guard. When the target is locked it
    // returns the current mode unchanged, so this is a no-op.
    const next = requestModeChange(target, pipeline, mode);
    if (next !== mode) {
      onModeChange(next);
    }
  };

  return (
    <div
      role="tablist"
      aria-label="Workspace mode"
      className="inline-flex items-center gap-0.5 rounded-lg p-0.5"
      style={{
        backgroundColor: SPACE.panelAlt,
        border: `1px solid ${SPACE.border}`,
      }}
    >
      {MODES.map((meta) => (
        <ModePill
          key={meta.id}
          meta={meta}
          active={meta.id === mode}
          enabled={pipeline.enabledModes[meta.id]}
          onActivate={() => handleActivate(meta.id)}
        />
      ))}
    </div>
  );
}

export default ModeSwitcher;


