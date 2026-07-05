import React, { useState, useRef, useEffect } from "react";
import { motion } from "motion/react";
import { ChevronsLeftRight, Database, GitMerge, Grid, RefreshCw, Sparkles, TrendingUp } from "lucide-react";

export const TheTransformation: React.FC = () => {
  const [sliderPos, setSliderPos] = useState<number>(50); // percentage (0 to 100)
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const containerRef = useRef<HTMLDivElement>(null);
  
  const [chartProgress, setChartProgress] = useState<number>(0);
  
  // Animate standard chart curves to feel "alive with motion"
  useEffect(() => {
    let animId: number;
    const animate = () => {
      setChartProgress((prev) => (prev + 0.01) % (Math.PI * 2));
      animId = requestAnimationFrame(animate);
    };
    animate();
    return () => cancelAnimationFrame(animId);
  }, []);

  // Handle Dragging Slider
  const handleMove = (clientX: number) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x = clientX - rect.left;
    const pct = Math.max(0, Math.min(100, (x / rect.width) * 100));
    setSliderPos(pct);
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    if (e.touches[0]) {
      handleMove(e.touches[0].clientX);
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (e.buttons === 1 || isDragging) {
      handleMove(e.clientX);
    }
  };

  // Scrambled data generator for the "Chaos" side
  const scrambledLines = [
    `{"status":"ERR_DISRUPT","nodes":[{"id":NaN,"val":"_undef_","raw":0xFA9B32},{"entropy":999.8}]}`,
    `[TRACE] STACK_OVERFLOW_COLLAPSE: unstable_gravity=9.8c² --abort-packet-drop`,
    `01001100 01000101 01001110 01010011 01001001 01001110 01000111`,
    `UNSORTED_RAW_GRID_ENTROPY: [x:0.129, y:NaN, z:-9.221, rot_phi:359.88, speed:99c]`,
    `0xFF9A: { "system_err": true, "message": "relativistic_temporal_decay_overflow" }`,
    `<<REORG_FAIL_COORDS_X>> :: -0.897412 :: -1.112349 :: -123.8812739`,
    `[CHAOS_BURST] payload_jitter=88.42% --entropy-threshold=exceeded`,
  ];

  // Perfect structured data for the "Clarity" side
  const cleanDataRecords = [
    { id: "EH-9820", metric: "Gravity Index", value: "1.414 c²", status: "Nominal" },
    { id: "EH-9821", metric: "Redshift Ratio", value: "2.718 z", status: "Aligned" },
    { id: "EH-9822", metric: "Entropy Capture", value: "99.982%", status: "Optimal" },
    { id: "EH-9823", metric: "Platform Yield", value: "982 Gigaflops", status: "Nominal" },
  ];

  return (
    <section
      id="section-transform"
      className="relative min-h-screen w-full flex flex-col justify-center items-center py-24 px-6 z-10 border-b border-white/[0.02]"
    >
      <div className="w-full max-w-7xl flex flex-col items-center space-y-16">
        {/* Editorial Heading */}
        <div className="text-center max-w-2xl space-y-4">
          <div className="inline-flex items-center gap-2 px-3 py-1 bg-white/[0.02] border border-white/[0.05] rounded-full">
            <Sparkles className="w-3.5 h-3.5 text-plasma-orange" />
            <span className="font-mono text-[9px] tracking-widest text-zinc-400 uppercase">
              Phase 02 :: Crossing the Horizon
            </span>
          </div>

          <h2 className="font-display font-semibold text-3xl md:text-5xl text-white tracking-tight uppercase">
            The Transformation
            <span className="block text-zinc-500 font-light text-xl md:text-2xl mt-2 lowercase font-sans">
              structured coherence in real-time
            </span>
          </h2>

          <p className="text-zinc-400 text-sm font-sans leading-relaxed font-light">
            As data crosses the event horizon boundary, chaotic gravity decays into 
            perfect thermodynamic alignment. Watch how noisy, scrambled packets are instantly
            compressed, parsed, and emerged as pristine analytical structures on the other side.
          </p>
        </div>

        {/* Interactive Slider Split Screen Component */}
        <div
          ref={containerRef}
          onMouseMove={handleMouseMove}
          onTouchMove={handleTouchMove}
          onMouseDown={() => setIsDragging(true)}
          onMouseUp={() => setIsDragging(false)}
          onMouseLeave={() => setIsDragging(false)}
          className="relative w-full h-[450px] md:h-[500px] bg-coal border border-white/[0.05] rounded-2xl overflow-hidden select-none cursor-ew-resize noise-bg"
          id="transformation-slider-container"
        >
          {/* LEFT PANEL: CHAOTIC ENTROPY STATE (Static/Noisy) */}
          <div className="absolute inset-0 w-full h-full bg-void flex flex-col p-6 pr-12 md:p-10">
            <div className="flex items-center gap-2 mb-6">
              <RefreshCw className="w-4 h-4 text-plasma-purple animate-spin-slow" />
              <span className="font-mono text-xs tracking-widest text-plasma-purple font-semibold uppercase">
                STATE: HIGH ENTROPY CHAOS (0.00% SYNC)
              </span>
            </div>

            <div className="flex-1 font-mono text-[10px] md:text-xs text-zinc-600 space-y-4 leading-relaxed select-none">
              {scrambledLines.map((line, idx) => (
                <div key={idx} className="font-mono tracking-wide flex items-start gap-4">
                  <span className="text-zinc-800">[{1000 + idx * 82}]</span>
                  <p className="truncate text-red-500/60 font-mono italic">
                    {line}
                  </p>
                </div>
              ))}

              {/* Glowing decorative warp grid representation in chaos */}
              <div 
                className="absolute w-64 h-64 border border-plasma-purple/15 rounded-full filter blur-xl animate-pulse"
                style={{ left: "10%", bottom: "10%" }}
              />
            </div>
          </div>

          {/* RIGHT PANEL: CLEAN STRUCTURED STATE (Revealed dynamically via slider width clipPath) */}
          <div
            className="absolute inset-0 w-full h-full bg-coal flex flex-col p-6 md:p-10 transition-all"
            style={{
              clipPath: `polygon(${sliderPos}% 0%, 100% 0%, 100% 100%, ${sliderPos}% 100%)`,
            }}
          >
            <div className="flex items-center gap-2 mb-6 justify-end md:justify-start">
              <Database className="w-4 h-4 text-plasma-orange animate-pulse" />
              <span className="font-mono text-xs tracking-widest text-plasma-orange font-semibold uppercase">
                STATE: HORIZON STRUCTURED (99.98% COHERENCY)
              </span>
            </div>

            <div className="flex-1 grid grid-cols-1 md:grid-cols-12 gap-8 items-center" id="clarity-outputs">
              {/* Structured analytics tables */}
              <div className="md:col-span-6 space-y-4">
                <span className="block font-mono text-[10px] text-zinc-500 tracking-wider uppercase">
                  RECORD RECONSTRUCTION
                </span>
                
                <div className="border border-white/[0.05] rounded-lg overflow-hidden bg-void/50 backdrop-blur-md">
                  <table className="w-full text-left font-mono text-[10px] md:text-xs text-zinc-300">
                    <thead>
                      <tr className="bg-white/[0.02] border-b border-white/[0.05] text-zinc-500">
                        <th className="p-3">NODE ID</th>
                        <th className="p-3">METRIC</th>
                        <th className="p-3">VALUE</th>
                        <th className="p-3">STATUS</th>
                      </tr>
                    </thead>
                    <tbody>
                      {cleanDataRecords.map((rec) => (
                        <tr key={rec.id} className="border-b border-white/[0.03] hover:bg-white/[0.01] transition-colors">
                          <td className="p-3 font-semibold text-white">{rec.id}</td>
                          <td className="p-3 text-zinc-400">{rec.metric}</td>
                          <td className="p-3 text-plasma-orange font-medium">{rec.value}</td>
                          <td className="p-3">
                            <span className="px-1.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 text-[8px] font-mono border border-emerald-500/20">
                              {rec.status}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Glowing Dynamic SVG Chart Visualizer */}
              <div className="md:col-span-6 space-y-4">
                <span className="block font-mono text-[10px] text-zinc-500 tracking-wider uppercase flex justify-between">
                  <span>REAL-TIME COHERENCE SIGNAL</span>
                  <span className="text-plasma-orange font-semibold">SIGNAL: HIGH</span>
                </span>

                <div className="border border-white/[0.05] rounded-lg p-4 bg-void/50 backdrop-blur-md h-[180px] flex items-center justify-center relative">
                  <svg className="w-full h-full" viewBox="0 0 300 120" fill="none" xmlns="http://www.w3.org/2000/svg">
                    {/* Grid lines */}
                    <line x1="0" y1="20" x2="300" y2="20" stroke="rgba(255,255,255,0.03)" strokeWidth="0.5" />
                    <line x1="0" y1="60" x2="300" y2="60" stroke="rgba(255,255,255,0.03)" strokeWidth="0.5" />
                    <line x1="0" y1="100" x2="300" y2="100" stroke="rgba(255,255,255,0.03)" strokeWidth="0.5" />
                    
                    {/* Glowing wave curves representing processed energy */}
                    <path
                      d={Array.from({ length: 40 })
                        .map((_, idx) => {
                          const x = (idx / 39) * 300;
                          const y =
                            60 +
                            Math.sin(idx * 0.25 - chartProgress) * 24 * Math.exp(-Math.pow(idx - 20, 2) / 150) +
                            Math.cos(idx * 0.4 + chartProgress * 2) * 6;
                          return `${idx === 0 ? "M" : "L"} ${x} ${y}`;
                        })
                        .join(" ")}
                      stroke="url(#gradient-wave-orange)"
                      strokeWidth="2.5"
                      strokeLinecap="round"
                    />

                    <path
                      d={Array.from({ length: 40 })
                        .map((_, idx) => {
                          const x = (idx / 39) * 300;
                          const y =
                            60 +
                            Math.sin(idx * 0.15 + chartProgress * 1.5) * 16 * Math.exp(-Math.pow(idx - 20, 2) / 120);
                          return `${idx === 0 ? "M" : "L"} ${x} ${y}`;
                        })
                        .join(" ")}
                      stroke="rgba(99, 102, 241, 0.4)"
                      strokeWidth="1.5"
                      strokeDasharray="4 4"
                    />

                    <defs>
                      <linearGradient id="gradient-wave-orange" x1="0" y1="0" x2="300" y2="0" gradientUnits="userSpaceOnUse">
                        <stop offset="0%" stopColor="#FF5C00" />
                        <stop offset="50%" stopColor="#8B5CF6" />
                        <stop offset="100%" stopColor="#6366F1" />
                      </linearGradient>
                    </defs>
                  </svg>

                  {/* Pulsing focal point */}
                  <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 flex items-center justify-center">
                    <span className="w-3 h-3 bg-plasma-orange rounded-full animate-ping opacity-60 absolute" />
                    <span className="w-1.5 h-1.5 bg-white rounded-full relative z-10" />
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* SLIDER HANDLER DIVIDER (Vertical glow line with dragging grip) */}
          <div
            className="absolute top-0 bottom-0 w-[1.5px] bg-gradient-to-b from-plasma-orange via-plasma-purple to-transparent z-30 flex items-center justify-center pointer-events-none"
            style={{ left: `${sliderPos}%` }}
          >
            {/* Pulsing Drag handle button */}
            <div
              className="w-8 h-8 rounded-full bg-void border border-white/20 hover:border-plasma-orange/60 text-white flex items-center justify-center pointer-events-auto shadow-2xl transition-transform duration-300 hover:scale-115 active:scale-95"
              id="slider-grip-button"
            >
              <ChevronsLeftRight className="w-4 h-4 text-zinc-300" />
            </div>
          </div>

          {/* Guide Helper message overlay */}
          <div className="absolute bottom-4 left-1/2 -translate-x-1/2 font-mono text-[9px] text-zinc-500 tracking-wider bg-void/80 px-3 py-1 rounded-full border border-white/[0.04] pointer-events-none z-10">
            DRAG CENTER SLIDER TO CONVERT ENTROPY
          </div>
        </div>
      </div>
    </section>
  );
};
