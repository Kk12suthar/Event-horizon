import type { FC } from "react";
import { motion } from "motion/react";

interface NavbarProps {
  /** Optional handler for the primary CTA. Falls back to in-page scroll when omitted. */
  onLaunch?: () => void;
}

export const Navbar: FC<NavbarProps> = ({ onLaunch }) => {
  const scrollToSection = (id: string) => {
    const element = document.getElementById(id);
    if (element) {
      element.scrollIntoView({ behavior: "smooth" });
    }
  };

  return (
    <motion.header
      initial={{ y: -30, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
      className="fixed top-0 left-0 right-0 z-50 px-6 py-4 bg-void/35 backdrop-blur-xl border-b border-white/[0.03] flex justify-between items-center"
      id="navbar-container"
    >
      <div className="flex items-center gap-12">
        {/* Animated Brand Logo */}
        <a
          href="#"
          className="group flex items-center gap-3 font-display font-bold text-xs tracking-[0.4em] uppercase text-white hover:opacity-90"
          id="nav-logo"
        >
          <div className="relative w-6 h-6 flex items-center justify-center">
            {/* Spinning external ring */}
            <span className="absolute inset-0 border border-white/20 rounded-full group-hover:border-plasma-orange/50 group-hover:scale-110 transition-all duration-500 animate-spin-slower" />
            {/* Accretion disk light bar */}
            <span className="absolute w-4 h-[1.5px] bg-gradient-to-r from-plasma-orange via-plasma-purple to-transparent transform rotate-45 group-hover:rotate-[225deg] transition-transform duration-700" />
            {/* Core singularity */}
            <span className="absolute w-2 h-2 bg-black rounded-full border border-white/30 group-hover:border-plasma-orange/60" />
          </div>
          <span className="relative">
            EventHorizon
          </span>
        </a>

        {/* Navigation Menu */}
        <nav className="hidden md:flex items-center gap-8 font-display text-[11px] font-medium tracking-widest uppercase opacity-80" id="nav-menu">
          {[
            { label: "Sources", id: "section-pull" },
            { label: "Prepare", id: "section-transform" },
            { label: "Workspace", id: "section-capabilities" },
          ].map((item) => (
            <button
              key={item.id}
              onClick={() => scrollToSection(item.id)}
              className="text-zinc-400 hover:text-white tracking-widest relative py-1 transition-colors duration-300 cursor-pointer text-[11px] uppercase font-display"
            >
              {item.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Action CTA with magnetic-like hovering state */}
      <div className="flex items-center gap-4" id="nav-actions">
        
        <button
          onClick={() => (onLaunch ? onLaunch() : scrollToSection("section-cta"))}
          className="px-6 py-2 border border-white/20 rounded-full text-[10px] tracking-widest uppercase bg-transparent text-white hover:bg-white hover:text-black transition-all duration-300 font-mono cursor-pointer"
          id="btn-nav-cta"
        >
          GET STARTED
        </button>
      </div>
    </motion.header>
  );
};
