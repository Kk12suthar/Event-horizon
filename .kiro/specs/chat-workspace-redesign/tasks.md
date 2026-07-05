# Implementation Plan: Chat-Workspace Redesign

## Overview

This is a **UI-only** redesign of the EventHorizon frontend (TypeScript + React, under `new-frontend/app/src/`). It collapses the legacy Upload/Transform/Dashboard/Report pages into one chat-first **Workspace** with a mode switcher (`Sources · Prepare · Visualize · Publish`), a shared chat thread/streaming schema, and a mode-specific right artifact panel. No backend changes - all calls reuse the existing `lib/api.ts` SSE/WebSocket/REST surface.

Implementation proceeds bottom-up: shared tokens and types first, then the pure pipeline/guard logic (the most heavily property-tested core), then the streaming and upload hooks, then the shell and chat/composer/artifact components, and finally the `WorkspaceView` orchestrator that wires everything together with responsive behavior.

Note on mode naming: the design's final section and requirements (R3, R6-R9) supersede the earlier 3-mode proposal. Use `WorkspaceMode = 'sources' | 'prepare' | 'visualize' | 'publish'` throughout. Property tests use `fast-check`.

## Tasks

- [x] 1. Set up workspace foundation (tokens, types, routing)
  - [x] 1.1 Create shared theme tokens
    - Create `new-frontend/app/src/components/workspace/theme.ts` exporting the `SPACE` palette as the single source of truth (bg/panel/border/text/muted/success/danger)
    - Reuse existing colors exactly; no gradients/orbs/marketing accents
    - _Requirements: 11.1, 11.2, 11.3, 11.4_

  - [x] 1.2 Extend frontend types with workspace view models
    - In `new-frontend/app/src/types/index.ts` add `WorkspaceMode` (`'sources' | 'prepare' | 'visualize' | 'publish'`), `PipelineStage` (`'empty' | 'uploaded' | 'transformed'`), `PipelineState`, and `ArtifactState`
    - _Requirements: 2.1, 3.1_

  - [x] 1.3 Add Workspace route and legacy route redirects
    - In `new-frontend/app/src/App.tsx` make `/app/workspace` the primary surface; support `?folderId=` and `?mode=` params
    - Redirect legacy routes (`/app/upload`, `/app/transform`, `/app/dashboard`, `/app/reports`) into the Workspace preserving `folderId` context
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [x] 2. Implement pipeline derivation and mode-guard logic (pure core)
  - [x] 2.1 Implement pipeline stage derivation hook
    - Create `new-frontend/app/src/hooks/usePipelineStage.ts` with pure `derivePipelineState(tables)` and a memoized `usePipelineStage(tables)`
    - Derive `hasUploadedTables`/`hasTransformTable`/`stage`; `enabledModes.sources = true` always; `prepare` enabled iff uploaded table exists; `visualize`/`publish` enabled iff an `agent_created` table exists
    - _Requirements: 3.3, 3.4, 3.5, 3.7, 3.8_

  - [x]* 2.2 Write property test for gating soundness
    - **Property 1: Gating soundness**
    - **Validates: Requirements 3.5**
    - Use `fast-check` to generate random `DataTable[]` and assert `enabledModes.visualize === enabledModes.publish === hasTransformTable`

  - [x]* 2.3 Write property test for Sources always available
    - **Property 2: Shape (Sources) always available**
    - **Validates: Requirements 3.3**

  - [x]* 2.4 Write property test for stage determinism
    - **Property 7: Stage determinism**
    - **Validates: Requirements 3.7**
    - Assert equal table inputs yield equal `stage`/`enabledModes` (pure, no side effects)

  - [x] 2.5 Implement mode guard and stream-endpoint selection helpers
    - Add `requestModeChange(target, state, current)` (returns `current` when target disabled) and `streamUrlForMode(mode)` mapping to existing endpoints (`visualize` → dashboard stream; others → chat stream) in `new-frontend/app/src/hooks/usePipelineStage.ts` or a sibling `lib/workspaceMode.ts`
    - _Requirements: 3.6, 2.4, 7.7, 8.7, 9.x_

  - [x]* 2.6 Write property test for no navigation to locked mode
    - **Property 3: No navigation to locked mode**
    - **Validates: Requirements 3.6**

  - [x]* 2.7 Write property test for endpoint mapping
    - **Property 6: Endpoint mapping**
    - **Validates: Requirements 2.4**
    - Assert `streamUrlForMode('visualize')` resolves to the dashboard stream; other modes resolve to the chat stream

- [x] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement shared chat streaming and upload hooks
  - [x] 4.1 Implement mode-independent SSE event mapper
    - Create the SSE-event → `ChatMessage` mapping (`stream_start`/`status` → activity, `tool_call`/`function_request` → tool_call, `tool_response`/`function_response` → tool_response, `final_response` → agent, `error` → error) in `new-frontend/app/src/hooks/useAgentChat.ts`
    - Mapping must be identical regardless of `mode`
    - _Requirements: 2.3, 2.4, 2.6_

  - [x]* 4.2 Write property test for schema invariance across modes
    - **Property 4: Schema invariance across modes**
    - **Validates: Requirements 2.3**

  - [x] 4.3 Implement useAgentChat hook
    - In `new-frontend/app/src/hooks/useAgentChat.ts` implement `send`/`stop`/`reset` using `streamSse`; guard at most one `agent` final message per request (`hasFinal`); call `onCompletion(mode)` exactly once; abort via `AbortController`
    - On `completion`, refresh tables so gating updates without reload
    - _Requirements: 2.2, 2.3, 2.5, 3.8_

  - [x]* 4.4 Write property test for single final message
    - **Property 5: Single final message**
    - **Validates: Requirements 2.5**
    - Generate random ordered SSE sequences; assert at most one `agent` message and arrival-order preservation

  - [x] 4.5 Implement useFolderUpload hook
    - Create `new-frontend/app/src/hooks/useFolderUpload.ts` reusing the existing upload WebSocket protocol (`getUploadWebSocketUrl`, chunked `start_upload`/`metadata`/`data`/`process_files`); enforce `.csv/.xls/.xlsx` allowlist client-side; stream progress into the shared activity trail; on `all_tables_created` merge entities and reload folder tables
    - _Requirements: 6.4, 6.5_

- [x] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Build app shell and hierarchy navigation
  - [x] 6.1 Implement SlimRail
    - Create `new-frontend/app/src/components/workspace/SlimRail.tsx` (56px icon rail: New chat, Home, Data, History, Settings, Help); icon-first with tooltips
    - _Requirements: 1.1, 1.2, 4.6_

  - [x] 6.2 Implement WorkspaceTopbar and WorkspaceSwitcher
    - Create `new-frontend/app/src/components/workspace/WorkspaceTopbar.tsx` (breadcrumb Project / Folder, folder status, session indicator, artifact toggle)
    - Create `new-frontend/app/src/components/workspace/WorkspaceSwitcher.tsx` (project/folder popover with search and inline create reusing `appState.createProject`/`createFolder`)
    - _Requirements: 4.2, 5.1, 5.2_

  - [x] 6.3 Wire AppShellV2 and reduce sidebar navigation
    - Update `new-frontend/app/src/components/AppShell.tsx` to the slim-rail variant with Workspace as default landing; update `Sidebar.tsx` to list only Projects, Workspace, and Admin Panel (Admin only for Admin role); remove Upload/Transform/Dashboard/Report entries
    - _Requirements: 1.1, 1.2, 1.4_

  - [x] 6.4 Update Projects folder cards with gated workflow icons
    - Update the Projects page folder cards to show folder icon, name, status pill, description, created-by/date and four workflow action icons (Sources/Prepare/Visualize/Publish) using the same gating as Requirement 3; activating an icon opens the Workspace for that folder in the corresponding mode
    - _Requirements: 5.3, 5.4, 5.5, 5.6_

- [x] 7. Build the shared chat surface
  - [x] 7.1 Implement MessageRow
    - Create `new-frontend/app/src/components/workspace/MessageRow.tsx`: user = right-aligned dark rounded bubble; agent = left-aligned readable text (no heavy bubble); error = coral left-border
    - _Requirements: 2.6_

  - [x] 7.2 Implement ChatThread reusing AgentActivityTrail
    - Create `new-frontend/app/src/components/workspace/ChatThread.tsx` (centered `max-w-[820px]`); group intermediate events into the existing `AgentActivityTrail` (auto-expand while running, collapse but inspectable after completion)
    - _Requirements: 2.1, 2.2, 2.4_

  - [x] 7.3 Implement EmptyState
    - Create `new-frontend/app/src/components/workspace/EmptyState.tsx`: "Select a folder to begin." onboarding with pick/create folder and example chips
    - _Requirements: 6.2_

  - [x] 7.4 Implement Composer with upload affordance and quick actions
    - Create `new-frontend/app/src/components/workspace/Composer.tsx` and `UploadAffordance.tsx`: fixed bottom rounded dark input + send button; attach button + drag-drop wired to `useFolderUpload`; mode-specific placeholder and quick-action chips; disabled when no folder selected
    - _Requirements: 2.7, 6.1, 6.4_

  - [x] 7.5 Implement ModeSwitcher
    - Create `new-frontend/app/src/components/workspace/ModeSwitcher.tsx`: segmented control of four modes in order with 16-18px icons; active uses faint `#E4E4E7`/10 bg; disabled renders 40% opacity, `cursor: not-allowed`, lock tooltip, and click is a no-op (uses `requestModeChange`)
    - _Requirements: 3.1, 3.2, 3.6_

- [x] 8. Build the artifact panel and mode variants
  - [x] 8.1 Implement ArtifactPanel container
    - Create `new-frontend/app/src/components/workspace/ArtifactPanel.tsx`: renders exactly one variant for the active mode; in-flow on desktop, overlay drawer below `lg`; lazy-load chart/report variants
    - _Requirements: 4.1, 4.5_

  - [x]* 8.2 Write property test for panel/mode consistency
    - **Property 8: Panel/mode consistency**
    - **Validates: Requirements 4.1**

  - [x] 8.3 Implement Sources panel and TableArtifact (Prepare)
    - Create `new-frontend/app/src/components/workspace/artifacts/SourcesPanel.tsx` (dropzone, uploaded file list, upload progress, raw tables, processing status, file delete, collapsed session info; disabled state when no folder)
    - Create `artifacts/TableArtifact.tsx` (final transformed table preview, source tables, recipe/steps, data-quality checks, column mapping, Rerun/Save/Inspect; disabled/ready/running-skeleton/error states)
    - _Requirements: 6.1, 6.2, 6.3, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

  - [x] 8.4 Implement ChartArtifact (Visualize)
    - Create `new-frontend/app/src/components/workspace/artifacts/ChartArtifact.tsx`: KPI strip, chart canvas/grid, chart list, selected-chart inspector, suggestions, Add chart/Regenerate; empty/skeleton/ready/error states; charts render cleanly and not oversized
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [x] 8.5 Implement ReportArtifact (Publish)
    - Create `new-frontend/app/src/components/workspace/artifacts/ReportArtifact.tsx`: eight report sections with per-section status, preview excerpt, evidence chips, include/exclude toggle, regenerate/edit icons; Outline and Preview views; sections fill in one by one while generating; per-section coral failure without failing the page; download buttons in Preview
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8_

- [x] 9. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Integrate WorkspaceView orchestrator and responsive behavior
  - [x] 10.1 Implement WorkspaceView and wire all components
    - Slim `new-frontend/app/src/pages/Workspace.tsx` into `components/workspace/WorkspaceView.tsx`: resolve folder from `?folderId`, persist/guard `?mode`, own panel open state, wire `usePipelineStage`/`useAgentChat`/`useFolderUpload` to ModeSwitcher/ChatThread/Composer/ArtifactPanel; refresh correct artifact set on completion
    - _Requirements: 2.2, 3.8, 4.1, 4.2, 4.3, 4.4_

  - [x] 10.2 Implement responsive layout
    - Desktop (≥1024/1200px): context rail + centered chat + right artifact panel; tablet (640-1199px): two-pane with overlay drawer and collapsed rail; mobile (<640/768px): chat-only with artifact bottom-sheet/full-screen drawer, mode pills horizontal scroll, sticky composer with artifact button; no horizontal overflow; tables scroll inside their own container
    - _Requirements: 4.1, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

  - [x]* 10.3 Write integration tests for streaming and gating
    - Mock `streamSse` to emit a scripted sequence; assert thread renders trail + single final message and ModeSwitcher unlocks after a `completion` that adds an `agent_created` table
    - Mock the upload WebSocket; assert progress streams and tables appear, flipping gating
    - _Requirements: 2.2, 2.3, 3.8, 6.4, 6.5_

- [x] 11. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional (property/unit/integration tests) and can be skipped for a faster MVP.
- Each task references specific requirements for traceability.
- Checkpoints ensure incremental validation.
- Property tests use `fast-check` and validate the universal correctness properties from the design (Properties 1-8).
- No backend changes: all data flows reuse the existing `lib/api.ts` SSE/WebSocket/REST surface and auth headers.
- The existing `AgentActivityTrail`, `useAppState`, and `useAuth` are reused unchanged.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "2.1", "4.1", "4.5"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "2.5", "4.2", "4.3", "6.1"] },
    { "id": 3, "tasks": ["2.6", "2.7", "4.4", "6.2", "6.3", "6.4", "7.1", "7.5"] },
    { "id": 4, "tasks": ["7.2", "7.3", "7.4", "8.1", "8.3", "8.4", "8.5"] },
    { "id": 5, "tasks": ["8.2", "10.1"] },
    { "id": 6, "tasks": ["10.2"] },
    { "id": 7, "tasks": ["10.3"] }
  ]
}
```
