import { useMemo } from 'react';
import { getAgentStreamUrl, getReportStreamUrl } from '../lib/api';
import type { DataTable, PipelineState, WorkspaceMode } from '../types';

/**
 * Pure derivation of the folder pipeline state from its current table list.
 *
 * Derivation rules (see design.md "Pipeline stage derivation"):
 *   - hasUploadedTables  = some table has source === 'uploaded'
 *   - hasTransformTable  = some table has source === 'agent_created'
 *   - stage              = 'transformed' if a transform table exists,
 *                          else 'uploaded' if an uploaded table exists,
 *                          else 'empty'
 *   - enabledModes.sources   = true for legacy upload/source routes only
 *   - enabledModes.prepare   = true always (entry point for upload + transform)
 *   - enabledModes.visualize = hasTransformTable (need a clean source)
 *   - enabledModes.publish   = hasTransformTable (need a clean source)
 *
 * This function is pure and side-effect free: equal inputs yield equal outputs.
 * It is exported separately so it can be property-tested in isolation.
 */
export function derivePipelineState(tables: DataTable[]): PipelineState {
  const hasUploadedTables = tables.some((t) => t.source === 'uploaded');
  const hasTransformTable = tables.some((t) => t.source === 'agent_created');

  const stage = hasTransformTable
    ? 'transformed'
    : hasUploadedTables
      ? 'uploaded'
      : 'empty';

  return {
    stage,
    hasUploadedTables,
    hasTransformTable,
    enabledModes: {
      sources: true,
      prepare: true,
      visualize: hasTransformTable,
      publish: hasTransformTable,
    },
  };
}

/**
 * Memoized React hook wrapper around {@link derivePipelineState}.
 *
 * Recomputes only when the `tables` reference changes, so it is safe to call on
 * every render (e.g. while the composer input changes) without recomputing the
 * gating state on each keystroke.
 */
export function usePipelineStage(tables: DataTable[]): PipelineState {
  return useMemo(() => derivePipelineState(tables), [tables]);
}

/**
 * Pure mode-guard for the ModeSwitcher (see design.md "Mode guard on switch").
 *
 * Returns `target` only when it is enabled in the supplied pipeline `state`;
 * otherwise returns `current` unchanged. This guarantees the UI can never
 * navigate to a locked mode - clicking a disabled mode is a no-op.
 *
 * Pure and side-effect free so it can be property-tested in isolation
 * (Property 3: "No navigation to locked mode").
 *
 * @param target  the mode the user attempted to switch to
 * @param state   the derived pipeline state gating the modes
 * @param current the currently active mode (returned when `target` is locked)
 */
export function requestModeChange(
  target: WorkspaceMode,
  state: PipelineState,
  current: WorkspaceMode,
): WorkspaceMode {
  return state.enabledModes[target] ? target : current;
}

/**
 * Pure mapping from a {@link WorkspaceMode} to the existing agent stream
 * endpoint (see design.md "Stream endpoint selection").
 *
 *   - `visualize` -> dashboard stream (`/agent/dashboard/stream`)
 *   - everything else (`sources`/`prepare`/`publish`) -> chat stream
 *     (`/agent/chat/stream`)
 *
 * No new endpoints are introduced; this only selects between the two existing
 * surfaces exposed by {@link getAgentStreamUrl}. Pure and side-effect free so
 * it can be property-tested in isolation (Property 6: "Endpoint mapping").
 *
 * @param mode the active workspace mode
 * @returns the fully-qualified stream URL for that mode
 */
export function streamUrlForMode(mode: WorkspaceMode, folderId = ''): string {
  if (mode === 'visualize') return getAgentStreamUrl('dashboard');
  if (mode === 'publish') return getReportStreamUrl(folderId);
  return getAgentStreamUrl('transform');
}

