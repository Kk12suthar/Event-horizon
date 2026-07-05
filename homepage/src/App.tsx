import React, { useEffect, useState } from "react";
import { Navbar } from "./components/Navbar";
import { Hero } from "./components/Hero";
import { ThePull } from "./components/ThePull";
import { TheTransformation } from "./components/TheTransformation";
import { Capabilities } from "./components/Capabilities";
import { ClosingCTA } from "./components/ClosingCTA";
import { BlackHoleCanvas } from "./components/BlackHoleCanvas";

export default function App() {
  const [scrollProgress, setScrollProgress] = useState<number>(0);
  const [mousePos, setMousePos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  // Handle passive scroll and normalized pointer tracking
  useEffect(() => {
    const handleScroll = () => {
      const totalScrollHeight = document.documentElement.scrollHeight - window.innerHeight;
      if (totalScrollHeight > 0) {
        setScrollProgress(window.scrollY / totalScrollHeight);
      }
    };

    const handleMouseMove = (e: MouseEvent) => {
      // Normalize pointer coordinates between -1 and 1 relative to center
      const x = (e.clientX / window.innerWidth) * 2 - 1;
      const y = -(e.clientY / window.innerHeight) * 2 + 1; // standard webgl coordinate direction
      setMousePos({ x, y });
    };

    window.addEventListener("scroll", handleScroll, { passive: true });
    window.addEventListener("mousemove", handleMouseMove, { passive: true });

    // Initial run
    handleScroll();

    return () => {
      window.removeEventListener("scroll", handleScroll);
      window.removeEventListener("mousemove", handleMouseMove);
    };
  }, []);

  const handleBeginUpload = () => {
    // Smoothly scroll down to capabilities instrument panel to interact with file dropzone
    const element = document.getElementById("section-capabilities");
    if (element) {
      element.scrollIntoView({ behavior: "smooth" });
      
      // Trigger a click highlight or focus on file zone if possible
      setTimeout(() => {
        const dropzone = document.getElementById("file-dropzone");
        if (dropzone) {
          dropzone.classList.add("ring-2", "ring-plasma-orange", "scale-[0.98]");
          setTimeout(() => {
            dropzone.classList.remove("ring-2", "ring-plasma-orange", "scale-[0.98]");
          }, 1200);
        }
      }, 800);
    }
  };

  return (
    <div className="relative min-h-screen bg-[#000000] text-zinc-300 selection:bg-plasma-orange/20 select-none dots-bg noise-bg overflow-hidden" id="app-viewport">
      
      {/* 1. Cinematic Relativistic Schwarzschild Black Hole Canvas in fixed background layer */}
      <div className="fixed inset-0 w-full h-full z-0 pointer-events-none overflow-hidden" id="bg-simulation-layer">
        <BlackHoleCanvas scrollProgress={scrollProgress} mousePos={mousePos} />
      </div>

      {/* 2. Top Minimal Navigation Bar */}
      <Navbar />

      {/* 3. Primary Page Scroll Layout Containers */}
      <main className="relative w-full z-10 flex flex-col items-center overflow-x-hidden" id="scroll-main">
        {/* Hero Section */}
        <Hero onBeginUpload={handleBeginUpload} />

        {/* Phase 01: Intake (The Pull) */}
        <ThePull />

        {/* Phase 02: Compression (The Transformation Split Slider) */}
        <TheTransformation />

        {/* Phase 03: Modular Scientific Tooling Instruments (Upload, Params, Nodes, Export) */}
        <Capabilities />

        {/* Closing CTA and Footer */}
        <ClosingCTA />
      </main>

      {/* Floating scroll indicator path on extreme right margin */}
      <div className="fixed right-6 top-1/2 -translate-y-1/2 h-44 w-[2px] bg-white/[0.03] rounded-full hidden md:flex items-center justify-center z-50 pointer-events-none">
        <div 
          className="w-1.5 h-1.5 rounded-full bg-plasma-orange shadow-[0_0_8px_#FF5C00] transition-all duration-100 absolute"
          style={{ top: `${scrollProgress * 100}%`, transform: "translateY(-50%)" }}
        />
        <span className="absolute -left-12 rotate-90 font-mono text-[7.5px] text-zinc-600 tracking-widest whitespace-nowrap uppercase">
          ORBITAL POSITION
        </span>
      </div>
    </div>
  );
}
