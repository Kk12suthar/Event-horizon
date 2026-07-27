import { Component, type ErrorInfo, type ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import { AlertTriangle, Database, RefreshCw } from 'lucide-react';

interface AppErrorBoundaryProps {
  children: ReactNode;
}

interface AppErrorBoundaryState {
  error: Error | null;
}

export class AppErrorBoundary extends Component<AppErrorBoundaryProps, AppErrorBoundaryState> {
  state: AppErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): AppErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('EventHorizon UI crashed', error, info);
  }

  private reload = () => {
    window.location.reload();
  };

  render() {
    if (!this.state.error) return this.props.children;

    return (
      <main className="flex min-h-screen items-center justify-center bg-black p-5 text-white">
        <section className="w-full max-w-lg rounded-2xl border border-[#342A26] bg-[#0D0D0D] p-6 shadow-2xl" role="alert">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-[#5B3628] bg-[#21130E]">
            <AlertTriangle className="h-5 w-5 text-[#D98B62]" />
          </div>
          <h1 className="mt-4 text-lg font-semibold">This screen could not be displayed</h1>
          <p className="mt-2 text-sm leading-6 text-[#A1A1AA]">
            Your data is safe. Reload this screen, or return to Data and choose the workspace again.
          </p>
          <p className="mt-3 rounded-lg border border-[#262626] bg-black px-3 py-2 font-mono text-[11px] text-[#8C8C8C]">
            {this.state.error.message || 'Unexpected interface error'}
          </p>
          <div className="mt-5 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={this.reload}
              className="inline-flex h-9 items-center gap-2 rounded-lg bg-[#C16E43] px-4 text-xs font-semibold text-black hover:bg-[#D07A4E]"
            >
              <RefreshCw className="h-3.5 w-3.5" /> Reload
            </button>
            <a
              href="/app/project"
              className="inline-flex h-9 items-center gap-2 rounded-lg border border-[#343434] px-4 text-xs font-medium text-[#D4D4D8] hover:bg-[#181818]"
            >
              <Database className="h-3.5 w-3.5" /> Return to Data
            </a>
          </div>
        </section>
      </main>
    );
  }
}

export function RouteErrorBoundary({ children }: AppErrorBoundaryProps) {
  const location = useLocation();
  return (
    <AppErrorBoundary key={`${location.pathname}${location.search}`}>
      {children}
    </AppErrorBoundary>
  );
}

export default AppErrorBoundary;