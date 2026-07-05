import React, { useEffect, useRef, useState } from "react";

interface BlackHoleCanvasProps {
  scrollProgress: number; // 0 to 1
  mousePos: { x: number; y: number };
}

export const BlackHoleCanvas: React.FC<BlackHoleCanvasProps> = ({
  scrollProgress,
  mousePos,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [glError, setGlError] = useState<boolean>(false);

  // Shader source code for the relativistic Schwarzschild black hole raytracer
  const vertexShaderSource = `
    attribute vec2 position;
    varying vec2 v_uv;
    void main() {
      v_uv = position * 0.5 + 0.5;
      gl_Position = vec4(position, 0.0, 1.0);
    }
  `;

  const fragmentShaderSource = `
    precision highp float;
    varying vec2 v_uv;
    uniform vec2 u_resolution;
    uniform float u_time;
    uniform float u_scroll;
    uniform vec2 u_mouse;

    #define MAX_STEPS 75
    #define DT 0.15
    #define RS 1.0
    #define PI 3.14159265359

    // Simple pseudo-random hash for stars
    float hash(vec3 p) {
      p = fract(p * 0.3183099 + .1);
      p *= 17.0;
      return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
    }

    // Procedural noise for accretion disk structure
    float noise(vec2 p) {
      vec2 i = floor(p);
      vec2 f = fract(p);
      vec2 u = f * f * (3.0 - 2.0 * f);
      
      float a = hash(vec3(i, 0.0));
      float b = hash(vec3(i + vec2(1.0, 0.0), 0.0));
      float c = hash(vec3(i + vec2(0.0, 1.0), 0.0));
      float d = hash(vec3(i + vec2(1.0, 1.0), 0.0));
      
      return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
    }

    float fbm(vec2 p) {
      float v = 0.0;
      float a = 0.5;
      vec2 shift = vec2(100.0);
      // Rotate to reduce axial bias
      mat2 rot = mat2(cos(0.5), sin(0.5), -sin(0.5), cos(0.5));
      for (int i = 0; i < 4; ++i) {
        v += a * noise(p);
        p = rot * p * 2.0 + shift;
        a *= 0.5;
      }
      return v;
    }

    // High fidelity color mapping for relativistic accretion disk
    vec3 getDiskColor(float dist, float g, float n) {
      // Base temperature profile T ~ r^(-0.75) for thin disks
      // We also make it fade out to 0 at the ISCO boundary (r = 3.0 * GM/c^2 = 1.5 * Rs)
      float isco = 1.5 * RS;
      if (dist < isco) return vec3(0.0);
      
      float temp = pow(dist / isco, -0.75) * (1.0 - sqrt(isco / dist));
      
      // Shift observed temp with general relativity + doppler factor g
      float finalTemp = temp * g * 2.5;
      
      // Add local gaseous clumps / heat variance from noise
      finalTemp += n * 0.15 * pow(dist, -0.5) * g;

      // Color mapping: hotter light is white, medium is pure orange (#c16e43), cooler is deep orange-red, redshifted is dark red-orange
      vec3 colHot = vec3(1.0, 1.0, 1.0);
      vec3 colMid = vec3(1.0, 0.36, 0.0); // Orange
      vec3 colCool = vec3(0.85, 0.25, 0.0); // Deeper orange-red
      vec3 colRedshift = vec3(0.35, 0.04, 0.00); // Gravitationally Redshifted dark red-orange
      
      vec3 col;
      if (finalTemp > 0.8) {
        col = mix(colMid, colHot, (finalTemp - 0.8) / 1.2);
      } else if (finalTemp > 0.3) {
        col = mix(colCool, colMid, (finalTemp - 0.3) / 0.5);
      } else {
        col = mix(colRedshift, colCool, finalTemp / 0.3);
      }
      
      // Fade near edges
      float edgeFade = smoothstep(isco, isco + 0.3, dist) * (1.0 - smoothstep(6.5 * RS, 9.0 * RS, dist));
      return col * edgeFade;
    }

    void main() {
      // Normalize UV to centered aspect-corrected coordinates (-1 to 1)
      vec2 uv = (gl_FragCoord.xy * 2.0 - u_resolution.xy) / min(u_resolution.x, u_resolution.y);
      
      // Time and interactive variables
      float t_var = u_time * 0.8;
      
      // Cinematic Camera Motion based on Scroll Progress & subtle Mouse Parallax
      // Scroll moves camera from slightly elevated orbit down to a more side-on, sweeping cinematic angle
      float camPitch = mix(0.35, 0.05, u_scroll); // angle above disk plane (y=0)
      float camYaw = t_var * 0.12 + u_scroll * 0.6 + u_mouse.x * 0.15; // orbital angle around y-axis
      float camRadius = mix(6.2, 5.0, u_scroll); // pan closer during scroll
      
      // Subtly raise/lower view with mouse
      camPitch += u_mouse.y * 0.08;

      // Calculate camera vectors
      vec3 camPos = vec3(
        camRadius * cos(camYaw) * cos(camPitch),
        camRadius * sin(camPitch),
        camRadius * sin(camYaw) * cos(camPitch)
      );
      
      vec3 target = vec3(0.0, -0.15 * u_scroll, 0.0); // look-at target shifts down slightly as we scroll
      vec3 forward = normalize(target - camPos);
      vec3 right = normalize(cross(forward, vec3(0.0, 1.0, 0.0)));
      vec3 up = cross(right, forward);
      
      // Generate ray direction with subtle lens stretching towards the screen edges
      float fov = mix(1.6, 1.3, u_scroll); // Zoom in slightly as we scroll
      vec3 rayDir = normalize(forward * fov + right * uv.x + up * uv.y);
      
      // Raymarching Geodesic Integrator (Schwarzschild Light Bending)
      vec3 p = camPos;
      vec3 v = rayDir;
      
      vec3 accumColor = vec3(0.0);
      float accumAlpha = 0.0;
      bool hitEventHorizon = false;
      
      vec3 prev_p = p;
      
      for (int i = 0; i < MAX_STEPS; i++) {
        float r2 = dot(p, p);
        float r = sqrt(r2);
        
        // 1. Check if ray fell into the Event Horizon (r <= Rs)
        if (r < RS * 1.002) {
          hitEventHorizon = true;
          break;
        }
        
        // 2. Check crossing of Accretion Disk Plane (y = 0)
        // If sign of y changes, we passed through the plane
        if (p.y * prev_p.y < 0.0) {
          // Exact interpolation of the crossing point
          float t_plane = -prev_p.y / (p.y - prev_p.y);
          vec3 intersect = mix(prev_p, p, t_plane);
          float d_disk = length(intersect.xz);
          
          // Render disk matter inside stable boundaries (ISCO to outer limit)
          if (d_disk >= 1.5 * RS && d_disk <= 8.5 * RS) {
            // Calculate orbital mechanics for Doppler boosting
            // Keplerian orbital velocity V = sqrt(GM/r) in normalized unit: 1.0 / sqrt(2.0 * r)
            float V = 1.0 / sqrt(2.0 * d_disk);
            
            // Tangent vector representing disk material rotation direction
            vec3 tangent = normalize(vec3(-intersect.z, 0.0, intersect.x));
            
            // Matter velocity vector projected onto our ray direction
            float beta = V * dot(tangent, v);
            
            // Relativistic Doppler Factor D = 1 / (gamma * (1 - beta))
            float gamma = 1.0 / sqrt(1.0 - V * V);
            float D = 1.0 / (gamma * (1.0 - beta));
            
            // Gravitational Redshift Factor z_g = sqrt(1.0 - Rs/r)
            float z_g = sqrt(1.0 - RS / d_disk);
            
            // Combining Relativistic Doppler + Gravitational lensing shift
            float g = D * z_g;
            
            // Generate rotating gas spiral structures using noise
            float angle = atan(intersect.z, intersect.x);
            vec2 noiseUV = vec2(d_disk * 1.8 - t_var * 1.5, angle * 2.0 - d_disk * 0.8 + t_var * 0.3);
            float n = fbm(noiseUV);
            
            vec3 diskColor = getDiskColor(d_disk, g, n);
            
            // Doppler beaming boosts energy density by g^3.5
            float beaming = pow(g, 3.5);
            diskColor *= beaming;
            
            // Transparent density accumulation based on angle of penetration
            float opacity = (0.22 + n * 0.15) * smoothstep(1.5 * RS, 1.8 * RS, d_disk) * (1.0 - smoothstep(7.0 * RS, 8.5 * RS, d_disk));
            opacity = clamp(opacity * (1.0 / max(0.05, abs(v.y))), 0.0, 1.0);
            
            accumColor += (1.0 - accumAlpha) * diskColor * opacity;
            accumAlpha += (1.0 - accumAlpha) * opacity;
            
            if (accumAlpha >= 0.98) {
              accumAlpha = 1.0;
              break;
            }
          }
        }
        
        // 3. Geodesic update: Bending the light ray
        // Strong gravity pulls the light path towards the center
        // Schwarzschild bending acceleration is proportional to -1.5 * Rs * L^2 / r^5
        prev_p = p;
        p += v * DT;
        
        // Numerical deflection step
        vec3 force = -1.45 * RS * p / (r2 * r) * DT;
        v = normalize(v + force);
      }
      
      // Render Starfield Background (Warped light rays escaping to infinity)
      if (!hitEventHorizon && accumAlpha < 1.0) {
        // Starfield mapped to celestial sphere from warped direction v
        vec3 starDir = v;
        
        // Generate pseudo-random star field lensed by gravity
        float starDensity = hash(floor(starDir * 240.0));
        vec3 starColor = vec3(0.0);
        
        if (starDensity > 0.994) {
          float intensity = smoothstep(0.994, 1.0, starDensity);
          // Stars have cool visual colors
          float cHash = hash(floor(starDir * 120.0));
          vec3 starTint = vec3(0.85, 0.92, 1.0); // Cyanic star
          if (cHash > 0.7) starTint = vec3(1.0, 0.82, 0.75); // Red giant tint
          if (cHash < 0.25) starTint = vec3(1.0, 1.0, 1.0); // Pure white
          
          // Pulsing twinkle
          float twinkle = mix(0.7, 1.0, sin(u_time * 2.0 + hash(floor(starDir * 100.0)) * 6.0) * 0.5 + 0.5);
          starColor = starTint * intensity * twinkle;
        }
        
        // Draw deep galactic cloud / cosmic dust behind disk
        float dustNoise = fbm(starDir.xy * 2.5 + vec2(t_var * 0.015, t_var * 0.005));
        vec3 dustColor = mix(
          vec3(0.025, 0.008, 0.0), // deep warm ember
          vec3(0.03, 0.012, 0.005), // deep warm copper
          dustNoise
        ) * (1.0 - smoothstep(0.4, 0.9, length(starDir.xy)));
        
        vec3 bg = starColor + dustColor * 0.45;
        accumColor += (1.0 - accumAlpha) * bg;
      } else if (hitEventHorizon) {
        // Event Horizon has absolute black color
        accumColor += (1.0 - accumAlpha) * vec3(0.0);
      }
      
      // Output final color with subtle vignette and cinematic color grading
      vec3 finalCol = accumColor;
      
      // Vignette
      vec2 sUv = gl_FragCoord.xy / u_resolution.xy;
      float vignette = sUv.x * sUv.y * (1.0 - sUv.x) * (1.0 - sUv.y);
      vignette = clamp(pow(16.0 * vignette, 0.25), 0.0, 1.0);
      finalCol *= vignette;
      
      // Soft bloom around the extreme highlights
      float brightness = dot(finalCol, vec3(0.299, 0.587, 0.114));
      if (brightness > 0.8) {
        finalCol += (brightness - 0.8) * vec3(0.12, 0.04, 0.1) * u_scroll;
      }
      
      gl_FragColor = vec4(finalCol, 1.0);
    }
  `;

  // WebGL Renderer logic
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const gl = (canvas.getContext("webgl") ||
      canvas.getContext("experimental-webgl")) as WebGLRenderingContext | null;
    if (!gl) {
      console.warn("WebGL not supported by browser. Falling back to CPU 2D Particle simulation.");
      setGlError(true);
      return;
    }

    // Compile Helper function
    const compileShader = (source: string, type: number): WebGLShader | null => {
      const shader = gl.createShader(type);
      if (!shader) return null;
      gl.shaderSource(shader, source);
      gl.compileShader(shader);
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
        console.error("Shader compilation error:", gl.getShaderInfoLog(shader));
        gl.deleteShader(shader);
        return null;
      }
      return shader;
    };

    const vs = compileShader(vertexShaderSource, gl.VERTEX_SHADER);
    const fs = compileShader(fragmentShaderSource, gl.FRAGMENT_SHADER);
    if (!vs || !fs) {
      setGlError(true);
      return;
    }

    const program = gl.createProgram();
    if (!program) {
      setGlError(true);
      return;
    }
    gl.attachShader(program, vs);
    gl.attachShader(program, fs);
    gl.linkProgram(program);

    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      console.error("Program linking error:", gl.getProgramInfoLog(program));
      setGlError(true);
      return;
    }

    // Set up positions
    const vertices = new Float32Array([
      -1.0, -1.0,
       1.0, -1.0,
      -1.0,  1.0,
      -1.0,  1.0,
       1.0, -1.0,
       1.0,  1.0,
    ]);

    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, vertices, gl.STATIC_DRAW);

    const positionLoc = gl.getAttribLocation(program, "position");
    gl.enableVertexAttribArray(positionLoc);
    gl.vertexAttribPointer(positionLoc, 2, gl.FLOAT, false, 0, 0);

    // Uniform locations
    const resolutionLoc = gl.getUniformLocation(program, "u_resolution");
    const timeLoc = gl.getUniformLocation(program, "u_time");
    const scrollLoc = gl.getUniformLocation(program, "u_scroll");
    const mouseLoc = gl.getUniformLocation(program, "u_mouse");

    let animationFrameId = 0;
    let startTime = Date.now();

    // Responsive Canvas Resizer - Render at half-scale for 60 FPS performance
    const resizeCanvas = () => {
      const displayWidth = containerRef.current?.clientWidth || window.innerWidth;
      const displayHeight = containerRef.current?.clientHeight || window.innerHeight;
      
      // Half-resolution downscaling for incredibly smooth 60fps on retina and mobile
      const dpr = window.devicePixelRatio > 1 ? 1.0 : 1.0; 
      const renderWidth = Math.floor(displayWidth * dpr);
      const renderHeight = Math.floor(displayHeight * dpr);

      if (canvas.width !== renderWidth || canvas.height !== renderHeight) {
        canvas.width = renderWidth;
        canvas.height = renderHeight;
        gl.viewport(0, 0, renderWidth, renderHeight);
      }
    };

    window.addEventListener("resize", resizeCanvas);
    resizeCanvas();

    // Render loop
    const render = () => {
      const now = Date.now();
      const elapsed = (now - startTime) / 1000.0;

      gl.useProgram(program);

      // Pass uniforms
      gl.uniform2f(resolutionLoc, canvas.width, canvas.height);
      gl.uniform1f(timeLoc, elapsed);
      gl.uniform1f(scrollLoc, scrollProgress);
      gl.uniform2f(mouseLoc, mousePos.x, mousePos.y);

      // Draw
      gl.drawArrays(gl.TRIANGLES, 0, 6);

      animationFrameId = requestAnimationFrame(render);
    };

    render();

    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener("resize", resizeCanvas);
      gl.deleteBuffer(buffer);
      gl.deleteProgram(program);
      gl.deleteShader(vs);
      gl.deleteShader(fs);
    };
  }, [scrollProgress, glError]);

  // HIGH PERFORMANCE HTML5 2D CANVAS FALLBACK
  // Designed in case WebGL is unavailable or errors out
  const fallbackCanvasRef = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    if (!glError) return;

    const canvas = fallbackCanvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animationId = 0;
    let startTime = Date.now();

    // Create a high-fidelity 2D particle accretion disk simulation
    interface Particle {
      angle: number;
      radius: number;
      speed: number;
      size: number;
      color: string;
      alpha: number;
    }

    const particles: Particle[] = [];
    const particleCount = 280;

    // Initialize stars orbiting the gravity well
    for (let i = 0; i < particleCount; i++) {
      const radius = 60 + Math.random() * 220;
      // Closer particles orbit much faster (Keplerian physics: speed ~ r^-1.5)
      const speed = (0.2 + Math.random() * 0.15) * Math.pow(radius / 60, -1.2);
      // Doppler mapping: left side is coming towards observer (+y), color is white-orange.
      // Right side moving away, color is deep blood orange/pink.
      particles.push({
        angle: Math.random() * Math.PI * 2,
        radius,
        speed,
        size: 1 + Math.random() * 2.5,
        color: radius < 110 ? "rgba(195, 112, 70, " : "rgba(200, 128, 80, ",
        alpha: 0.15 + Math.random() * 0.7,
      });
    }

    // Static starfield background for deep space feeling
    const stars: { x: number; y: number; size: number; brightness: number }[] = [];
    for (let i = 0; i < 150; i++) {
      stars.push({
        x: Math.random(),
        y: Math.random(),
        size: 0.5 + Math.random() * 1.5,
        brightness: 0.2 + Math.random() * 0.8,
      });
    }

    const resizeFallback = () => {
      const displayWidth = containerRef.current?.clientWidth || window.innerWidth;
      const displayHeight = containerRef.current?.clientHeight || window.innerHeight;
      canvas.width = displayWidth;
      canvas.height = displayHeight;
    };

    window.addEventListener("resize", resizeFallback);
    resizeFallback();

    const drawFallback = () => {
      const t = (Date.now() - startTime) / 1000;
      const w = canvas.width;
      const h = canvas.height;
      const cx = w / 2;
      const cy = h / 2 + mixValue(0, -60, scrollProgress);

      // Fade canvas to black-indigo void
      ctx.fillStyle = "#000000";
      ctx.fillRect(0, 0, w, h);

      // Draw Starfield with Gravitational Lensing displacement near center
      ctx.fillStyle = "rgba(255, 255, 255, 0.8)";
      stars.forEach((star) => {
        let sx = star.x * w;
        let sy = star.y * h;
        
        // Calculate vector from black hole center to star
        const dx = sx - cx;
        const dy = sy - cy;
        const dist = Math.sqrt(dx * dx + dy * dy);
        
        // Relativistic lensing effect: stretch and deflect star positions
        // Stars close to event horizon are pushed outward or smeared
        if (dist > 35) {
          const deflection = 1.0 + (3000 / (dist * dist));
          sx = cx + dx * deflection;
          sy = cy + dy * deflection;
          
          ctx.globalAlpha = star.brightness * (0.35 + Math.sin(t * 3 + star.x * 20) * 0.15);
          ctx.beginPath();
          ctx.arc(sx, sy, star.size, 0, Math.PI * 2);
          ctx.fill();
        }
      });

      // Draw subtle glowing dust clouds / nebula background
      const nebulaGlow = ctx.createRadialGradient(cx, cy, 30, cx, cy, 320);
      nebulaGlow.addColorStop(0, "rgba(193, 110, 67, 0.1)");
      nebulaGlow.addColorStop(0.3, "rgba(198, 126, 78, 0.06)");
      nebulaGlow.addColorStop(0.6, "rgba(175, 92, 55, 0.02)");
      nebulaGlow.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.globalAlpha = 1;
      ctx.fillStyle = nebulaGlow;
      ctx.fillRect(0, 0, w, h);

      // Draw Accretion Disk back lensing (glowing ring curving over the top)
      ctx.lineWidth = 4;
      ctx.strokeStyle = "rgba(193, 110, 67, 0.12)";
      ctx.beginPath();
      ctx.ellipse(cx, cy - 8, 95, 30, 0, Math.PI, Math.PI * 2, false);
      ctx.stroke();

      // Update and Draw Orbiting Particles (Data nodes)
      // Doppler brightness: left side (moving forward) is brighter
      particles.forEach((p) => {
        // Orbital projection with pitch tilting
        const pitch = mixValue(0.3, 0.08, scrollProgress) + mousePos.y * 0.03;
        const yaw = p.angle + mousePos.x * 0.05;
        
        const px = cx + p.radius * Math.cos(yaw);
        const py = cy + p.radius * Math.sin(yaw) * pitch;

        // Is particle in front of or behind the central black hole?
        const isFront = Math.sin(yaw) > 0;

        // Velocity along the line of sight (Doppler boosting)
        // Left side is moving forward, right is moving back
        const lineOfSightVel = -Math.sin(yaw); // Max at cos() point
        const dopplerMultiplier = mixValue(0.4, 2.3, (lineOfSightVel + 1) / 2);

        ctx.globalAlpha = p.alpha * dopplerMultiplier * (isFront ? 1.0 : 0.4);
        ctx.fillStyle = p.color + (p.alpha * dopplerMultiplier).toFixed(2) + ")";

        ctx.beginPath();
        ctx.arc(px, py, p.size * (isFront ? 1.2 : 0.8) * (0.8 + dopplerMultiplier * 0.2), 0, Math.PI * 2);
        ctx.fill();

        // Gravitational drag pulls particle closer to the center
        p.angle += p.speed;
        p.radius -= 0.05; // spiral inward
        if (p.radius < 35) {
          // Re-spawn particle at outer edge when sucked into event horizon
          p.radius = 200 + Math.random() * 80;
          p.speed = (0.2 + Math.random() * 0.15) * Math.pow(p.radius / 60, -1.2);
        }
      });

      // Draw the central pitch-black Event Horizon shadow
      ctx.globalAlpha = 1.0;
      ctx.fillStyle = "#000000";
      ctx.beginPath();
      ctx.arc(cx, cy, 35, 0, Math.PI * 2);
      ctx.fill();

      // Sharp glowing photon sphere ring
      const innerGlow = ctx.createRadialGradient(cx, cy, 32, cx, cy, 38);
      innerGlow.addColorStop(0, "rgba(255, 255, 255, 0.95)");
      innerGlow.addColorStop(0.2, "rgba(193, 110, 67, 0.9)");
      innerGlow.addColorStop(0.7, "rgba(175, 92, 55, 0.3)");
      innerGlow.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.fillStyle = innerGlow;
      ctx.beginPath();
      ctx.arc(cx, cy, 44, 0, Math.PI * 2);
      ctx.fill();

      // Outer light wrap around Event Horizon (lensed accretion disk foreground overlay)
      ctx.lineWidth = 14;
      const gradientDisk = ctx.createLinearGradient(cx - 100, cy, cx + 100, cy);
      gradientDisk.addColorStop(0, "rgba(255, 255, 255, 0.95)"); // Doppler boosted bright left
      gradientDisk.addColorStop(0.4, "rgba(193, 110, 67, 0.8)");
      gradientDisk.addColorStop(0.7, "rgba(198, 126, 78, 0.4)");
      gradientDisk.addColorStop(1, "rgba(0, 0, 0, 0.1)"); // Receding faint right
      ctx.strokeStyle = gradientDisk;
      
      ctx.beginPath();
      // Only draw the front half of the ellipse if tilted
      ctx.ellipse(cx, cy, 75, 12, 0, 0, Math.PI, false);
      ctx.stroke();

      animationId = requestAnimationFrame(drawFallback);
    };

    drawFallback();

    return () => {
      cancelAnimationFrame(animationId);
      window.removeEventListener("resize", resizeFallback);
    };
  }, [scrollProgress, glError, mousePos]);

  // Utility lerp helper for fallback canvas
  const mixValue = (start: number, end: number, amt: number) => {
    return (1 - amt) * start + amt * end;
  };

  return (
    <div
      ref={containerRef}
      className="absolute inset-0 w-full h-full overflow-hidden pointer-events-none"
    >
      {/* Background radial soft light center to make black hole feel integrated */}
      <div 
        className="absolute w-[600px] h-[600px] rounded-full filter blur-[150px] pointer-events-none opacity-40 transition-all duration-300"
        style={{
          left: "50%",
          top: `calc(50% + ${mixValue(0, -60, scrollProgress)}px)`,
          transform: "translate(-50%, -50%)",
          background: `radial-gradient(circle, rgba(193, 110, 67,0.15) 0%, rgba(200, 128, 80,0.10) 40%, rgba(185, 100, 60,0.04) 75%, rgba(0,0,0,0) 100%)`,
        }}
      />

      {glError ? (
        <canvas
          ref={fallbackCanvasRef}
          className="absolute inset-0 w-full h-full mix-blend-screen opacity-90 transition-transform duration-700 ease-out"
        />
      ) : (
        <canvas
          ref={canvasRef}
          className="absolute inset-0 w-full h-full mix-blend-screen opacity-95 transition-opacity duration-1000"
        />
      )}

      {/* Subtle overlay lines/noise suggesting spacetime coordinates warp */}
      <div 
        className="absolute inset-0 grid-bg opacity-10 pointer-events-none"
        style={{
          maskImage: "radial-gradient(circle at 50% 50%, transparent 120px, black 320px)",
          WebkitMaskImage: "radial-gradient(circle at 50% 50%, transparent 120px, black 320px)",
          transform: `perspective(1000px) rotateX(${mixValue(65, 80, scrollProgress)}deg) translateZ(${mixValue(0, -100, scrollProgress)}px) translateY(${mixValue(0, 150, scrollProgress)}px)`,
          transformOrigin: "center center",
          transition: "transform 0.15s ease-out"
        }}
      />
    </div>
  );
};
