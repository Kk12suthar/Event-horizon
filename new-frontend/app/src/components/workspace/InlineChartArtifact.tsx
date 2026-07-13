import { useState } from 'react';
import { BarChart3, Check, Gauge, Loader2, Plus, TriangleAlert } from 'lucide-react';
import type { ChartWidget } from '@/types';
import { ChartCanvas } from './artifacts/ChartArtifact';
import { SPACE } from './theme';

export interface InlineChartArtifactProps {
  chart: ChartWidget;
  saved: boolean;
  onSave?: (chart: ChartWidget) => Promise<ChartWidget>;
}

type SaveState = 'draft' | 'saving' | 'error';

export function InlineChartArtifact({ chart, saved, onSave }: InlineChartArtifactProps) {
  const [saveState, setSaveState] = useState<SaveState>('draft');
  const [error, setError] = useState('');
  const displayState = saved ? 'saved' : saveState;

  const save = async () => {
    if (!onSave || displayState === 'saving' || displayState === 'saved') return;
    setSaveState('saving');
    setError('');
    try {
      await onSave(chart);
      setSaveState('draft');
    } catch (reason) {
      setSaveState('error');
      setError(reason instanceof Error ? reason.message : 'Could not save this chart.');
    }
  };

  const Icon = chart.type === 'kpi' ? Gauge : BarChart3;

  return (
    <section
      className="w-full max-w-[720px] overflow-hidden rounded-lg border"
      style={{ backgroundColor: SPACE.panelAlt, borderColor: SPACE.border }}
      aria-label={`${chart.name} chart preview`}
    >
      <header
        className="flex min-h-12 flex-wrap items-center gap-2 px-3 py-2.5 sm:px-4"
        style={{ borderBottom: `1px solid ${SPACE.border}` }}
      >
        <div
          className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md"
          style={{ backgroundColor: SPACE.hover, color: SPACE.text }}
        >
          <Icon className="h-4 w-4" strokeWidth={1.8} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-xs font-medium" style={{ color: SPACE.text }}>
            {chart.name}
          </div>
          <div className="mt-0.5 text-[11px] capitalize" style={{ color: SPACE.subtle }}>
            Agent preview · {chart.type} · {chart.data.length} {chart.data.length === 1 ? 'value' : 'points'}
          </div>
        </div>
        <button
          type="button"
          onClick={() => void save()}
          disabled={!onSave || displayState === 'saving' || displayState === 'saved'}
          className="inline-flex h-8 flex-shrink-0 items-center gap-1.5 rounded-md px-2.5 text-xs font-medium outline-none transition-colors focus-visible:ring-1 disabled:cursor-default"
          style={{
            backgroundColor: displayState === 'saved' ? SPACE.hover : SPACE.text,
            color: displayState === 'saved' ? SPACE.muted : SPACE.bg,
            opacity: !onSave ? 0.45 : 1,
          }}
        >
          {displayState === 'saving' ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : displayState === 'saved' ? (
            <Check className="h-3.5 w-3.5" />
          ) : (
            <Plus className="h-3.5 w-3.5" />
          )}
          {displayState === 'saving' ? 'Saving' : displayState === 'saved' ? 'On dashboard' : 'Add to dashboard'}
        </button>
      </header>

      <div className="px-3 py-3 sm:px-4 sm:py-4">
        <ChartCanvas chart={chart} height={chart.type === 'kpi' ? 124 : 240} />
      </div>

      {saveState === 'error' && (
        <div
          className="flex items-start gap-2 border-t px-3 py-2.5 text-xs sm:px-4"
          style={{ borderColor: SPACE.border, color: SPACE.text }}
          role="alert"
        >
          <TriangleAlert className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
          <span className="min-w-0 flex-1">{error}</span>
          <button type="button" onClick={() => void save()} className="font-medium underline underline-offset-2">
            Retry
          </button>
        </div>
      )}
    </section>
  );
}

export default InlineChartArtifact;
