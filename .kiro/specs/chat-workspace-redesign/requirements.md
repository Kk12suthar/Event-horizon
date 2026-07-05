# Requirements Document

## Introduction

This is a **UI-only** redesign of the EventHorizon frontend. It converts the four separate pages (Upload, Transform, Dashboard, Reports) and the hierarchy/upload pages into a single, minimal, Codex-style **folder Workspace**. The user always feels they are working inside one selected folder. The four workflow steps appear as top **segmented mode buttons** inside the Workspace - **Sources (Upload) · Prepare (Transform) · Visualize (Dashboard) · Publish (Report)** - not as large separate pages. A centered chat is the constant primary surface across all modes; a right-side **artifact panel** changes by mode.

Backend behavior, APIs, data model, auth, routes, and streaming are **unchanged**. The existing dark graphite theme and current button styling are **preserved exactly**.

Preserved visual theme (non-negotiable):
- Backgrounds: `#0A0A0B` / `#0B0B0E` / `#08080A`. Panels: `#121116` / `#131316` / `#0E0E11`. Borders: `#302C36` / `#232327`.
- Text: primary `#FFFFFF` / `#F4F4F5` / `#E4E4E7`; secondary `#B8B0C0` / `#8F8898` / `#8A8A92`.
- Primary button: bg `#E4E4E7`, text `#09090B`, hover `#D4D4D8`. Outline button: border `#302C36`, text `#B8B0C0`, hover bg `#1D1A22`, hover text white.
- Error/coral `#F97066` for destructive/failed only; success green `#22C55E` for completed/ready only (small dot, not large badge).
- Inter font; keep existing radius, density, icon style, shadcn-like controls. No gradients, orbs, hero blocks, or marketing copy.

## Glossary

- **Mode**: one of `sources | prepare | visualize | publish`.
- **Pipeline stage**: derived state of a folder - `empty | uploaded | transformed`.
- **Artifact panel**: the right-side, mode-specific output panel.
- **Agent Activity trail**: the single collapsible container grouping streamed intermediate events.
- **Context rail**: the left in-workspace panel showing folder context (files, tables, sessions, metadata).

## Requirements

### Requirement 1: Global App Structure & Navigation

**User Story:** As a user, I want a minimal sidebar with only the essential destinations, so that the app feels like a focused data IDE rather than a multi-page tool.

#### Acceptance Criteria
1. THE sidebar SHALL contain only: Projects, Workspace, and Admin Panel (Admin Panel only WHEN the user role is Admin).
2. THE sidebar SHALL NOT contain Upload, Transform, Dashboard, or Reports entries.
3. WHEN a user navigates to a legacy route (`/app/transform`, `/app/dashboard`, `/app/reports`, `/app/upload`) THEN the system SHALL route them into the unified Workspace preserving the `folderId` context.
4. THE Projects route SHALL be used for hierarchy creation and the Workspace route SHALL be used for all folder work.
5. THE redesign SHALL NOT modify backend APIs, data models, auth, or streaming behavior.

### Requirement 2: Shared Chat & Streaming Schema

**User Story:** As a user, I want the chat and streaming events to look and behave identically in every mode, so that I have one consistent mental model.

#### Acceptance Criteria
1. THE chat SHALL render with a centered column of max width ~820px in all modes.
2. WHEN the user switches modes THEN the system SHALL NOT reset, clear, or move the chat; chat history and final responses SHALL remain visible across modes.
3. THE system SHALL map streamed SSE events to chat items using one schema in every mode: `stream_start`/`status` to activity, `tool_call`/`function_request` to tool call, `tool_response`/`function_response` to tool response, `final_response` to agent message, `completion` to stop + refresh artifacts, `error` to error message.
4. WHILE the agent is generating THE intermediate events SHALL be grouped inside one Agent Activity container that auto-expands while running and collapses (but remains inspectable) after completion.
5. THE system SHALL append at most one final agent message per stream request.
6. User messages SHALL be right-aligned dark rounded bubbles; agent final responses SHALL be left-aligned readable text without a heavy bubble.
7. THE composer SHALL be fixed at the bottom of the center column with the existing rounded dark input + send button styling, and its placeholder SHALL change by mode (Sources: "Ask about uploaded files or schema…"; Prepare: "Ask how to clean, join, or transform this data…"; Visualize: "Ask for charts, KPIs, or dashboard changes…"; Publish: "Ask to draft, rewrite, or export report sections…").

### Requirement 3: Mode Switcher & Stepwise Gating

**User Story:** As a user, I want the four workflow steps as gated mode buttons, so that I follow the Upload to Transform to Dashboard to Report pipeline naturally.

#### Acceptance Criteria
1. THE Workspace top header SHALL show a small segmented control with four modes in order: Sources, Prepare, Visualize, Publish (16-18px icons).
2. THE active mode SHALL use a faint `#E4E4E7`/10 background with `#E4E4E7` text; inactive modes SHALL use `#8F8898` text with `#1D1A22` hover.
3. THE Sources mode SHALL be enabled WHEN the user has upload permission (Analyst/Admin); otherwise it SHALL be disabled.
4. THE Prepare mode SHALL be disabled UNTIL at least one uploaded file/table exists in the folder.
5. THE Visualize mode AND Publish mode SHALL be disabled UNTIL a transformed (agent-created) table exists in the folder.
6. WHEN a mode is disabled THEN it SHALL render at 40% opacity with `cursor: not-allowed` and a tooltip explaining what is missing, and clicking it SHALL be a no-op.
7. THE pipeline gating SHALL be derived from existing folder table/entity state with no new backend state.
8. WHEN a transform completes and produces a transformed table THEN Visualize and Publish SHALL unlock without a page reload.

### Requirement 4: Workspace Layout & Folder Context Rail

**User Story:** As a user, I want a Codex-style three-zone workspace, so that chat stays central while folder context and artifacts stay accessible.

#### Acceptance Criteria
1. ON desktop (>=1200px) THE Workspace SHALL show a left context rail (220-260px), a centered chat column (~820px), and a right artifact panel (420-520px) below a compact topbar.
2. THE Workspace top header SHALL show the folder breadcrumb (Project / Folder), a small folder status, and a current session indicator.
3. THE left context rail SHALL show folder context (not global navigation): Folder summary, Files, Tables, Sessions/history, and small metadata.
4. THE folder context SHALL always be visible somewhere in the Workspace.
5. THE layout SHALL use thin borders and compact panels with no marketing hero sections, no page-wide dashboard cards, and no nested cards inside cards.
6. Actions SHALL be icon-first with tooltips where possible.

### Requirement 5: Projects / Hierarchy Page

**User Story:** As a user, I want Projects to be the hierarchy command center, so that I can create and select projects and folders before entering the Workspace.

#### Acceptance Criteria
1. THE Projects page left column SHALL show a project list, a search input, a New Project button, and the existing active-project selection state.
2. THE Projects main content SHALL show the selected project header, description, folder count, created date, a Create Folder button, and the existing grid/list toggle.
3. EACH folder card SHALL be compact and dark and SHALL show: folder icon, folder name, status pill, short description, created-by/created-date, and four workflow action icons (Sources, Prepare, Visualize, Publish).
4. THE folder card workflow icons SHALL follow the same gating as Requirement 3 (Sources by permission; Prepare needs an uploaded table; Visualize/Publish need a transformed table).
5. WHEN a folder workflow icon is disabled THEN it SHALL use 40% opacity, muted text, and a lock icon or tooltip; ready state SHALL use a subtle white tint (not bright color); completed state MAY use a small green dot (not a large green badge).
6. WHEN the user activates a folder workflow icon THEN the system SHALL open the Workspace for that folder in the corresponding mode.

### Requirement 6: Sources Mode (Upload)

**User Story:** As a user, I want to upload and inspect raw data inside the Workspace, so that ingestion is part of the same chat-centric flow.

#### Acceptance Criteria
1. THE Sources right panel SHALL contain a dropzone, uploaded file list, upload progress, raw created tables, processing status, a file delete action, and collapsed session info.
2. WHEN no folder is selected THEN the center chat SHALL say "Select a folder to begin." and the right panel SHALL show a disabled upload state.
3. WHEN a folder is selected but has no files THEN the dropzone SHALL be shown prominently AND Prepare, Visualize, and Publish SHALL be disabled.
4. THE upload SHALL reuse the existing upload WebSocket protocol and SHALL stream progress into the shared Agent Activity trail.
5. WHEN upload processing completes THEN the system SHALL refresh folder tables so gating updates.

### Requirement 7: Prepare Mode (Transform)

**User Story:** As a user, I want Prepare to produce one final transformed table, so that downstream Visualize and Publish have a single clean source.

#### Acceptance Criteria
1. THE Prepare right panel SHALL show: final transformed table preview, source tables used, transformation recipe/steps, data quality checks, column mapping summary, and Rerun/Save/Inspect buttons.
2. WHEN the folder has no uploaded files THEN Prepare SHALL show a disabled state telling the user to upload in Sources.
3. WHEN uploaded files exist but no transform exists THEN the panel SHALL show a "Ready to prepare data." state.
4. WHILE a transform is running THE panel SHALL show a table skeleton and the live activity trail.
5. WHEN a transform completes THEN the final transformed table SHALL be shown as the main artifact.
6. WHEN a transform errors THEN the panel SHALL show a coral error panel with a retry action.
7. Prepare SHALL stream via the existing chat stream endpoint.

### Requirement 8: Visualize Mode (Dashboard)

**User Story:** As a user, I want Visualize to build charts from the transformed table, so that I can explore the prepared data.

#### Acceptance Criteria
1. THE Visualize right panel SHALL show: a KPI strip, a chart canvas/grid, a chart list, a selected-chart inspector, generated chart suggestions, and "Add chart"/"Regenerate" actions.
2. Visualize SHALL be disabled until a transformed table exists.
3. WHEN the dashboard is empty THEN the panel SHALL show chart suggestions derived from the transformed table.
4. WHILE charts are generating THE panel SHALL show chart skeletons and the activity trail.
5. WHEN charts are ready THEN they SHALL render cleanly and not oversized.
6. WHEN chart generation errors THEN the panel SHALL show a coral inline error with retry.
7. Visualize SHALL stream via the existing dashboard stream endpoint.

### Requirement 9: Publish Mode (Report)

**User Story:** As a user, I want Publish to be a section-based report workflow, so that a report is composed and reviewed rather than just downloaded.

#### Acceptance Criteria
1. THE Publish right panel SHALL present report sections: Executive Summary, Data Overview, Key Metrics, Trends and Patterns, Visual Evidence, Data Quality Notes, Recommendations, Appendix.
2. EACH section row SHALL show: section title, status (empty/drafted/reviewed/needs update), a small preview excerpt, evidence chips (table/chart/source), an include/exclude toggle, a regenerate icon button, and an edit icon button.
3. THE Publish right panel SHALL provide two views: Outline and Preview.
4. Publish SHALL be disabled until a transformed table exists.
5. WHEN no report is generated THEN the panel SHALL show the section outline with empty states.
6. WHILE a report is generating THE section rows SHALL fill in one by one.
7. WHEN the report is ready THEN a Preview SHALL be available with download buttons visible.
8. WHEN a section fails THEN that section SHALL show a coral status without failing the entire page.

### Requirement 10: Responsive Behavior

**User Story:** As a user on any device, I want the workspace to adapt, so that chat stays primary and panels remain accessible without overflow.

#### Acceptance Criteria
1. ON desktop (>=1200px) THE system SHALL show context rail + centered chat + right artifact panel.
2. ON tablet (768-1199px) THE system SHALL show a two-pane layout: chat ~60% and artifact panel ~40%, context rail collapsed to icons or a drawer, mode buttons visible at top, composer full width within the chat pane; a three-column layout SHALL only appear above 1100px.
3. ON mobile (<768px) THE system SHALL show chat only, with the artifact panel as a bottom sheet/full-screen drawer and the context rail as a drawer opened by a folder/context icon.
4. ON mobile THE mode buttons SHALL become horizontal scroll pills below the topbar and the composer SHALL stay fixed at the bottom with an artifact button near it to open the current mode's artifact.
5. THE layout SHALL have no horizontal overflow; tables SHALL scroll horizontally inside their own container.
6. Mobile priority order SHALL be: chat first, current mode second, artifact panel accessible but not permanently consuming width.

### Requirement 11: Theme & Styling Preservation

**User Story:** As a stakeholder, I want the existing theme and controls preserved exactly, so that the redesign changes layout/IA without a visual rebrand.

#### Acceptance Criteria
1. THE redesign SHALL reuse the existing color tokens, button variants, radius, density, icon style, and Inter typography exactly as specified in the Introduction.
2. THE redesign SHALL NOT introduce decorative gradients, orbs, hero blocks, or marketing copy.
3. Coral `#F97066` SHALL be used only for destructive/failed states and success green `#22C55E` only for completed/ready states (small dot form).
4. THE redesign SHALL NOT regress the established monochrome theme (no purple/blue accents).
