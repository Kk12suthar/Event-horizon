import React from "react";
import { motion } from "motion/react";
import { ArrowUpRight, Compass, Shield, Zap } from "lucide-react";

interface HeroProps {
  onBeginUpload: () => void;
}

export const Hero: React.FC<HeroProps> = ({ onBeginUpload }) => {
  return (
    <section
      id="section-hero"
      className="relative min-h-screen w-full flex flex-col justify-center items-center px-6 pt-32 pb-16 z-10 overflow-hidden"
    >
      {/* Decorative gradient overlay behind title */}
      <div className="absolute top-[35%] left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-[600px] h-[300px] bg-gradient-to-r from-plasma-orange/10 to-transparent rounded-full filter blur-[120px] pointer-events-none" />

      {/* Main Hero Content */}
      <div className="flex-1 flex flex-col justify-center items-center text-center max-w-4xl mt-12 md:mt-0">
        {/* Display Typography */}
        <motion.h1
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 1.4, delay: 0.2, ease: [0.16, 1, 0.3, 1] }}
          className="font-display font-bold text-5xl md:text-7xl lg:text-8xl text-white tracking-tight leading-[0.9] uppercase"
          id="hero-title"
        >
          Chaos In.
          <br />
          <span className="bg-clip-text text-transparent bg-gradient-to-r from-white via-plasma-orange to-plasma-orange drop-shadow-sm text-glow-orange">
            Clarity Out.
          </span>
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 1.2, delay: 0.4, ease: [0.16, 1, 0.3, 1] }}
          className="text-zinc-400 text-sm md:text-base max-w-xl mt-8 font-sans leading-relaxed font-light"
          id="hero-description"
        >
          Pulls in raw, high-volume datasets, compresses them through our lensed
          relativistic processing core, and outputs beautifully structured, structured flows in real time.
        </motion.p>

        {/* Hero Actions */}
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 1.2, delay: 0.6, ease: [0.16, 1, 0.3, 1] }}
          className="flex flex-col sm:flex-row items-center gap-4 mt-12 w-full justify-center"
          id="hero-actions"
        >
          <button
            onClick={onBeginUpload}
            className="w-full sm:w-auto px-8 py-4 bg-transparent border border-white/20 hover:border-white hover:bg-white text-white hover:text-black text-xs font-mono font-medium tracking-widest uppercase rounded-full shadow-2xl transition-all duration-300 relative group overflow-hidden cursor-pointer"
          >
            <span className="relative z-10 flex items-center justify-center gap-2">
              PULL IN A DATASET <ArrowUpRight className="w-4 h-4" />
            </span>
          </button>

          <button
            onClick={() => {
              document.getElementById("section-pull")?.scrollIntoView({ behavior: "smooth" });
            }}
            className="w-full sm:w-auto px-8 py-4 bg-white/[0.01] border border-white/[0.05] hover:border-white/20 text-zinc-300 hover:text-white text-xs font-mono font-medium tracking-widest uppercase rounded-full backdrop-blur-md transition-all duration-300 cursor-pointer"
          >
            OBSERVE THE METAPHOR
          </button>
        </motion.div>
      </div>

      {/* Animated scroll prompt */}
      <div className="absolute bottom-12 left-1/2 -translate-x-1/2 flex flex-col items-center gap-1 opacity-40">
        <span className="text-[8px] font-mono tracking-widest text-zinc-500 uppercase">
          SCROLL TO COMPRESS
        </span>
        <div className="w-[1px] h-6 bg-gradient-to-b from-zinc-500 to-transparent relative overflow-hidden">
          <span className="absolute top-0 left-0 right-0 h-2 bg-plasma-orange animate-[bounce_1.5s_infinite]" />
        </div>
      </div>
    </section>
  );
};
