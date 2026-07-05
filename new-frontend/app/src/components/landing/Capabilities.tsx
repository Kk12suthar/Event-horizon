import React, { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Sliders, LineChart, FileJson, Check, Copy } from "lucide-react";

export const Capabilities: React.FC = () => {
  // Instrument 1: Prepare - transform parameter sliders
  const [rowsNormalized, setRowsNormalized] = useState<number>(78);
  const [joinAlignment, setJoinAlignment] = useState<number>(45);
  const [noiseFilter, setNoiseFilter] = useState<number>(92);

  // Instrument 2: Visualize - series click states
  const [selectedNode, setSelectedNode] = useState<{ id: string; value: string; trend: string } | null>({
    id: "SERIES-04", value: "1.49K", trend: "+2.81%"
  });
  const [ripples, setRipples] = useState<{ id: number; x: number; y: number }[]>([]);

  // Instrument 3: Publish - manifest copy status
  const [copied, setCopied] = useState<boolean>(false);

  // Series click handler for ripple feedback on the chart canvas
  const handleNodeClick = (e: React.MouseEvent<HTMLElement>, nodeId: string, value: string, trend: string) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const rippleId = Date.now();
    setRipples((prev) => [...prev, { id: rippleId, x, y }]);
    setSelectedNode({ id: nodeId, value, trend });

    // Clear this ripple after its animation completes
    setTimeout(() => {
      setRipples((prev) => prev.filter((r) => r.id !== rippleId));
    }, 1200);
  };

  // Report manifest emitted by the Publish stage
  const reportManifest = `{
  "platform": "EventHorizon",
  "workspace_mode": "publish",
  "folder_state": "TRANSFORMED",
  "prepare": {
    "rows_normalized": "${rowsNormalized}%",
    "join_alignment": "${joinAlignment}%",
    "noise_filtered": "${noiseFilter}%"
  },
  "artifacts": {
    "tables": 3,
    "charts": ["line", "bar", "pie"],
    "report_formats": ["PPTX", "PDF", "DOCX", "XLSX"]
  }
}`;

  const handleCopyReport = () => {
    navigator.clipboard.writeText(reportManifest);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <section
      id="section-capabilities"
      className="relative min-h-screen w-full py-24 px-6 z-10 border-b border-white/[0.02]"
    >
      <div className="w-full max-w-7xl mx-auto flex flex-col items-center space-y-20">

        {/* Section Headline */}
        <div className="text-center max-w-2xl space-y-4">
          <h2 className="font-display font-semibold text-3xl md:text-5xl text-white tracking-tight uppercase">
            One Unified Workspace
            <span className="block text-zinc-500 font-light text-xl md:text-2xl mt-2 lowercase font-sans">
              prepare · visualize · publish
            </span>
          </h2>
        </div>

        {/* Bento Grid layout of the three workspace modes */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 w-full" id="instrument-bento-grid">

          {/* PREPARE - transform controls (5 cols) */}
          <div className="lg:col-span-5 bg-coal border border-white/[0.05] rounded-2xl p-6 flex flex-col space-y-6 relative noise-bg overflow-hidden" id="instrument-prepare">
            <div className="flex justify-between items-start border-b border-white/[0.04] pb-4">
              <div className="space-y-1">
                <h3 className="font-display font-medium text-lg text-white uppercase tracking-tight">
                  Agentic Transforms
                </h3>
              </div>
              <Sliders className="w-5 h-5 text-plasma-orange" />
            </div>

            {/* Transform parameter sliders */}
            <div className="flex-1 flex flex-col justify-center space-y-6">
              {[
                {
                  label: "ROWS NORMALIZED",
                  min: 10, max: 100, unit: "%",
                  value: rowsNormalized,
                  setter: setRowsNormalized,
                  color: "accent-plasma-orange"
                },
                {
                  label: "JOIN ALIGNMENT",
                  min: 0, max: 100, unit: "%",
                  value: joinAlignment,
                  setter: setJoinAlignment,
                  color: "accent-plasma-purple"
                },
                {
                  label: "NOISE FILTER",
                  min: 50, max: 100, unit: "%",
                  value: noiseFilter,
                  setter: setNoiseFilter,
                  color: "accent-plasma-purple"
                }
              ].map((slider, index) => (
                <div key={index} className="space-y-2">
                  <div className="flex justify-between items-center text-[10px] font-mono tracking-wider">
                    <span className="text-zinc-500 uppercase">{slider.label}</span>
                    <span className="text-white font-medium">
                      {slider.value}{slider.unit}
                    </span>
                  </div>
                  <input
                    type="range"
                    min={slider.min}
                    max={slider.max}
                    value={slider.value}
                    onChange={(e) => slider.setter(parseInt(e.target.value))}
                    className={`w-full h-1 bg-white/[0.05] rounded-lg appearance-none cursor-pointer ${slider.color}`}
                  />
                </div>
              ))}
            </div>

            <div className="p-3 bg-void/50 border border-white/[0.03] rounded-lg font-mono text-[8.5px] text-zinc-600 flex justify-between">
              <span>THROUGHPUT: {(rowsNormalized * 4.4).toFixed(0)} rows/s</span>
              <span>NULLS: {((100 - noiseFilter) * 0.08).toFixed(3)}%</span>
            </div>
          </div>

          {/* VISUALIZE - dashboard builder (7 cols) */}
          <div className="lg:col-span-7 bg-coal border border-white/[0.05] rounded-2xl p-6 flex flex-col space-y-6 relative noise-bg overflow-hidden" id="instrument-visualize">
            <div className="flex justify-between items-start border-b border-white/[0.04] pb-4">
              <div className="space-y-1">
                <h3 className="font-display font-medium text-lg text-white uppercase tracking-tight">
                  Charts & Dashboards
                </h3>
              </div>
              <LineChart className="w-5 h-5 text-ion-violet" />
            </div>

            {/* Interactive series canvas */}
            <div className="flex-1 flex flex-col space-y-4">
              <span className="block font-mono text-[9px] text-zinc-500 tracking-wider">
                CHART CANVAS (CLICK A SERIES TO INSPECT)
              </span>

              <div
                className="h-[180px] bg-void border border-white/[0.05] rounded-xl relative overflow-hidden flex items-center justify-center cursor-pointer"
                onClick={(e) => handleNodeClick(e, "SERIES-" + Math.floor(1 + Math.random() * 9).toString().padStart(2, "0"), (Math.random() * 3 + 0.5).toFixed(2) + "K", (Math.random() > 0.5 ? "+" : "-") + (Math.random() * 5).toFixed(2) + "%")}
              >
                {/* Background chart grid */}
                <div className="absolute inset-0 grid-bg opacity-20" />
                <div className="absolute w-[1px] h-full bg-white/[0.04] left-1/2" />
                <div className="absolute h-[1px] w-full bg-white/[0.04] top-1/2" />

                {/* Animated scanning light bar */}
                <div className="absolute top-0 bottom-0 w-20 bg-gradient-to-r from-transparent via-ion-violet/5 to-transparent animate-scanline" />

                {/* Concentric guides */}
                <div className="absolute w-24 h-24 border border-white/[0.03] rounded-full" />
                <div className="absolute w-44 h-44 border border-white/[0.015] rounded-full" />

                {/* Data points the user can highlight */}
                {[
                  { x: "32%", y: "25%", id: "SERIES-01", value: "0.82K", trend: "+1.09%" },
                  { x: "72%", y: "65%", id: "SERIES-02", value: "2.14K", trend: "+0.45%" },
                  { x: "18%", y: "70%", id: "SERIES-04", value: "1.49K", trend: "+2.81%" },
                  { x: "85%", y: "20%", id: "SERIES-09", value: "3.78K", trend: "-0.12%" },
                ].map((node) => (
                  <button
                    key={node.id}
                    onClick={(e) => {
                      e.stopPropagation(); // prevent parent click
                      handleNodeClick(e, node.id, node.value, node.trend);
                    }}
                    className={`absolute w-3 h-3 rounded-full flex items-center justify-center transform -translate-x-1/2 -translate-y-1/2 transition-all duration-300 ${
                      selectedNode?.id === node.id
                        ? "bg-white border-2 border-ion-violet scale-125 z-20 shadow-lg shadow-ion-violet/50"
                        : "bg-ion-violet/20 hover:bg-ion-violet/50 border border-ion-violet/40"
                    }`}
                    style={{ left: node.x, top: node.y }}
                  />
                ))}

                {/* Ripple feedback on click */}
                {ripples.map((rip) => (
                  <span
                    key={rip.id}
                    className="absolute border border-ion-violet/50 rounded-full animate-ping pointer-events-none"
                    style={{
                      left: rip.x,
                      top: rip.y,
                      width: "60px",
                      height: "60px",
                      transform: "translate(-50%, -50%)",
                      animationDuration: "1.2s",
                    }}
                  />
                ))}
              </div>

              {/* Selected series stats */}
              <AnimatePresence mode="wait">
                {selectedNode && (
                  <motion.div
                    key={selectedNode.id}
                    initial={{ opacity: 0, y: 5 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -5 }}
                    className="p-3 bg-void/50 border border-white/[0.04] rounded-lg grid grid-cols-3 gap-2 text-[10px] font-mono leading-normal"
                  >
                    <div>
                      <span className="block text-zinc-600">SERIES</span>
                      <span className="text-white font-medium">{selectedNode.id}</span>
                    </div>
                    <div>
                      <span className="block text-zinc-600">VALUE</span>
                      <span className="text-ion-violet font-medium">{selectedNode.value}</span>
                    </div>
                    <div>
                      <span className="block text-zinc-600">TREND</span>
                      <span className="text-white font-medium">{selectedNode.trend}</span>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>

          {/* PUBLISH - report exporter (full width) */}
          <div className="lg:col-span-12 bg-coal border border-white/[0.05] rounded-2xl p-6 flex flex-col space-y-6 relative noise-bg overflow-hidden" id="instrument-publish">
            <div className="flex justify-between items-start border-b border-white/[0.04] pb-4">
              <div className="space-y-1">
                <h3 className="font-display font-medium text-lg text-white uppercase tracking-tight">
                  Reports & Export
                </h3>
              </div>
              <FileJson className="w-5 h-5 text-plasma-purple" />
            </div>

            {/* Report manifest viewer with clipboard option */}
            <div className="flex-1 flex flex-col space-y-3">
              <div className="flex justify-between items-center text-[10px] font-mono">
                <span className="text-zinc-500">EXPORT MANIFEST - PPTX · PDF · DOCX · XLSX</span>

                <button
                  onClick={handleCopyReport}
                  className="flex items-center gap-1.5 text-zinc-400 hover:text-white transition-colors duration-200 cursor-pointer"
                >
                  {copied ? (
                    <>
                      <Check className="w-3.5 h-3.5 text-emerald-400" />
                      <span className="text-emerald-400 font-semibold">COPIED</span>
                    </>
                  ) : (
                    <>
                      <Copy className="w-3.5 h-3.5" />
                      <span>COPY MANIFEST</span>
                    </>
                  )}
                </button>
              </div>

              <div className="flex-1 bg-void border border-white/[0.04] rounded-xl p-4 font-mono text-[9.5px] text-zinc-400 overflow-x-auto relative">
                <pre className="leading-relaxed select-all">
                  <code>{reportManifest}</code>
                </pre>

                {/* Visual glow on the right representing a compiled report */}
                <div className="absolute right-0 bottom-0 top-0 w-32 bg-gradient-to-l from-plasma-purple/5 to-transparent pointer-events-none" />
              </div>
            </div>
          </div>

        </div>

      </div>
    </section>
  );
};
