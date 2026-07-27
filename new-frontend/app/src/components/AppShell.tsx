import { useEffect, useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { SlimRail, type SlimRailItemId } from './workspace/SlimRail';
import { TopBar } from './TopBar';
import { ToastContainer } from './Toast';
import { useAuth } from '@/hooks/useAuth';
import { useToast } from '@/hooks/useToast';
import { useAppState } from '@/hooks/useAppState';

export function AppShell() {
  const location = useLocation();
  const navigate = useNavigate();
  const auth = useAuth();
  const toast = useToast();
  const appState = useAppState();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // Workspace is the default landing surface: entering the shell without a
  // concrete destination (`/app`) drops the user straight into the Workspace.
  useEffect(() => {
    if (location.pathname === '/app' || location.pathname === '/app/') {
      navigate('/app/project', { replace: true });
    }
  }, [location.pathname, navigate]);

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const urlFolderId = params.get('folderId');
    // Only fall back to sessionStorage on the workspace route where restoring
    // context is expected. On other pages (e.g. Projects) a stale sessionStorage
    // value would trigger a race condition that overrides the user's new folder
    // selection with a previously visited one.
    const restoresFolderContext = location.pathname.startsWith('/app/workspace') || location.pathname.startsWith('/app/canvas');
    const folderId = urlFolderId || (restoresFolderContext ? sessionStorage.getItem('folderId') : null);
    if (folderId && appState.selectedFolder?.id !== folderId) {
      void appState.loadFolderContext(folderId);
    }
  }, [appState.selectedFolder?.id, appState.loadFolderContext, location.search, location.pathname]);

  // Breadcrumb computation
  const getBreadcrumb = () => {
    const path = location.pathname;
    const { selectedProject, selectedFolder } = appState;

    if (path === '/app/project') {
      if (selectedProject && selectedFolder) {
        return `Data / ${selectedProject.name} / ${selectedFolder.name}`;
      }
      if (selectedProject) {
        return `Data / ${selectedProject.name}`;
      }
      return 'Data';
    }

    if (path === '/app/workspace') return selectedFolder ? `Workspace / ${selectedFolder.name}` : 'Workspace';
    if (path === '/app/canvas') return selectedFolder ? `Workspace / ${selectedFolder.name} / Canvas` : 'Canvas';
    if (path === '/app/model-access') return 'Model Access';
    if (path === '/app/admin-panel') return 'Admin Panel';
    return '';
  };

  const handleNavigate = (route: string) => {
    const needsFolderContext = !route.includes('project') && !route.includes('admin-panel') && !route.includes('model-access');
    const target =
      needsFolderContext && appState.selectedFolder && !route.includes('folderId=')
        ? `${route}?folderId=${appState.selectedFolder.id}`
        : route;
    navigate(target);
    setMobileMenuOpen(false);
  };

  // The slim rail maps its icon-first actions onto the three global
  // destinations (Requirement 1.1): Home → Workspace (default landing),
  // Data → Projects, Settings → Admin Panel (Admin only). History/Help stay
  // within the Workspace surface; Admin is a no-op for non-Admin roles.
  const railActive: SlimRailItemId | undefined = location.pathname.startsWith('/app/workspace') || location.pathname.startsWith('/app/canvas')
    ? 'home'
    : location.pathname.startsWith('/app/project')
      ? 'data'
      : location.pathname.startsWith('/app/model-access') || location.pathname.startsWith('/app/admin-panel')
        ? 'settings'
        : undefined;

  const handleRailNavigate = (id: SlimRailItemId) => {
    switch (id) {
      case 'home':
      case 'history':
        handleNavigate('/app/workspace');
        break;
      case 'data':
        handleNavigate('/app/project');
        break;
      case 'settings':
        handleNavigate('/app/model-access');
        break;
      case 'help':
        toast.info(
          'Workspace help',
          'Pick a folder, then use the Sources · Prepare · Visualize · Publish modes. Upload data in Sources, ask the agent in chat, and review results in the right panel.',
        );
        break;
      default:
        break;
    }
  };

  // Get page title
  const getPageTitle = () => {
    const path = location.pathname;
    if (path === '/app/project') return 'Data';
    if (path === '/app/workspace') return 'Workspace';
    if (path === '/app/canvas') return 'Canvas';
    if (path === '/app/model-access') return 'Model Access';
    if (path === '/app/admin-panel') return 'Admin Panel';
    return '';
  };

  return (
    <div className="flex h-screen w-screen bg-black overflow-hidden">
      {/* Desktop slim rail - icon-first 56px navigation (slim-rail variant) */}
      <div className="hidden lg:block flex-shrink-0">
        <SlimRail
          active={railActive}
          onNewChat={() => handleNavigate('/app/workspace')}
          onNavigate={handleRailNavigate}
        />
      </div>

      {/* Mobile Sidebar Overlay */}
      {mobileMenuOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-black/60" onClick={() => setMobileMenuOpen(false)} />
          <div className="absolute left-0 top-0 bottom-0 w-[280px] bg-[#101010] border-r border-[#242424]">
            <Sidebar
              isOpen={true}
              onToggle={() => setMobileMenuOpen(false)}
              currentRoute={location.pathname}
              onNavigate={handleNavigate}
              user={auth.user}
              selectedFolder={appState.selectedFolder}
              selectedProject={appState.selectedProject}
            />
          </div>
        </div>
      )}

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0">
        <TopBar
          breadcrumb={getBreadcrumb()}
          pageTitle={getPageTitle()}
          user={auth.user}
          onLogout={auth.logout}
          onNavigate={handleNavigate}
          onMobileMenuToggle={() => setMobileMenuOpen(true)}
          notifications={toast.toasts}
        />
        <main className="flex-1 min-h-0 overflow-hidden">
          <div className="h-full min-h-0 animate-fade-in">
            <Outlet context={{ auth, toast, appState }} />
          </div>
        </main>
      </div>

      {/* Toast Container */}
      <ToastContainer toasts={toast.toasts} onDismiss={toast.removeToast} />
    </div>
  );
}
