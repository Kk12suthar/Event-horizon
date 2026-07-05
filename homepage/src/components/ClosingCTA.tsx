import React, { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { ArrowRight, CornerDownRight, Radio, Star, Terminal } from "lucide-react";

export const ClosingCTA: React.FC = () => {
  const [email, setEmail] = useState<string>("");
  const [submitted, setSubmitted] = useState<boolean>(false);
  const [isWarping, setIsWarping] = useState<boolean>(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) return;

    // Trigger cool cinematic warp transition
    setIsWarping(true);
    setTimeout(() => {
      setSubmitted(true);
      setIsWarping(false);
    }, 1500);
  };

  return (
    <section
      id="section-cta"
      className="relative min-h-[90vh] w-full flex flex-col justify-center items-center py-24 px-6 z-10 overflow-hidden"
    >
      {/* Absolute dark gravitational center shadow echoing the hero */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[300px] h-[300px] rounded-full bg-black border border-white/[0.04] shadow-[0_0_120px_rgba(255,92,0,0.1)] flex items-center justify-center pointer-events-none">
        <div className="w-12 h-12 rounded-full border border-plasma-orange/20 animate-ping opacity-30" />
      </div>

      {/* Galactic ambient glow */}
      <div className="absolute top-[45%] left-[50%] -translate-x-1/2 -translate-y-1/2 w-full max-w-[500px] h-[350px] bg-gradient-to-tr from-plasma-orange/5 to-transparent rounded-full filter blur-[120px] pointer-events-none" />

      <div className="w-full max-w-3xl text-center space-y-12 relative z-10">
        
        {/* Confident final heading */}
        <div className="space-y-4">
          <motion.h2
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
            className="font-display font-semibold text-4xl md:text-6xl text-white tracking-tight uppercase"
            id="cta-title"
          >
            Ready to Cross
            <span className="block bg-clip-text text-transparent bg-gradient-to-r from-white via-plasma-orange to-plasma-orange text-glow-orange leading-tight">
              The Horizon?
            </span>
          </motion.h2>

          <motion.p
            initial={{ opacity: 0, y: 15 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 1.2, delay: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className="text-zinc-500 text-xs md:text-sm max-w-md mx-auto font-sans leading-relaxed"
            id="cta-description"
          >
            Step into perfect structured alignment. Connect your data, activate the lensed
            core, and experience zero information decay.
          </motion.p>
        </div>

        {/* Email Portal Form */}
        <AnimatePresence mode="wait">
          {!submitted ? (
            <motion.form
              key="cta-form"
              onSubmit={handleSubmit}
              initial={{ opacity: 0, y: 10 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.8, delay: 0.3 }}
              className="max-w-md mx-auto w-full"
              id="cta-form"
            >
              <div className="relative flex items-center p-1.5 bg-coal border border-white/[0.08] hover:border-white/20 rounded-xl focus-within:border-plasma-orange/60 transition-all duration-300 shadow-2xl">
                <input
                  type="email"
                  required
                  placeholder="enter.coordinate@email.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="flex-1 bg-transparent border-0 outline-0 px-4 py-2 font-mono text-xs text-white placeholder-zinc-600 focus:ring-0"
                />
                
                <button
                  type="submit"
                  disabled={isWarping}
                  className="px-5 py-2.5 bg-white hover:bg-plasma-orange hover:text-white text-black font-mono text-[10px] font-medium tracking-widest uppercase rounded-full transition-all duration-300 flex items-center gap-1.5 relative overflow-hidden cursor-pointer"
                >
                  {isWarping ? (
                    "WARPING..."
                  ) : (
                    <>
                      ACCELERATE <ArrowRight className="w-3.5 h-3.5" />
                    </>
                  )}
                </button>
              </div>

              {/* Console note below portal */}
              <div className="mt-3 flex items-center justify-center gap-2 text-[9px] font-mono text-zinc-600">
                <Terminal className="w-3 h-3 text-zinc-700" />
                <span>INITIATES SECURE GRAVITY SYNC INSTANCE</span>
              </div>
            </motion.form>
          ) : (
            /* Horizon crossing success warp confirmation */
            <motion.div
              key="cta-success"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ type: "spring", stiffness: 100, damping: 15 }}
              className="p-6 md:p-8 bg-coal border border-plasma-orange/20 rounded-2xl max-w-md mx-auto space-y-4 glow-orange text-left"
              id="cta-success-box"
            >
              <div className="flex items-center gap-3">
                <div className="p-2 bg-plasma-orange/10 border border-plasma-orange/30 rounded-lg">
                  <Radio className="w-5 h-5 text-plasma-orange animate-pulse" />
                </div>
                <div className="space-y-0.5">
                  <span className="block font-mono text-[9px] tracking-widest text-plasma-orange font-semibold">
                    WARP STAGE: COMPLETE
                  </span>
                  <h4 className="text-sm font-display font-medium text-white uppercase tracking-tight">
                    Horizon Bridge Active
                  </h4>
                </div>
              </div>

              <div className="p-3.5 bg-void rounded-lg font-mono text-[10px] text-zinc-400 space-y-1">
                <div className="flex items-center gap-1">
                  <CornerDownRight className="w-3.5 h-3.5 text-zinc-600" />
                  <span>Target Coordinate: <span className="text-white font-semibold">{email}</span></span>
                </div>
                <div className="flex items-center gap-1">
                  <CornerDownRight className="w-3.5 h-3.5 text-zinc-600" />
                  <span>Geodesic Token: <span className="text-plasma-purple font-semibold">0xEH_WARP_INIT_82A</span></span>
                </div>
                <div className="flex items-center gap-1">
                  <CornerDownRight className="w-3.5 h-3.5 text-zinc-600" />
                  <span>Sync Status: <span className="text-emerald-400 font-semibold">ESTABLISHED</span></span>
                </div>
              </div>

              <p className="text-[10px] text-zinc-500 font-sans leading-relaxed">
                Platform bridge coordinates have been successfully locked. Check your temporal mailbox shortly for launch authorization protocols.
              </p>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Quiet footer */}
        <div className="pt-24 border-t border-white/[0.03] flex flex-col md:flex-row justify-between items-center gap-4 text-[10px] font-mono text-zinc-600">
          <div>© 2026 EVENTHORIZON INC. ALL DIMENSIONAL RIGHTS RESERVED.</div>
          <div className="flex gap-6">
            <a href="#section-pull" className="hover:text-zinc-400 transition-colors">THE PULL</a>
            <a href="#section-transform" className="hover:text-zinc-400 transition-colors">WARP PORTS</a>
            <a href="#section-capabilities" className="hover:text-zinc-400 transition-colors">INSTRUMENTS</a>
          </div>
        </div>
      </div>
    </section>
  );
};
