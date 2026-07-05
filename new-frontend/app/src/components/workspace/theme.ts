/**
 * Shared workspace theme tokens - single source of truth.
 *
 * Monochrome "Deep Space Terminal" palette. White / light-gray is the only
 * accent; there are no purple or blue accents, no gradients, orbs, hero
 * blocks, or marketing copy. Every new workspace component must import these
 * tokens instead of hardcoding hex values, so the redesign changes layout/IA
 * without a visual rebrand.
 *
 * Values are reused exactly from the existing `Workspace.tsx` palette and the
 * error/success colors already used by the agent activity trail.
 *
 * Usage rules:
 * - Backgrounds near-black; raised surfaces dark gray; borders subtle gray.
 * - `success` is reserved for completed/ready states only (small dot form).
 * - `danger` is reserved for destructive/failed states only.
 */
export const SPACE = {
  bg: '#000000', // app background (pure black - matches homepage void)
  panel: '#161616', // raised surfaces (bubbles, cards) - greyish dark
  panelAlt: '#111111', // rails / artifact panel - slightly raised from black
  border: '#262626', // hairline borders
  hover: '#1E1E1E', // hover fill
  text: '#F4F4F5', // primary text / the only "accent"
  muted: '#8A8A8A', // secondary text
  subtle: '#5C5C5C', // tertiary text / captions
  success: '#22C55E', // completed/ready only (small dot)
  danger: '#F97066', // destructive/failed only
} as const;

export type SpaceToken = keyof typeof SPACE;
