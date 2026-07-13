import { useState, type FC } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ArrowUpRight, Menu, X } from "lucide-react";
import { Link } from "react-router-dom";

interface NavbarProps {
  onLaunch?: () => void;
}

const navigation = [
  { label: "Workflow", id: "section-workflow" },
  { label: "Workspace", id: "section-workspace" },
  { label: "Outputs", id: "section-outputs" },
];

export const Navbar: FC<NavbarProps> = ({ onLaunch }) => {
  const [menuOpen, setMenuOpen] = useState(false);

  const scrollToSection = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
    setMenuOpen(false);
  };

  const launch = () => {
    setMenuOpen(false);
    if (onLaunch) onLaunch();
  };

  return (
    <motion.header
      initial={{ y: -16, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
      className="fixed inset-x-0 top-0 z-50 border-b border-white/[0.07] bg-black/55 backdrop-blur-2xl"
      id="navbar-container"
    >
      <div className="mx-auto flex h-16 w-full max-w-[1440px] items-center justify-between px-4 sm:px-6 lg:px-10">
        <div className="flex items-center gap-10">
          <Link
            to="/"
            className="group flex items-center gap-3 text-white transition-opacity duration-300 hover:opacity-80"
            aria-label="EventHorizon home"
            id="nav-logo"
          >
            <span className="relative flex h-7 w-7 items-center justify-center" aria-hidden="true">
              <span className="absolute inset-0 rounded-full border border-white/35 transition-all duration-700 group-hover:rotate-45 group-hover:border-primary/60" />
              <span className="absolute h-px w-6 rotate-[-18deg] bg-primary/80" />
              <span className="absolute h-2.5 w-2.5 rounded-full border border-white/50 bg-black" />
            </span>
            <span className="font-display text-[13px] font-semibold tracking-[0.12em]">
              EventHorizon
            </span>
          </Link>

          <nav className="hidden items-center gap-7 lg:flex" aria-label="Landing sections">
            {navigation.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => scrollToSection(item.id)}
                className="py-2 font-sans text-xs font-medium text-zinc-500 transition-colors duration-300 hover:text-white"
              >
                {item.label}
              </button>
            ))}
          </nav>
        </div>

        <div className="hidden items-center gap-5 sm:flex">
          <Link
            to="/login"
            className="text-xs font-medium text-zinc-400 transition-colors duration-300 hover:text-white"
          >
            Log in
          </Link>
          <button
            type="button"
            onClick={launch}
            className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-4 text-xs font-semibold text-primary-foreground shadow-[0_8px_24px_rgba(193,110,67,0.16)] transition-colors duration-300 hover:bg-primary/90"
            id="btn-nav-cta"
          >
            Open workspace
            <ArrowUpRight className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        </div>

        <button
          type="button"
          onClick={() => setMenuOpen((open) => !open)}
          className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-white/10 text-zinc-300 transition-colors duration-300 hover:border-white/25 hover:text-white sm:hidden"
          aria-label={menuOpen ? "Close navigation" : "Open navigation"}
          aria-expanded={menuOpen}
          title={menuOpen ? "Close navigation" : "Open navigation"}
        >
          {menuOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
        </button>
      </div>

      <AnimatePresence>
        {menuOpen && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
            className="overflow-hidden border-t border-white/[0.07] bg-black/95 sm:hidden"
          >
            <nav className="flex flex-col px-4 py-3" aria-label="Mobile landing sections">
              {navigation.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => scrollToSection(item.id)}
                  className="border-b border-white/[0.06] px-1 py-3 text-left text-sm text-zinc-300"
                >
                  {item.label}
                </button>
              ))}
              <div className="grid grid-cols-2 gap-2 pt-3">
                <Link
                  to="/login"
                  className="inline-flex h-10 items-center justify-center rounded-md border border-white/15 text-xs font-medium text-white"
                >
                  Log in
                </Link>
                <button
                  type="button"
                  onClick={launch}
                  className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-primary text-xs font-semibold text-primary-foreground"
                >
                  Open
                  <ArrowUpRight className="h-3.5 w-3.5" />
                </button>
              </div>
            </nav>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.header>
  );
};