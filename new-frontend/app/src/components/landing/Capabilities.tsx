import { useState, type FC } from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  BarChart3,
  Check,
  ChevronRight,
  Database,
  FileOutput,
  FileSpreadsheet,
  Folder,
  History,
  LayoutDashboard,
  MessageSquare,
  MoreHorizontal,
  Paperclip,
  Presentation,
  Send,
  Table2,
  Wrench,
} from "lucide-react";

type WorkspaceMode = "prepare" | "visualize" | "publish";

const modes = [
  { id: "prepare" as const, label: "Prepare", icon: Table2 },
  { id: "visualize" as const, label: "Visualize", icon: BarChart3 },
  { id: "publish" as const, label: "Publish", icon: FileOutput },
];

const modeCopy: Record<WorkspaceMode, { title: string; prompt: string; response: string; tool: string; toolInput: string; toolOutput: string }> = {
  prepare: {
    title: "Prepare one reliable table",
    prompt: "Clean the uploaded sales tables, standardize regions, and create one table for analysis.",
    response: "I inspected the three folder sources, aligned their schemas, removed duplicate order IDs, and validated the resulting row count. The prepared table is ready to save.",
    tool: "prepare_folder_tables",
    toolInput: 'folder="Global sales"; sources=3; dedupe_key="order_id"',
    toolOutput: 'table="sales_clean"; rows=48,219; checks=passed',
  },
  visualize: {
    title: "Build visuals from the selected table",
    prompt: "Compare net revenue by region and highlight the strongest quarter.",
    response: "APAC leads net revenue and shows the strongest quarter-over-quarter gain. I created a regional comparison chart and kept it available in the chat until it is saved to the dashboard.",
    tool: "create_dashboard_chart",
    toolInput: 'table="sales_clean"; metric="net_revenue"; dimension="region"',
    toolOutput: 'chart="Revenue by region"; type="bar"; state="draft"',
  },
  publish: {
    title: "Turn the same evidence into a report",
    prompt: "Create a concise executive report using the saved regional revenue chart.",
    response: "The report has an executive summary, regional performance section, key risks, and an appendix with the prepared-table lineage. Four export formats are ready.",
    tool: "generate_report",
    toolInput: 'table="sales_clean"; dashboard="Executive dashboard"; audience="board"',
    toolOutput: 'report="Board review"; sections=4; formats="HTML, PDF, PPTX, DOCX"',
  },
};

const chartData = [
  { label: "NA", value: 68 },
  { label: "EMEA", value: 52 },
  { label: "APAC", value: 86 },
  { label: "LATAM", value: 39 },
];

const sourceRows = [
  { name: "orders_q1.csv", meta: "18.4k rows" },
  { name: "orders_q2.csv", meta: "17.1k rows" },
  { name: "orders_q3.csv", meta: "14.2k rows" },
];

function ToolTrace({ mode }: { mode: WorkspaceMode }) {
  const content = modeCopy[mode];

  return (
    <details className="group mt-5 overflow-hidden rounded-md border border-white/[0.08] bg-white/[0.02]">
      <summary className="flex min-h-11 cursor-pointer list-none items-center gap-3 px-3 text-xs text-zinc-400 transition-colors duration-300 hover:text-zinc-200 [&::-webkit-details-marker]:hidden">
        <ChevronRight className="h-3.5 w-3.5 shrink-0 transition-transform duration-300 group-open:rotate-90" aria-hidden="true" />
        <Wrench className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        <span className="truncate font-mono text-[10px]">{content.tool}</span>
        <span className="ml-auto flex items-center gap-2 font-mono text-[9px] text-zinc-600">
          <span className="h-1.5 w-1.5 rounded-full bg-primary" aria-hidden="true" />
          completed
        </span>
      </summary>
      <div className="grid gap-px border-t border-white/[0.07] bg-white/[0.07] sm:grid-cols-2">
        <div className="bg-[#090909] p-3">
          <p className="font-mono text-[9px] uppercase tracking-[0.12em] text-zinc-600">Input arguments</p>
          <code className="mt-2 block break-words font-mono text-[10px] leading-5 text-zinc-400">{content.toolInput}</code>
        </div>
        <div className="bg-[#090909] p-3">
          <p className="font-mono text-[9px] uppercase tracking-[0.12em] text-zinc-600">Tool response</p>
          <code className="mt-2 block break-words font-mono text-[10px] leading-5 text-zinc-400">{content.toolOutput}</code>
        </div>
      </div>
    </details>
  );
}

function PrepareResult() {
  return (
    <div className="mt-5 overflow-hidden rounded-md border border-white/[0.08]">
      <div className="flex items-center justify-between border-b border-white/[0.07] bg-white/[0.02] px-3 py-2.5">
        <div className="flex items-center gap-2">
          <Table2 className="h-3.5 w-3.5 text-zinc-400" aria-hidden="true" />
          <span className="font-mono text-[10px] text-zinc-300">sales_clean</span>
        </div>
        <span className="flex items-center gap-1.5 text-[10px] text-zinc-500">
          <Check className="h-3 w-3" aria-hidden="true" />
          48,219 rows validated
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[520px] text-left font-mono text-[9px]">
          <thead className="text-zinc-600">
            <tr>{["order_id", "region", "quarter", "net_revenue"].map((heading) => <th key={heading} className="border-b border-white/[0.06] px-3 py-2 font-normal">{heading}</th>)}</tr>
          </thead>
          <tbody className="text-zinc-400">
            <tr>{["ORD-10482", "APAC", "Q3", "$128,440"].map((cell) => <td key={cell} className="px-3 py-2">{cell}</td>)}</tr>
            <tr className="bg-white/[0.015]">{["ORD-10483", "EMEA", "Q3", "$96,210"].map((cell) => <td key={cell} className="px-3 py-2">{cell}</td>)}</tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

function VisualizeResult() {
  return (
    <div className="mt-5 rounded-md border border-white/[0.08] bg-[#080808] p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium text-zinc-200">Net revenue by region</p>
          <p className="mt-1 font-mono text-[9px] text-zinc-600">sales_clean / Q1-Q3 FY26</p>
        </div>
        <button type="button" className="inline-flex h-8 items-center gap-1.5 rounded-md border border-transparent bg-primary px-3 text-[10px] font-medium text-primary-foreground transition-colors duration-300 hover:bg-primary/90">
          <LayoutDashboard className="h-3.5 w-3.5" aria-hidden="true" />
          Add to dashboard
        </button>
      </div>
      <div className="mt-6 flex h-44 items-end gap-3 border-b border-l border-white/[0.08] px-4 pt-4 sm:gap-6">
        {chartData.map((bar) => (
          <div key={bar.label} className="flex h-full flex-1 flex-col justify-end gap-2">
            <div className="relative flex-1">
              <div className={`absolute inset-x-0 bottom-0 transition-[height,background-color] duration-700 ${bar.label === "APAC" ? "bg-primary hover:bg-primary/90" : "bg-zinc-300 hover:bg-white"}`} style={{ height: `${bar.value}%` }} />
            </div>
            <span className="pb-2 text-center font-mono text-[9px] text-zinc-600">{bar.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function PublishResult() {
  const sections = ["Executive summary", "Regional performance", "Risks and opportunities", "Data lineage appendix"];
  return (
    <div className="mt-5 overflow-hidden rounded-md border border-white/[0.08] bg-[#080808]">
      <div className="flex items-center justify-between border-b border-white/[0.07] px-4 py-3">
        <div className="flex items-center gap-2">
          <FileOutput className="h-3.5 w-3.5 text-zinc-400" aria-hidden="true" />
          <span className="text-xs font-medium text-zinc-200">Board review</span>
        </div>
        <span className="font-mono text-[9px] text-zinc-600">4 sections</span>
      </div>
      <div className="divide-y divide-white/[0.06] px-4">
        {sections.map((section, index) => (
          <div key={section} className="flex items-center gap-3 py-3 text-xs text-zinc-400">
            <span className="font-mono text-[9px] text-zinc-700">0{index + 1}</span>
            {section}
            <Check className="ml-auto h-3.5 w-3.5 text-zinc-500" aria-label="Complete" />
          </div>
        ))}
      </div>
    </div>
  );
}

function ArtifactRail({ mode }: { mode: WorkspaceMode }) {
  if (mode === "prepare") {
    return (
      <>
        <p className="font-mono text-[9px] uppercase tracking-[0.14em] text-zinc-600">Sources</p>
        <div className="mt-3 divide-y divide-white/[0.06] border-y border-white/[0.07]">
          {sourceRows.map((source) => (
            <div key={source.name} className="flex items-center gap-2 py-3">
              <FileSpreadsheet className="h-3.5 w-3.5 shrink-0 text-zinc-500" aria-hidden="true" />
              <div className="min-w-0">
                <p className="truncate font-mono text-[10px] text-zinc-300">{source.name}</p>
                <p className="mt-0.5 text-[9px] text-zinc-600">{source.meta}</p>
              </div>
            </div>
          ))}
        </div>
        <p className="mt-6 font-mono text-[9px] uppercase tracking-[0.14em] text-zinc-600">Prepared output</p>
        <div className="mt-3 rounded-md border border-primary/30 bg-primary/[0.06] p-3">
          <div className="flex items-center gap-2 text-xs text-white"><Table2 className="h-4 w-4 text-primary" />sales_clean</div>
          <p className="mt-2 text-[10px] leading-4 text-zinc-500">Selected for downstream work</p>
        </div>
      </>
    );
  }

  if (mode === "visualize") {
    return (
      <>
        <p className="font-mono text-[9px] uppercase tracking-[0.14em] text-zinc-600">Dashboard artifacts</p>
        <div className="mt-3 divide-y divide-white/[0.06] border-y border-white/[0.07]">
          {["Revenue by region", "Quarterly trend", "Margin KPI", "Order volume"].map((item, index) => (
            <div key={item} className="flex items-center gap-2 py-3 text-[11px] text-zinc-400">
              <BarChart3 className="h-3.5 w-3.5 text-zinc-500" aria-hidden="true" />
              <span className="flex-1">{item}</span>
              <span className="font-mono text-[9px] text-zinc-700">0{index + 1}</span>
            </div>
          ))}
        </div>
        <div className="mt-6 border-l border-white/20 pl-3">
          <p className="text-xs font-medium text-zinc-300">APAC leads</p>
          <p className="mt-1 text-[10px] leading-4 text-zinc-600">Highest net revenue and strongest quarterly gain.</p>
        </div>
      </>
    );
  }

  return (
    <>
      <p className="font-mono text-[9px] uppercase tracking-[0.14em] text-zinc-600">Report outputs</p>
      <div className="mt-3 grid grid-cols-2 gap-2">
        {[
          { label: "HTML", icon: FileOutput },
          { label: "PDF", icon: FileOutput },
          { label: "PPTX", icon: Presentation },
          { label: "DOCX", icon: FileOutput },
        ].map(({ label, icon: Icon }) => (
          <button key={label} type="button" className="flex h-16 flex-col items-start justify-between rounded-md border border-white/[0.08] p-3 text-[10px] text-zinc-400 transition-colors duration-300 hover:border-primary/40 hover:bg-primary/[0.06] hover:text-primary">
            <Icon className="h-3.5 w-3.5" aria-hidden="true" />
            {label}
          </button>
        ))}
      </div>
      <div className="mt-6 border-t border-white/[0.07] pt-4">
        <p className="text-xs text-zinc-300">Board review</p>
        <p className="mt-1 font-mono text-[9px] text-zinc-600">Based on sales_clean</p>
      </div>
    </>
  );
}

export const Capabilities: FC = () => {
  const [activeMode, setActiveMode] = useState<WorkspaceMode>("prepare");
  const content = modeCopy[activeMode];

  return (
    <section id="section-workspace" className="relative w-full bg-[#030303] px-4 py-24 sm:px-6 lg:px-10 lg:py-32">
      <div className="mx-auto w-full max-w-[1440px]">
        <div className="grid gap-8 lg:grid-cols-12 lg:items-end">
          <div className="lg:col-span-7">
            <p className="font-mono text-[10px] font-medium uppercase tracking-[0.16em] text-zinc-500">The working surface</p>
            <h2 className="mt-4 max-w-4xl font-display text-4xl font-semibold leading-tight text-white sm:text-5xl lg:text-6xl">
              Chat stays central. The right context changes with the work.
            </h2>
          </div>
          <p className="max-w-xl text-sm leading-6 text-zinc-400 sm:text-base lg:col-span-5">
            The same conversation shell follows every stage. Tool calls appear only when a task needs them, traces stay inspectable, and temporary artifacts remain in chat until you choose to save them.
          </p>
        </div>

        <div className="mt-14 overflow-hidden rounded-lg border border-white/[0.1] bg-[#080808] shadow-[0_24px_90px_rgba(0,0,0,0.55)]">
          <div className="flex min-h-14 flex-wrap items-center gap-3 border-b border-white/[0.08] px-3 py-2 sm:px-4">
            <div className="flex min-w-0 items-center gap-2 sm:w-48">
              <Folder className="h-4 w-4 shrink-0 text-zinc-500" aria-hidden="true" />
              <span className="truncate text-xs font-medium text-zinc-300">Global sales</span>
            </div>

            <div className="order-3 grid w-full grid-cols-3 rounded-md border border-white/[0.08] bg-black p-1 sm:order-none sm:mx-auto sm:w-auto">
              {modes.map((mode) => {
                const Icon = mode.icon;
                const selected = activeMode === mode.id;
                return (
                  <button
                    key={mode.id}
                    type="button"
                    onClick={() => setActiveMode(mode.id)}
                    className={`inline-flex h-8 items-center justify-center gap-2 rounded px-3 text-[11px] font-medium transition-colors duration-300 sm:min-w-28 ${selected ? "bg-primary text-primary-foreground" : "text-zinc-500 hover:bg-white/[0.05] hover:text-zinc-200"}`}
                    aria-pressed={selected}
                  >
                    <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                    {mode.label}
                  </button>
                );
              })}
            </div>

            <div className="ml-auto flex items-center gap-2 text-[10px] text-zinc-500 sm:w-48 sm:justify-end">
              <span className="h-1.5 w-1.5 rounded-full bg-primary" aria-hidden="true" />
              sales_clean selected
            </div>
          </div>

          <div className="grid lg:grid-cols-[190px_minmax(0,1fr)_280px] xl:grid-cols-[210px_minmax(0,1fr)_310px]">
            <aside className="hidden border-r border-white/[0.08] bg-[#060606] p-4 lg:block" aria-label="Project navigation">
              <p className="font-mono text-[9px] uppercase tracking-[0.14em] text-zinc-700">Project</p>
              <div className="mt-3 space-y-1">
                {["Overview", "Global sales", "Customer health", "Forecasting"].map((item, index) => (
                  <div key={item} className={`flex h-9 items-center gap-2 rounded px-2 text-[11px] ${index === 1 ? "bg-primary/10 text-primary" : "text-zinc-600"}`}>
                    <Folder className="h-3.5 w-3.5" aria-hidden="true" />
                    {item}
                  </div>
                ))}
              </div>
              <div className="mt-7 border-t border-white/[0.07] pt-4">
                <p className="font-mono text-[9px] uppercase tracking-[0.14em] text-zinc-700">History</p>
                <div className="mt-3 flex items-center gap-2 text-[11px] text-zinc-600"><MessageSquare className="h-3.5 w-3.5" />Regional analysis</div>
              </div>
            </aside>

            <div className="flex min-h-[650px] min-w-0 flex-col bg-black/35">
              <div className="flex h-14 items-center justify-between border-b border-white/[0.07] px-4 sm:px-5">
                <div>
                  <p className="text-xs font-medium text-zinc-200">{content.title}</p>
                  <p className="mt-0.5 font-mono text-[9px] text-zinc-700">Agent session / Global sales</p>
                </div>
                <button type="button" className="inline-flex h-8 w-8 items-center justify-center rounded-md text-zinc-600 transition-colors duration-300 hover:bg-white/[0.04] hover:text-zinc-300" aria-label="Open session history" title="Session history">
                  <History className="h-4 w-4" />
                </button>
              </div>

              <AnimatePresence mode="wait">
                <motion.div
                  key={activeMode}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -6 }}
                  transition={{ duration: 0.32, ease: [0.16, 1, 0.3, 1] }}
                  className="flex-1 overflow-hidden px-4 py-6 sm:px-6"
                >
                  <div className="ml-auto max-w-[82%] rounded-md border border-white/[0.09] bg-white/[0.055] px-4 py-3 text-sm leading-6 text-zinc-300 sm:max-w-[70%]">
                    {content.prompt}
                  </div>

                  <div className="mt-7 max-w-3xl">
                    <div className="flex items-center gap-2">
                      <span className="flex h-6 w-6 items-center justify-center rounded-full border border-primary/40 bg-primary/10 text-[9px] font-semibold text-primary">EH</span>
                      <span className="text-xs font-medium text-zinc-300">EventHorizon</span>
                    </div>
                    <p className="mt-3 text-sm leading-6 text-zinc-400">{content.response}</p>
                    <ToolTrace mode={activeMode} />
                    {activeMode === "prepare" && <PrepareResult />}
                    {activeMode === "visualize" && <VisualizeResult />}
                    {activeMode === "publish" && <PublishResult />}
                  </div>
                </motion.div>
              </AnimatePresence>

              <div className="border-t border-white/[0.07] p-3 sm:p-4">
                <div className="flex min-h-12 items-center gap-2 rounded-md border border-white/[0.1] bg-[#090909] px-2 transition-colors duration-300 focus-within:border-primary/50">
                  <button type="button" className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded text-zinc-600 transition-colors duration-300 hover:bg-white/[0.04] hover:text-zinc-300" aria-label="Attach context" title="Attach context">
                    <Paperclip className="h-4 w-4" />
                  </button>
                  <span className="min-w-0 flex-1 truncate text-xs text-zinc-600">Ask about the selected table...</span>
                  <button type="button" className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded bg-primary text-primary-foreground transition-colors duration-300 hover:bg-primary/90" aria-label="Send message" title="Send message">
                    <Send className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            </div>

            <aside className="border-t border-white/[0.08] bg-[#060606] p-4 sm:p-5 lg:border-l lg:border-t-0" aria-label="Mode artifacts">
              <div className="flex items-center justify-between border-b border-white/[0.07] pb-4">
                <div className="flex items-center gap-2">
                  <Database className="h-3.5 w-3.5 text-zinc-500" aria-hidden="true" />
                  <span className="text-xs font-medium text-zinc-300">{activeMode === "prepare" ? "Data" : activeMode === "visualize" ? "Dashboard" : "Report"}</span>
                </div>
                <MoreHorizontal className="h-4 w-4 text-zinc-700" aria-hidden="true" />
              </div>
              <div className="pt-5"><ArtifactRail mode={activeMode} /></div>
            </aside>
          </div>
        </div>
      </div>
    </section>
  );
};