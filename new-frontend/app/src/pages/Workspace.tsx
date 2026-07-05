import { WorkspaceView } from '@/components/workspace/WorkspaceView';

/**
 * Workspace route entry point.
 *
 * The page is now a thin shell: all orchestration and the responsive layout
 * live in {@link WorkspaceView}, which wires the pipeline/chat/upload hooks to
 * the ModeSwitcher, ChatThread, Composer, and ArtifactPanel.
 */
export function Workspace() {
  return <WorkspaceView />;
}

export default Workspace;
