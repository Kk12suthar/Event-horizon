import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Navbar } from '@/components/landing/Navbar';
import { Hero } from '@/components/landing/Hero';
import { ThePull } from '@/components/landing/ThePull';
import { TheTransformation } from '@/components/landing/TheTransformation';
import { Capabilities } from '@/components/landing/Capabilities';
import { ClosingCTA } from '@/components/landing/ClosingCTA';
import { BlackHoleCanvas } from '@/components/landing/BlackHoleCanvas';

/**
 * Public marketing landing page served at "/".
 *
 * Ported from the standalone `homepage` app. The cinematic sections are
 * self-contained; this wrapper wires the primary call-to-action into the
 * application's auth flow via react-router.
 */
export function Landing() {
  const navigate = useNavigate();
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

    window.addEventListener('scroll', handleScroll, { passive: true });
    window.addEventListener('mousemove', handleMouseMove, { passive: true });

    // Initial run
    handleScroll();

    return () => {
      window.removeEventListener('scroll', handleScroll);
      window.removeEventListener('mousemove', handleMouseMove);
    };
  }, []);

  const handleLaunch = () => {
    navigate('/signup');
  };

  return (
    <div
      className="relative min-h-screen bg-[#000000] text-zinc-300 selection:bg-plasma-orange/20 select-none dots-bg noise-bg overflow-hidden"
      id="app-viewport"
    >
      {/* 1. Cinematic Relativistic Schwarzschild Black Hole Canvas in fixed background layer */}
      <div
        className="fixed inset-0 w-full h-full z-0 pointer-events-none overflow-hidden"
        id="bg-simulation-layer"
      >
        <BlackHoleCanvas scrollProgress={scrollProgress} mousePos={mousePos} />
      </div>

      {/* 2. Top Minimal Navigation Bar */}
      <Navbar onLaunch={handleLaunch} />

      {/* 3. Primary Page Scroll Layout Containers */}
      <main
        className="relative w-full z-10 flex flex-col items-center overflow-x-hidden"
        id="scroll-main"
      >
        {/* Hero Section */}
        <Hero onLaunch={handleLaunch} />

        {/* Phase 01: Intake (The Pull) */}
        <ThePull />

        {/* Phase 02: Compression (The Transformation Split Slider) */}
        <TheTransformation />

        {/* Phase 03: Modular Scientific Tooling Instruments (Upload, Params, Nodes, Export) */}
        <Capabilities />

        {/* Closing CTA and Footer */}
        <ClosingCTA onLaunch={handleLaunch} />
      </main>

      {/* Floating scroll indicator path on extreme right margin */}
      <div className="fixed right-6 top-1/2 -translate-y-1/2 h-44 w-[2px] bg-white/[0.03] rounded-full hidden md:flex items-center justify-center z-50 pointer-events-none">
        <div
          className="w-1.5 h-1.5 rounded-full bg-plasma-orange shadow-[0_0_8px_#c16e43] transition-all duration-100 absolute"
          style={{ top: `${scrollProgress * 100}%`, transform: 'translateY(-50%)' }}
        />
        <span className="absolute -left-12 rotate-90 font-mono text-[7.5px] text-zinc-600 tracking-widest whitespace-nowrap uppercase">
          ORBITAL POSITION
        </span>
      </div>
    </div>
  );
}
