import type { FC } from "react";
import { motion } from "motion/react";
import {
  ArrowRight,
  BarChart3,
  Check,
  FileOutput,
  Files,
  Folder,
  Table2,
} from "lucide-react";

const stages = [
  {
    number: "01",
    name: "Prepare",
    description: "Upload folder sources, ask the agent to inspect, clean, join, and validate them, then save the table you trust.",
    outcome: "One selected table",
    icon: Table2,
  },
  {
    number: "02",
    name: "Visualize",
    description: "The visualization agent works from that selected table to build KPIs, charts, and reusable dashboard views.",
    outcome: "Saved dashboard artifacts",
    icon: BarChart3,
  },
  {
    number: "03",
    name: "Publish",
    description: "Report sections use the same prepared table and saved visuals, keeping every conclusion tied to a common source.",
    outcome: "HTML, PDF, PPTX, DOCX",
    icon: FileOutput,
  },
];

const projectRows = [
  { label: "Sources", detail: "3 files", icon: Files, muted: true },
  { label: "sales_clean", detail: "Prepared table", icon: Table2, active: true },
  { label: "Executive dashboard", detail: "4 saved charts", icon: BarChart3 },
  { label: "Board review", detail: "3 report formats", icon: FileOutput },
];

export const ThePull: FC = () => {
  return (
    <section
      id="section-workflow"
      className="relative w-full border-y border-white/[0.07] bg-black/90 px-4 py-24 backdrop-blur-xl sm:px-6 lg:px-10 lg:py-32"
    >
      <div className="mx-auto w-full max-w-[1440px]">
        <div className="grid gap-12 lg:grid-cols-12 lg:items-end">
          <motion.div
            initial={{ opacity: 0, y: 18 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.35 }}
            transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
            className="lg:col-span-7"
          >
            <p className="font-mono text-[10px] font-medium uppercase tracking-[0.16em] text-zinc-500">
              One continuous data lineage
            </p>
            <h2 className="mt-4 max-w-4xl font-display text-4xl font-semibold leading-tight text-white sm:text-5xl lg:text-6xl">
              One folder. One prepared table. Every output.
            </h2>
          </motion.div>

          <motion.p
            initial={{ opacity: 0, y: 14 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.35 }}
            transition={{ duration: 0.7, delay: 0.1, ease: [0.16, 1, 0.3, 1] }}
            className="max-w-xl text-sm leading-6 text-zinc-400 sm:text-base lg:col-span-5"
          >
            Project folders hold the working context. Sources belong to Prepare; Visualize and Publish unlock only after a prepared table is selected, and both continue from that same table.
          </motion.p>
        </div>

        <div className="mt-16 grid overflow-hidden rounded-lg border border-white/[0.09] bg-[#070707] lg:grid-cols-[0.82fr_1.5fr]">
          <div className="border-b border-white/[0.08] p-5 sm:p-7 lg:border-b-0 lg:border-r">
            <div className="flex items-center gap-2 border-b border-white/[0.08] pb-5">
              <Folder className="h-4 w-4 text-zinc-300" aria-hidden="true" />
              <div className="min-w-0">
                <p className="truncate text-xs font-medium text-white">Revenue Operations</p>
                <p className="mt-0.5 truncate font-mono text-[9px] text-zinc-600">FY26 / Global sales</p>
              </div>
            </div>

            <div className="py-2">
              {projectRows.map((row) => {
                const Icon = row.icon;
                return (
                  <div
                    key={row.label}
                    className={`flex min-h-14 items-center gap-3 border-b border-white/[0.05] px-1 ${row.muted ? "text-zinc-500" : "text-zinc-300"} ${row.active ? "bg-primary/[0.06]" : ""}`}
                  >
                    <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                    <div className="min-w-0 flex-1">
                      <p className={`truncate text-xs ${row.active ? "font-medium text-white" : ""}`}>{row.label}</p>
                      <p className="mt-0.5 truncate font-mono text-[9px] text-zinc-600">{row.detail}</p>
                    </div>
                    {row.active && <Check className="h-3.5 w-3.5 text-primary" aria-label="Selected" />}
                  </div>
                );
              })}
            </div>
          </div>

          <div className="grid sm:grid-cols-3">
            {stages.map((stage, index) => {
              const Icon = stage.icon;
              return (
                <div
                  key={stage.name}
                  className={`relative flex min-h-72 flex-col justify-between p-6 sm:min-h-80 lg:p-7 ${index > 0 ? "border-t border-white/[0.08] sm:border-l sm:border-t-0" : ""}`}
                >
                  <div>
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-[10px] text-zinc-600">{stage.number}</span>
                      <Icon className="h-4 w-4 text-zinc-500" aria-hidden="true" />
                    </div>
                    <h3 className="mt-8 font-display text-xl font-semibold text-white">{stage.name}</h3>
                    <p className="mt-4 text-sm leading-6 text-zinc-500">{stage.description}</p>
                  </div>
                  <div className="mt-8 flex items-center gap-2 border-t border-white/[0.07] pt-4 text-xs text-zinc-300">
                    <span className="h-1.5 w-1.5 rounded-full bg-primary/80" aria-hidden="true" />
                    {stage.outcome}
                  </div>
                  {index < stages.length - 1 && (
                    <ArrowRight className="absolute -right-2.5 top-1/2 z-10 hidden h-5 w-5 -translate-y-1/2 bg-[#070707] text-zinc-600 sm:block" aria-hidden="true" />
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
};