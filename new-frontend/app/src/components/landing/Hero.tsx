import type { FC } from "react";
import { motion } from "motion/react";
import { ArrowDown, ArrowRight, FolderKanban } from "lucide-react";

interface HeroProps {
  onLaunch: () => void;
}

const reveal = {
  hidden: { opacity: 0, y: 18 },
  visible: { opacity: 1, y: 0 },
};

export const Hero: FC<HeroProps> = ({ onLaunch }) => {
  return (
    <section
      id="section-hero"
      className="relative flex min-h-[96svh] w-full items-end overflow-hidden px-4 pb-6 pt-24 sm:px-6 lg:px-10"
    >
      <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(90deg,rgba(0,0,0,0.78)_0%,rgba(0,0,0,0.28)_56%,rgba(0,0,0,0.08)_100%)]" />

      <div className="relative mx-auto flex w-full max-w-[1440px] flex-col justify-end">
        <div className="max-w-3xl pb-12 sm:pb-16 lg:pb-20">
          <motion.div
            initial="hidden"
            animate="visible"
            variants={reveal}
            transition={{ duration: 0.7, delay: 0.1, ease: [0.16, 1, 0.3, 1] }}
            className="mb-6 flex items-center gap-3"
          >
            <span className="h-px w-8 bg-primary/70" aria-hidden="true" />
            <span className="font-mono text-[10px] font-medium uppercase tracking-[0.18em] text-zinc-400">
              AI data workspace
            </span>
          </motion.div>

          <motion.h1
            initial="hidden"
            animate="visible"
            variants={reveal}
            transition={{ duration: 0.85, delay: 0.18, ease: [0.16, 1, 0.3, 1] }}
            className="font-display text-5xl font-semibold leading-[0.96] text-white sm:text-6xl md:text-7xl lg:text-8xl"
            id="hero-title"
          >
            EventHorizon
          </motion.h1>

          <motion.p
            initial="hidden"
            animate="visible"
            variants={reveal}
            transition={{ duration: 0.8, delay: 0.28, ease: [0.16, 1, 0.3, 1] }}
            className="mt-6 max-w-2xl font-display text-2xl font-medium leading-tight text-zinc-200 sm:text-3xl md:text-4xl"
          >
            Turn scattered data into one prepared table, clear visualizations, and publishable reports.
          </motion.p>

          <motion.p
            initial="hidden"
            animate="visible"
            variants={reveal}
            transition={{ duration: 0.8, delay: 0.36, ease: [0.16, 1, 0.3, 1] }}
            className="mt-5 max-w-xl text-sm leading-6 text-zinc-400 sm:text-base"
            id="hero-description"
          >
            Work with an agent inside each project folder. Sources stay available in Prepare,
            the saved table unlocks Visualize, and every chart and report traces back to that table.
          </motion.p>

          <motion.div
            initial="hidden"
            animate="visible"
            variants={reveal}
            transition={{ duration: 0.8, delay: 0.44, ease: [0.16, 1, 0.3, 1] }}
            className="mt-8 flex flex-col gap-3 sm:flex-row"
            id="hero-actions"
          >
            <button
              type="button"
              onClick={onLaunch}
              className="inline-flex h-12 items-center justify-center gap-2 rounded-md bg-primary px-5 text-sm font-semibold text-primary-foreground shadow-[0_12px_36px_rgba(193,110,67,0.16)] transition-colors duration-300 hover:bg-primary/90"
            >
              Create a workspace
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </button>
            <button
              type="button"
              onClick={() => document.getElementById("section-workflow")?.scrollIntoView({ behavior: "smooth" })}
              className="inline-flex h-12 items-center justify-center gap-2 rounded-md border border-white/15 bg-black/20 px-5 text-sm font-medium text-zinc-200 backdrop-blur-md transition-colors duration-300 hover:border-white/30 hover:bg-white/[0.06] hover:text-white"
            >
              Explore the workflow
              <ArrowDown className="h-4 w-4" aria-hidden="true" />
            </button>
          </motion.div>
        </div>

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.8, delay: 0.58 }}
          className="grid border-y border-white/[0.09] bg-black/35 backdrop-blur-md sm:grid-cols-[1.2fr_1fr_1fr]"
        >
          <div className="flex min-h-16 items-center gap-3 px-4 py-3 sm:px-5">
            <FolderKanban className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
            <div>
              <p className="text-xs font-medium text-white">Folder-scoped context</p>
              <p className="mt-0.5 text-[11px] text-zinc-500">Sources and artifacts stay together</p>
            </div>
          </div>
          <div className="border-t border-white/[0.07] px-4 py-3 sm:border-l sm:border-t-0 sm:px-5">
            <p className="font-mono text-[9px] uppercase tracking-[0.14em] text-zinc-600">Core flow</p>
            <p className="mt-1 text-xs text-zinc-300">Prepare → Visualize → Publish</p>
          </div>
          <div className="border-t border-white/[0.07] px-4 py-3 sm:border-l sm:border-t-0 sm:px-5">
            <p className="font-mono text-[9px] uppercase tracking-[0.14em] text-zinc-600">Outputs</p>
            <p className="mt-1 text-xs text-zinc-300">Dashboards · PDF · PPTX · DOCX</p>
          </div>
        </motion.div>
      </div>
    </section>
  );
};