import type { FC } from "react";
import { motion } from "motion/react";
import { ArrowRight, FileCheck2, GitBranch, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";

interface ClosingCTAProps {
  onLaunch?: () => void;
}

const principles = [
  { title: "Explicit saves", detail: "Draft charts stay in chat until you add them.", icon: FileCheck2 },
  { title: "Visible lineage", detail: "Reports trace back to the selected prepared table.", icon: GitBranch },
  { title: "Scoped access", detail: "Each agent receives only the context its mode needs.", icon: ShieldCheck },
];

export const ClosingCTA: FC<ClosingCTAProps> = ({ onLaunch }) => {
  return (
    <section id="section-outputs" className="relative w-full border-t border-white/[0.08] bg-black px-4 pt-24 sm:px-6 lg:px-10 lg:pt-32">
      <div className="mx-auto w-full max-w-[1440px]">
        <div className="grid border-y border-white/[0.08] sm:grid-cols-3">
          {principles.map((principle, index) => {
            const Icon = principle.icon;
            return (
              <div key={principle.title} className={`flex min-h-32 gap-4 px-4 py-6 sm:px-6 ${index > 0 ? "border-t border-white/[0.08] sm:border-l sm:border-t-0" : ""}`}>
                <Icon className="mt-0.5 h-4 w-4 shrink-0 text-zinc-500" aria-hidden="true" />
                <div>
                  <p className="text-sm font-medium text-zinc-200">{principle.title}</p>
                  <p className="mt-2 text-xs leading-5 text-zinc-600">{principle.detail}</p>
                </div>
              </div>
            );
          })}
        </div>

        <motion.div
          initial={{ opacity: 0, y: 18 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.4 }}
          transition={{ duration: 0.75, ease: [0.16, 1, 0.3, 1] }}
          className="flex min-h-[62svh] flex-col items-center justify-center py-24 text-center"
        >
          <p className="font-mono text-[10px] font-medium uppercase tracking-[0.16em] text-zinc-600">Begin with your data</p>
          <h2 className="mt-5 max-w-4xl font-display text-4xl font-semibold leading-tight text-white sm:text-5xl lg:text-7xl">
            Start with a folder. Leave with a decision.
          </h2>
          <p className="mt-6 max-w-xl text-sm leading-6 text-zinc-500 sm:text-base">
            Prepare the table once, then keep analysis, dashboards, and reports connected inside the same workspace.
          </p>
          <div className="mt-9 flex w-full max-w-sm flex-col justify-center gap-3 sm:max-w-none sm:flex-row">
            <button
              type="button"
              onClick={onLaunch}
              className="inline-flex h-12 items-center justify-center gap-2 rounded-md bg-primary px-5 text-sm font-semibold text-primary-foreground shadow-[0_12px_36px_rgba(193,110,67,0.14)] transition-colors duration-300 hover:bg-primary/90"
            >
              Create a workspace
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </button>
            <Link
              to="/login"
              className="inline-flex h-12 items-center justify-center rounded-md border border-white/15 px-5 text-sm font-medium text-zinc-300 transition-colors duration-300 hover:border-white/30 hover:bg-white/[0.04] hover:text-white"
            >
              Log in
            </Link>
          </div>
        </motion.div>

        <footer className="flex flex-col gap-5 border-t border-white/[0.08] py-7 text-[10px] text-zinc-700 sm:flex-row sm:items-center sm:justify-between">
          <div className="font-mono">EVENTHORIZON / 2026</div>
          <nav className="flex flex-wrap gap-5" aria-label="Footer navigation">
            <a href="#section-workflow" className="transition-colors duration-300 hover:text-zinc-400">Workflow</a>
            <a href="#section-workspace" className="transition-colors duration-300 hover:text-zinc-400">Workspace</a>
            <Link to="/login" className="transition-colors duration-300 hover:text-zinc-400">Log in</Link>
          </nav>
        </footer>
      </div>
    </section>
  );
};