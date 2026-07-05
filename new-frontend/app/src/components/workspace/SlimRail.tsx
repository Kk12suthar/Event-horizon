import {
  Plus,
  Home,
  Database,
  History,
  Settings,
  HelpCircle,
  type LucideIcon,
} from 'lucide-react';
import { SPACE } from './theme';

/**
 * SlimRail - Codex-style 56px icon rail.
 *
 * Replaces the legacy 224-260px sidebar with a slim, icon-first vertical rail.
 * Hosts: New chat (top), then Home, Data, History (navigation group), and a
 * bottom group with Settings and Help. Every action is icon-first with a
 * tooltip that appears to the right on hover (the rail is too narrow for
 * labels). Uses only the monochrome SPACE tokens - white/light-gray accent,
 * no purple/blue, no gradients.
 *
 * Requirements: 1.1 (minimal navigation surface), 1.2 (no Upload/Transform/
 * Dashboard/Report entries), 4.6 (actions are icon-first with tooltips).
 */

export type SlimRailItemId = 'home' | 'data' | 'history' | 'settings' | 'help';

interface RailItem {
  id: SlimRailItemId;
  label: string;
  icon: LucideIcon;
}

/** Primary navigation group (top). */
const NAV_ITEMS: RailItem[] = [
  { id: 'home', label: 'Home', icon: Home },
  { id: 'data', label: 'Data', icon: Database },
  { id: 'history', label: 'History', icon: History },
];

/** Utility group (bottom). */
const UTILITY_ITEMS: RailItem[] = [
  { id: 'settings', label: 'Settings', icon: Settings },
  { id: 'help', label: 'Help', icon: HelpCircle },
];

export interface SlimRailProps {
  /** The currently active navigation item, highlighted in the rail. */
  active?: SlimRailItemId;
  /** Invoked when the user clicks the "New chat" action. */
  onNewChat?: () => void;
  /** Invoked when the user activates a navigation/utility item. */
  onNavigate?: (id: SlimRailItemId) => void;
}

/** A single rail button with an icon and a hover tooltip to its right. */
function RailButton({
  label,
  icon: Icon,
  active = false,
  emphasis = false,
  onClick,
}: {
  label: string;
  icon: LucideIcon;
  active?: boolean;
  /** Emphasized (filled) styling, used for the New chat action. */
  emphasis?: boolean;
  onClick?: () => void;
}) {
  return (
    <div className="group relative flex justify-center">
      <button
        type="button"
        onClick={onClick}
        aria-label={label}
        title={label}
        className="relative flex h-9 w-9 items-center justify-center rounded-lg outline-none transition-colors focus-visible:ring-1"
        style={{
          color: emphasis ? SPACE.bg : active ? SPACE.text : SPACE.muted,
          backgroundColor: emphasis
            ? SPACE.text
            : active
              ? SPACE.hover
              : 'transparent',
        }}
        onMouseEnter={(e) => {
          if (emphasis || active) return;
          e.currentTarget.style.backgroundColor = SPACE.hover;
          e.currentTarget.style.color = SPACE.text;
        }}
        onMouseLeave={(e) => {
          if (emphasis || active) return;
          e.currentTarget.style.backgroundColor = 'transparent';
          e.currentTarget.style.color = SPACE.muted;
        }}
      >
        {/* Active indicator bar on the left edge of the rail. */}
        {active && (
          <span
            className="absolute -left-[14px] top-1/2 h-5 w-[2px] -translate-y-1/2 rounded-r"
            style={{ backgroundColor: SPACE.text }}
          />
        )}
        <Icon className="h-[18px] w-[18px]" strokeWidth={2} />
      </button>

      {/* Hover tooltip, positioned to the right of the narrow rail. */}
      <span
        role="tooltip"
        className="pointer-events-none absolute left-full top-1/2 z-50 ml-2 -translate-y-1/2 whitespace-nowrap rounded-md px-2 py-1 text-xs font-medium opacity-0 shadow-md transition-opacity duration-150 group-hover:opacity-100"
        style={{
          backgroundColor: SPACE.panel,
          color: SPACE.text,
          border: `1px solid ${SPACE.border}`,
        }}
      >
        {label}
      </span>
    </div>
  );
}

export function SlimRail({ active, onNewChat, onNavigate }: SlimRailProps) {
  return (
    <nav
      aria-label="Workspace navigation"
      className="flex h-full w-[56px] flex-shrink-0 flex-col items-center py-3"
      style={{
        backgroundColor: SPACE.panelAlt,
        borderRight: `1px solid ${SPACE.border}`,
      }}
    >
      {/* New chat */}
      <RailButton label="New chat" icon={Plus} emphasis onClick={onNewChat} />

      {/* Primary navigation */}
      <div className="mt-4 flex flex-col items-center gap-1">
        {NAV_ITEMS.map((item) => (
          <RailButton
            key={item.id}
            label={item.label}
            icon={item.icon}
            active={active === item.id}
            onClick={() => onNavigate?.(item.id)}
          />
        ))}
      </div>

      {/* Utility group pinned to the bottom */}
      <div className="mt-auto flex flex-col items-center gap-1">
        {UTILITY_ITEMS.map((item) => (
          <RailButton
            key={item.id}
            label={item.label}
            icon={item.icon}
            active={active === item.id}
            onClick={() => onNavigate?.(item.id)}
          />
        ))}
      </div>
    </nav>
  );
}

export default SlimRail;
