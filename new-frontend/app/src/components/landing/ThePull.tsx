import React, { useEffect, useRef, useState } from "react";
import { Activity, Magnet, Radio } from "lucide-react";

export const ThePull: React.FC = () => {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [hoveredCoords, setHoveredCoords] = useState<{ x: number; y: number } | null>(null);

  // Generate real-time chaotic scrolling data logs
  useEffect(() => {
    const logInterval = setInterval(() => {
      const entropy = (Math.random() * 100).toFixed(4);
      const nodeId = Math.floor(Math.random() * 9999);
      const r = (1.5 + Math.random() * 6).toFixed(3);
      const v = (0.5 + Math.random() * 0.499).toFixed(5);
      
      const newLogs = [
        `[INFLOW] node_id=${nodeId} :: raw_entropy=${entropy} :: distance=${r}Rs`,
        `[GRAV_ACCEL] pull_factor=${(10 / parseFloat(r)).toFixed(2)}x :: velocity=${v}c`,
        `[GEODESIC] coordinate_warp_offset=[${(Math.random() - 0.5).toFixed(3)}, ${(Math.random() - 0.5).toFixed(3)}]`,
      ];
      
      setLogs((prev) => [...prev, ...newLogs].slice(-15));
    }, 450);

    return () => clearInterval(logInterval);
  }, []);

  // Interactive Particle Pull Grid (Canvas)
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animFrame = 0;
    const points: {
      x: number;
      y: number;
      vx: number;
      vy: number;
      size: number;
      alpha: number;
      color: string;
      id: string;
    }[] = [];

    // Initialize 160 random chaotic points
    for (let i = 0; i < 160; i++) {
      points.push({
        x: Math.random() * 400,
        y: Math.random() * 400,
        vx: (Math.random() - 0.5) * 1.5,
        vy: (Math.random() - 0.5) * 1.5,
        size: 1 + Math.random() * 2.5,
        alpha: 0.1 + Math.random() * 0.5,
        color: Math.random() > 0.6 ? "rgba(193, 110, 67, " : "rgba(205, 150, 95, ",
        id: `N-${Math.floor(1000 + Math.random() * 9000)}`,
      });
    }

    const draw = () => {
      ctx.fillStyle = "rgba(5, 5, 8, 0.35)"; // fade to trace with atmospheric void background
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // Center of the canvas acts as the main gravity well
      const cx = canvas.width / 2;
      const cy = canvas.height / 2;

      // Draw subtle lensed field lines
      ctx.strokeStyle = "rgba(255, 255, 255, 0.02)";
      ctx.lineWidth = 1;
      for (let r = 40; r < 240; r += 40) {
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        ctx.stroke();
      }

      // Draw gravity well vortex
      ctx.fillStyle = "rgba(193, 110, 67, 0.03)";
      ctx.beginPath();
      ctx.arc(cx, cy, 35, 0, Math.PI * 2);
      ctx.fill();

      // Update and draw points
      points.forEach((p) => {
        // Core gravity pull towards center (cx, cy)
        const dx = cx - p.x;
        const dy = cy - p.y;
        const distSq = dx * dx + dy * dy;
        const dist = Math.sqrt(distSq);

        // Core Black hole gravity force
        let pull = 18.0 / Math.max(30, dist);
        if (dist < 40) {
          // Cross horizon: collapse to singularity, respawn
          p.x = Math.random() * canvas.width;
          p.y = Math.random() * canvas.height;
          p.vx = (Math.random() - 0.5) * 1.5;
          p.vy = (Math.random() - 0.5) * 1.5;
          return;
        }

        // Apply core acceleration
        p.vx += (dx / dist) * pull * 0.05;
        p.vy += (dy / dist) * pull * 0.05;

        // Pointer-based gravity pull if hovered
        if (hoveredCoords) {
          const pdx = hoveredCoords.x - p.x;
          const pdy = hoveredCoords.y - p.y;
          const pdist = Math.sqrt(pdx * pdx + pdy * pdy);
          if (pdist < 120) {
            const pPull = (120 - pdist) * 0.04;
            p.vx += (pdx / pdist) * pPull * 0.05;
            p.vy += (pdy / pdist) * pPull * 0.05;
          }
        }

        // Apply friction
        p.vx *= 0.96;
        p.vy *= 0.96;

        // Position update
        p.x += p.vx;
        p.y += p.vy;

        // Render point
        ctx.fillStyle = p.color + p.alpha.toFixed(2) + ")";
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
        ctx.fill();

        // Connect points that are close to visualize chaotic data mesh
        points.forEach((p2) => {
          if (p === p2) return;
          const cdx = p.x - p2.x;
          const cdy = p.y - p2.y;
          const cdist = cdx * cdx + cdy * cdy;
          if (cdist < 1400) {
            const connAlpha = (1.0 - Math.sqrt(cdist) / 38) * 0.14 * p.alpha;
            ctx.strokeStyle = `rgba(193, 110, 67, ${connAlpha.toFixed(2)})`;
            ctx.lineWidth = 0.5;
            ctx.beginPath();
            ctx.moveTo(p.x, p.y);
            ctx.lineTo(p2.x, p2.y);
            ctx.stroke();
          }
        });

        // Hover effect helper - draw tiny node labels
        if (hoveredCoords) {
          const pdx = hoveredCoords.x - p.x;
          const pdy = hoveredCoords.y - p.y;
          const pdist = Math.sqrt(pdx * pdx + pdy * pdy);
          if (pdist < 30) {
            ctx.font = "8px monospace";
            ctx.fillStyle = "rgba(255, 255, 255, 0.4)";
            ctx.fillText(p.id, p.x + 6, p.y - 4);
          }
        }
      });

      animFrame = requestAnimationFrame(draw);
    };

    draw();

    return () => {
      cancelAnimationFrame(animFrame);
    };
  }, [hoveredCoords]);

  // Handle pointer tracking over the simulation canvas
  const handlePointerMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    setHoveredCoords({
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    });
  };

  const handlePointerLeave = () => {
    setHoveredCoords(null);
  };

  return (
    <section
      id="section-pull"
      ref={containerRef}
      className="relative min-h-screen w-full flex flex-col justify-center items-center py-24 px-6 z-10 border-b border-white/[0.02]"
    >
      <div className="w-full max-w-7xl grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
        {/* Left Side: Editorial copywriting & status trackers */}
        <div className="lg:col-span-5 space-y-8 text-left">
          <h2 className="font-display font-semibold text-3xl md:text-5xl text-white tracking-tight uppercase">
            Bring In Your Data
            <span className="block text-zinc-500 font-light text-xl md:text-2xl mt-2 lowercase font-sans">
              organized by project and folder
            </span>
          </h2>

          <p className="text-zinc-400 text-sm font-sans leading-relaxed font-light">
            Create a project, add a folder, and upload your datasets. CSV files and
            tables land in a shared workspace the agent can reach &mdash; no rigid schema
            setup, no manual wiring. Everything you bring orbits the same folder
            context, ready for the next stage.
          </p>

          {/* Interactive cursor gravity badge info */}
          <div className="p-4 bg-white/[0.01] border border-white/[0.04] rounded-lg flex items-start gap-4">
            <div className="p-2 bg-plasma-orange/10 rounded-md">
              <Magnet className="w-5 h-5 text-plasma-orange" />
            </div>
            <div className="space-y-1">
              <p className="text-[11px] text-zinc-500 leading-normal">
                Move your cursor over the telemetry grid on the right to feel the
                folder&rsquo;s gravity &mdash; a playful preview of data being drawn into a
                single workspace context.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4 pt-4 border-t border-white/[0.04]">
            <div>
              <span className="block text-[8px] font-mono text-zinc-500 uppercase tracking-wider">
                SUPPORTED DATA
              </span>
              <span className="block text-sm font-mono text-zinc-300 font-medium">
                CSV, Tables, Files
              </span>
            </div>
            <div>
              <span className="block text-[8px] font-mono text-zinc-500 uppercase tracking-wider">
                ORGANIZED INTO
              </span>
              <span className="block text-sm font-mono text-zinc-300 font-medium text-glow-orange">
                Projects & Folders
              </span>
            </div>
          </div>
        </div>

        {/* Right Side: The live coordinates grid & falling particles canvas */}
        <div className="lg:col-span-7 grid grid-cols-1 md:grid-cols-12 gap-6 w-full h-[400px] md:h-[450px]">
          {/* Telemetry scrolling feed monitor */}
          <div className="md:col-span-5 h-full bg-coal border border-white/[0.04] rounded-xl flex flex-col overflow-hidden relative noise-bg">
            <div className="px-4 py-2.5 bg-void border-b border-white/[0.04] flex justify-between items-center">
              <div className="flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-plasma-purple animate-ping" />
                <span className="font-mono text-[9px] tracking-wider text-zinc-400 uppercase">
                  Telemetry Stream
                </span>
              </div>
              <Radio className="w-3.5 h-3.5 text-zinc-600 animate-pulse" />
            </div>

            <div className="flex-1 p-4 font-mono text-[9px] text-zinc-500 overflow-y-hidden space-y-1.5 leading-normal select-none">
              {logs.map((log, idx) => (
                <div
                  key={idx}
                  className={`truncate transition-all duration-300 ${
                    log.includes("[INFLOW]") ? "text-zinc-400" : log.includes("[GRAV_ACCEL]") ? "text-plasma-orange/80" : "text-plasma-purple/75"
                  }`}
                >
                  {log}
                </div>
              ))}
            </div>
            
            <div className="absolute bottom-0 left-0 right-0 h-10 bg-gradient-to-t from-coal to-transparent pointer-events-none" />
          </div>

          {/* Interactive attractor gravity well canvas */}
          <div className="md:col-span-7 h-full bg-coal border border-white/[0.04] rounded-xl relative overflow-hidden flex flex-col noise-bg">
            <div className="px-4 py-2.5 bg-void border-b border-white/[0.04] flex justify-between items-center z-10">
              <span className="font-mono text-[9px] tracking-wider text-zinc-400 uppercase">
                GEODESIC INTAKE MONITOR
              </span>
              <Activity className="w-3.5 h-3.5 text-plasma-orange animate-pulse" />
            </div>

            <div className="flex-1 relative flex items-center justify-center bg-[#000000]">
              <canvas
                ref={canvasRef}
                width={400}
                height={400}
                onMouseMove={handlePointerMove}
                onMouseLeave={handlePointerLeave}
                className="w-full h-full max-w-[400px] max-h-[400px] cursor-crosshair mix-blend-screen"
              />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
