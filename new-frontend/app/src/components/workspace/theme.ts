/**
 * Shared workspace theme tokens - single source of truth.
 *
 * "Deep Space Terminal" palette. Near-black surfaces stay monochrome while
 * muted burnt orange marks primary actions and selected workflow state. There
 * are no purple or blue accents, gradients, or decorative color fields. Every
 * new workspace component must import these
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
  panel: '#101010', // raised surfaces (bubbles, cards) - greyish dark
  panelAlt: '#090909', // rails / artifact panel - slightly raised from black
  border: '#262626', // hairline borders
  hover: '#181818', // hover fill
  text: '#F4F4F5', // primary text / the only "accent"
  muted: '#8A8A8A', // secondary text
  subtle: '#5C5C5C', // tertiary text / captions
  brand: '#C16E43', // shared primary action background (matches --primary)
  brandHover: '#D07A4E', // restrained hover lift for primary actions
  brandSoft: 'rgba(255, 255, 255, 0.06)', // neutral selected surface; brand stays on controls and borders
  brandBorder: 'rgba(193, 110, 67, 0.38)',
  onBrand: '#0A0A0A', // high-contrast content on the brand fill
  success: '#D4D4D8', // completed/ready only (small dot)
  danger: '#A1A1AA', // destructive/failed only
} as const;

export type SpaceToken = keyof typeof SPACE;
