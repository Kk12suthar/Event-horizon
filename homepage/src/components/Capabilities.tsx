import React, { useState, useRef } from "react";
import { motion, AnimatePresence } from "motion/react";
import { 
  Upload, Sliders, LineChart, FileJson, 
  Check, Copy, Database, Layers, Radio, ShieldAlert 
} from "lucide-react";

export const Capabilities: React.FC = () => {
  // Instrument 1: File Upload State
  const [uploadedFile, setUploadedFile] = useState<{ name: string; size: number; progress: number } | null>(null);
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [isExtracting, setIsExtracting] = useState<boolean>(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Instrument 2: Parameter Sliders State
  const [compressionRatio, setCompressionRatio] = useState<number>(78);
  const [lensingStrength, setLensingStrength] = useState<number>(45);
  const [noiseFilter, setNoiseFilter] = useState<number>(92);

  // Instrument 3: Anomalies Nodes click states
  const [selectedNode, setSelectedNode] = useState<{ id: string; mass: string; entropy: string } | null>({
    id: "NODE-304", mass: "1.49 Solar", entropy: "2.812 H"
  });
  const [ripples, setRipples] = useState<{ id: number; x: number; y: number }[]>([]);

  // Instrument 4: Report copying status
  const [copied, setCopied] = useState<boolean>(false);

  // File Upload Handlers (Drag & Drop + Click)
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const simulateProgress = (fileName: string, fileSize: number) => {
    setUploadedFile({ name: fileName, size: fileSize, progress: 0 });
    setIsExtracting(true);
    let cur = 0;
    const interval = setInterval(() => {
      cur += 4;
      setUploadedFile(prev => prev ? { ...prev, progress: Math.min(100, cur) } : null);
      if (cur >= 100) {
        clearInterval(interval);
        setIsExtracting(false);
      }
    }, 80);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      simulateProgress(file.name, file.size);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      simulateProgress(file.name, file.size);
    }
  };

  // Node grid click handler for ripples
  const handleNodeClick = (e: React.MouseEvent<HTMLDivElement>, nodeId: string, mass: string, entropy: string) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    
    setRipples(prev => [...prev, { id: Date.now(), x, y }]);
    setSelectedNode({ id: nodeId, mass, entropy });
    
    // Clear ripples
    setTimeout(() => {
      setRipples(prev => prev.filter(r => r.id !== r.id));
    }, 1200);
  };

  // JSON Copier
  const jsonReportCode = `{
  "platform": "EventHorizon",
  "engine_version": "v3.14.0",
  "data_state": "HORIZON_COHERENT",
  "telemetry": {
    "lensing_alignment": "${(lensingStrength * 0.015).toFixed(3)} Rs",
    "compression_factor": "${(compressionRatio * 4.8).toFixed(2)}x",
    "residual_entropy": "${(100 - noiseFilter).toFixed(2)}%"
  },
  "extraction_results": {
    "file_ingested": "${uploadedFile?.name || "unstable_plasma_logs.bin"}",
    "gravity_nodes_resolved": 16409,
    "integrity_checksum": "0xEF38A1B0C"
  }
}`;

  const handleCopyReport = () => {
    navigator.clipboard.writeText(jsonReportCode);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <section
      id="section-capabilities"
      className="relative min-h-screen w-full py-24 px-6 z-10 border-b border-white/[0.02]"
    >
      <div className="w-full max-w-7xl flex flex-col items-center space-y-20">
        
        {/* Section Headline */}
        <div className="text-center max-w-2xl space-y-4">
          <div className="inline-flex items-center gap-2 px-3 py-1 bg-white/[0.02] border border-white/[0.05] rounded-full">
            <Layers className="w-3.5 h-3.5 text-plasma-purple" />
            <span className="font-mono text-[9px] tracking-widest text-zinc-400 uppercase">
              Phase 03 :: Capability Matrix
            </span>
          </div>

          <h2 className="font-display font-semibold text-3xl md:text-5xl text-white tracking-tight uppercase">
            The Instrument Panel
            <span className="block text-zinc-500 font-light text-xl md:text-2xl mt-2 lowercase font-sans">
              interactive high-mass tooling
            </span>
          </h2>
        </div>

        {/* Bento Grid layout of Modular Instruments */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 w-full" id="instrument-bento-grid">
          
          {/* INSTRUMENT 1: GRAVITY INTAKE (Upload) - 7 cols */}
          <div className="lg:col-span-7 bg-coal border border-white/[0.05] rounded-2xl p-6 flex flex-col space-y-6 relative noise-bg overflow-hidden" id="instrument-upload">
            <div className="flex justify-between items-start border-b border-white/[0.04] pb-4">
              <div className="space-y-1">
                <span className="font-mono text-[9px] tracking-wider text-plasma-orange font-semibold uppercase">
                  INSTRUMENT 01 // GRAV_INTAKE_MODULE
                </span>
                <h3 className="font-display font-medium text-lg text-white uppercase tracking-tight">
                  High-Mass Data Upload
                </h3>
              </div>
              <Upload className="w-5 h-5 text-plasma-orange" />
            </div>

            {/* Custom Interactive File Upload Drag Drop field */}
            <div
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`flex-1 min-h-[180px] border-2 border-dashed rounded-xl flex flex-col items-center justify-center p-6 transition-all duration-300 cursor-pointer ${
                isDragging 
                  ? "border-plasma-orange bg-plasma-orange/[0.02] scale-[0.99]" 
                  : "border-white/[0.08] hover:border-white/20 bg-void/30"
              }`}
              id="file-dropzone"
            >
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                onChange={handleFileSelect}
              />
              
              <div className="p-3.5 bg-white/[0.02] border border-white/[0.05] rounded-full mb-4">
                <Upload className="w-5 h-5 text-zinc-400" />
              </div>

              <p className="text-xs font-mono text-zinc-300 uppercase tracking-widest text-center">
                DRAG DATASETS HERE OR <span className="text-plasma-orange hover:underline">BROWSE</span>
              </p>
              
              <p className="text-[10px] text-zinc-600 mt-2 text-center max-w-sm">
                Supports binary, JSON chunks, massive multi-column CSVs, and logs up to 12.8 GB
              </p>
            </div>

            {/* Display active upload progress / relativistic scanning animation */}
            <AnimatePresence>
              {uploadedFile && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  className="p-4 bg-void/65 border border-white/[0.05] rounded-xl flex flex-col space-y-3"
                >
                  <div className="flex justify-between items-center text-xs font-mono">
                    <span className="text-white font-medium truncate max-w-[70%]">{uploadedFile.name}</span>
                    <span className="text-zinc-500">{(uploadedFile.size / 1024).toFixed(1)} KB</span>
                  </div>

                  {/* Scanning slide line bar */}
                  <div className="relative w-full h-1 bg-white/[0.04] rounded-full overflow-hidden">
                    <div 
                      className="absolute top-0 bottom-0 left-0 bg-gradient-to-r from-plasma-orange to-plasma-purple transition-all duration-100"
                      style={{ width: `${uploadedFile.progress}%` }}
                    />
                  </div>

                  <div className="flex justify-between items-center text-[9px] font-mono">
                    <span className="text-plasma-orange flex items-center gap-1">
                      {isExtracting ? (
                        <>
                          <span className="w-1.5 h-1.5 rounded-full bg-plasma-orange animate-ping" />
                          COMPRESSING SPACE...
                        </>
                      ) : (
                        "COMPRESSION SECURE (100%)"
                      )}
                    </span>
                    <span className="text-zinc-500">{uploadedFile.progress}%</span>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* INSTRUMENT 2: SPACETIME TRANSFORMER (Sliders) - 5 cols */}
          <div className="lg:col-span-5 bg-coal border border-white/[0.05] rounded-2xl p-6 flex flex-col space-y-6 relative noise-bg overflow-hidden" id="instrument-transform">
            <div className="flex justify-between items-start border-b border-white/[0.04] pb-4">
              <div className="space-y-1">
                <span className="font-mono text-[9px] tracking-wider text-plasma-purple font-semibold uppercase">
                  INSTRUMENT 02 // COORDINATE_WARP_UNIT
                </span>
                <h3 className="font-display font-medium text-lg text-white uppercase tracking-tight">
                  Spacetime Transformer
                </h3>
              </div>
              <Sliders className="w-5 h-5 text-plasma-purple" />
            </div>

            {/* Interactive sliders for gravitational configuration */}
            <div className="flex-1 flex flex-col justify-center space-y-6">
              {[
                { 
                  label: "MASS COMPRESSION RATIO", 
                  min: 10, max: 150, unit: "x", 
                  value: compressionRatio, 
                  setter: setCompressionRatio,
                  color: "accent-plasma-orange"
                },
                { 
                  label: "GRAVITATIONAL LENSING FIELD", 
                  min: 0, max: 100, unit: " Rs", 
                  value: lensingStrength, 
                  setter: setLensingStrength,
                  color: "accent-plasma-purple"
                },
                { 
                  label: "THERMAL ENTROPY FILTER", 
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
              <span>OUTPUT_RATE: {(compressionRatio * 4.4).toFixed(0)} MB/s</span>
              <span>ENTROPY: {((100 - noiseFilter) * 0.08).toFixed(3)} H</span>
            </div>
          </div>

          {/* INSTRUMENT 3: LENSING ANALYZER (Interactions) - 5 cols */}
          <div className="lg:col-span-5 bg-coal border border-white/[0.05] rounded-2xl p-6 flex flex-col space-y-6 relative noise-bg overflow-hidden" id="instrument-analyze">
            <div className="flex justify-between items-start border-b border-white/[0.04] pb-4">
              <div className="space-y-1">
                <span className="font-mono text-[9px] tracking-wider text-ion-violet font-semibold uppercase">
                  INSTRUMENT 03 // VECTOR_LENSING_ANALYST
                </span>
                <h3 className="font-display font-medium text-lg text-white uppercase tracking-tight">
                  Relativistic Analyzer
                </h3>
              </div>
              <LineChart className="w-5 h-5 text-ion-violet" />
            </div>

            {/* Interactive Node Gravity Well Detector */}
            <div className="flex-1 flex flex-col space-y-4">
              <span className="block font-mono text-[9px] text-zinc-500 tracking-wider">
                DETECTION HORIZON (CLICK TO EMIT GRAVITY WAVE)
              </span>

              <div 
                className="h-[180px] bg-void border border-white/[0.05] rounded-xl relative overflow-hidden flex items-center justify-center cursor-pointer"
                onClick={(e) => handleNodeClick(e, "NODE-" + Math.floor(100 + Math.random() * 900), (Math.random() * 3 + 0.5).toFixed(2) + " Solar", (Math.random() * 4).toFixed(3) + " H")}
              >
                {/* Background radar grid */}
                <div className="absolute inset-0 grid-bg opacity-20" />
                <div className="absolute w-[1px] h-full bg-white/[0.04] left-1/2" />
                <div className="absolute h-[1px] w-full bg-white/[0.04] top-1/2" />

                {/* Animated scanning light bar */}
                <div className="absolute top-0 bottom-0 w-20 bg-gradient-to-r from-transparent via-ion-violet/5 to-transparent animate-scanline" />

                {/* Concentric targets */}
                <div className="absolute w-24 h-24 border border-white/[0.03] rounded-full" />
                <div className="absolute w-44 h-44 border border-white/[0.015] rounded-full" />

                {/* Scatter nodes that the user can highlight */}
                {[
                  { x: "32%", y: "25%", id: "NODE-112", mass: "0.82 Solar", entropy: "1.092 H" },
                  { x: "72%", y: "65%", id: "NODE-219", mass: "2.14 Solar", entropy: "0.455 H" },
                  { x: "18%", y: "70%", id: "NODE-304", mass: "1.49 Solar", entropy: "2.812 H" },
                  { x: "85%", y: "20%", id: "NODE-490", mass: "3.78 Solar", entropy: "0.012 H" },
                ].map((node) => (
                  <button
                    key={node.id}
                    onClick={(e) => {
                      e.stopPropagation(); // prevent parent click
                      handleNodeClick(e, node.id, node.mass, node.entropy);
                    }}
                    className={`absolute w-3 h-3 rounded-full flex items-center justify-center transform -translate-x-1/2 -translate-y-1/2 transition-all duration-300 ${
                      selectedNode?.id === node.id 
                        ? "bg-white border-2 border-ion-violet scale-125 z-20 shadow-lg shadow-ion-violet/50" 
                        : "bg-ion-violet/20 hover:bg-ion-violet/50 border border-ion-violet/40"
                    }`}
                    style={{ left: node.x, top: node.y }}
                  />
                ))}

                {/* Rippling custom waves generated inside detector */}
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

              {/* Detector Stats Card */}
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
                      <span className="block text-zinc-600">NODE ID</span>
                      <span className="text-white font-medium">{selectedNode.id}</span>
                    </div>
                    <div>
                      <span className="block text-zinc-600">GRAV_MASS</span>
                      <span className="text-ion-violet font-medium">{selectedNode.mass}</span>
                    </div>
                    <div>
                      <span className="block text-zinc-600">LOCAL_ENTROPY</span>
                      <span className="text-white font-medium">{selectedNode.entropy}</span>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>

          {/* INSTRUMENT 4: COHERENCY REPORTER (JSON Export) - 7 cols */}
          <div className="lg:col-span-7 bg-coal border border-white/[0.05] rounded-2xl p-6 flex flex-col space-y-6 relative noise-bg overflow-hidden" id="instrument-report">
            <div className="flex justify-between items-start border-b border-white/[0.04] pb-4">
              <div className="space-y-1">
                <span className="font-mono text-[9px] tracking-wider text-plasma-purple font-semibold uppercase">
                  INSTRUMENT 04 // SCHEMATIC_COHERENCY_REPORTER
                </span>
                <h3 className="font-display font-medium text-lg text-white uppercase tracking-tight">
                  Prismatic Report Exporter
                </h3>
              </div>
              <FileJson className="w-5 h-5 text-plasma-purple" />
            </div>

            {/* Glowing JSON viewer with clipboard option */}
            <div className="flex-1 flex flex-col space-y-3">
              <div className="flex justify-between items-center text-[10px] font-mono">
                <span className="text-zinc-500">SCHEMATIC EXPORT PAYLOAD (JSON)</span>
                
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
                      <span>COPY SCHEMA</span>
                    </>
                  )}
                </button>
              </div>

              <div className="flex-1 bg-void border border-white/[0.04] rounded-xl p-4 font-mono text-[9.5px] text-zinc-400 overflow-x-auto relative">
                <pre className="leading-relaxed select-all">
                  <code>{jsonReportCode}</code>
                </pre>
                
                {/* Visual glow on the right representing compiled data */}
                <div className="absolute right-0 bottom-0 top-0 w-32 bg-gradient-to-l from-plasma-purple/5 to-transparent pointer-events-none" />
              </div>
            </div>
          </div>

        </div>

      </div>
    </section>
  );
};
