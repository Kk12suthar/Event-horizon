import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Navbar } from '@/components/landing/Navbar';
import { Hero } from '@/components/landing/Hero';
import { ThePull } from '@/components/landing/ThePull';
import { Capabilities } from '@/components/landing/Capabilities';
import { ClosingCTA } from '@/components/landing/ClosingCTA';
import { BlackHoleCanvas } from '@/components/landing/BlackHoleCanvas';

export function Landing() {
  const navigate = useNavigate();
  const [scrollProgress, setScrollProgress] = useState(0);
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });

  useEffect(() => {
    let scrollFrame = 0;
    let pointerFrame = 0;
    let latestPointer = { x: 0, y: 0 };

    const commitScroll = () => {
      const scrollable = document.documentElement.scrollHeight - window.innerHeight;
      setScrollProgress(scrollable > 0 ? Math.min(window.scrollY / scrollable, 1) : 0);
      scrollFrame = 0;
    };

    const handleScroll = () => {
      if (!scrollFrame) scrollFrame = window.requestAnimationFrame(commitScroll);
    };

    const commitPointer = () => {
      setMousePos(latestPointer);
      pointerFrame = 0;
    };

    const handlePointerMove = (event: PointerEvent) => {
      latestPointer = {
        x: (event.clientX / window.innerWidth) * 2 - 1,
        y: -(event.clientY / window.innerHeight) * 2 + 1,
      };
      if (!pointerFrame) pointerFrame = window.requestAnimationFrame(commitPointer);
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    if (window.matchMedia('(pointer: fine)').matches) {
      window.addEventListener('pointermove', handlePointerMove, { passive: true });
    }
    commitScroll();

    return () => {
      window.removeEventListener('scroll', handleScroll);
      window.removeEventListener('pointermove', handlePointerMove);
      window.cancelAnimationFrame(scrollFrame);
      window.cancelAnimationFrame(pointerFrame);
    };
  }, []);

  const handleLaunch = () => navigate('/signup');

  return (
    <div
      id="app-viewport"
      className="landing-shell relative min-h-screen overflow-hidden bg-black text-zinc-200 selection:bg-primary/30 selection:text-white"
    >
      <div
        id="bg-simulation-layer"
        className="fixed inset-0 z-0 h-full w-full overflow-hidden pointer-events-none"
        aria-hidden="true"
      >
        <BlackHoleCanvas scrollProgress={scrollProgress} mousePos={mousePos} />
      </div>

      <Navbar onLaunch={handleLaunch} />

      <main id="scroll-main" className="relative z-10 flex w-full flex-col items-center overflow-x-hidden">
        <Hero onLaunch={handleLaunch} />
        <ThePull />
        <Capabilities />
        <ClosingCTA onLaunch={handleLaunch} />
      </main>
    </div>
  );
}