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
  const scrollRef = useRef(scrollProgress);
  const mouseRef = useRef(mousePos);

  useEffect(() => {
    scrollRef.current = scrollProgress;
  }, [scrollProgress]);

  useEffect(() => {
    mouseRef.current = mousePos;
  }, [mousePos]);

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

    // Neutral temperature map: warm white near the core, silver at the edge.
    vec3 getDiskColor(float dist, float g, float n) {
      float isco = 1.5 * RS;
      if (dist < isco) return vec3(0.0);

      float temp = pow(dist / isco, -0.75) * (1.0 - sqrt(isco / dist));
      float finalTemp = temp * g * 2.15;
      finalTemp += n * 0.08 * pow(dist, -0.5) * g;

      vec3 colHot = vec3(1.0, 0.985, 0.95);
      vec3 colMid = vec3(0.62, 0.49, 0.42);
      vec3 colCool = vec3(0.34, 0.31, 0.30);
      vec3 colRedshift = vec3(0.075, 0.078, 0.085);

      vec3 col;
      if (finalTemp > 0.8) {
        col = mix(colMid, colHot, (finalTemp - 0.8) / 1.2);
      } else if (finalTemp > 0.3) {
        col = mix(colCool, colMid, (finalTemp - 0.3) / 0.5);
      } else {
        col = mix(colRedshift, colCool, finalTemp / 0.3);
      }

      float edgeFade = smoothstep(isco, isco + 0.3, dist) * (1.0 - smoothstep(6.5 * RS, 9.0 * RS, dist));
      return col * edgeFade * 0.82;
    }

    void main() {
      // Normalize UV to centered aspect-corrected coordinates (-1 to 1)
      vec2 uv = (gl_FragCoord.xy * 2.0 - u_resolution.xy) / min(u_resolution.x, u_resolution.y);
      float aspectRatio = u_resolution.x / max(u_resolution.y, 1.0);
      if (aspectRatio > 1.2) uv.x -= 0.28;
      
      // Time and interactive variables
      float t_var = u_time * 0.35;
      
      // Cinematic Camera Motion based on Scroll Progress & subtle Mouse Parallax
      // Scroll moves camera from slightly elevated orbit down to a more side-on, sweeping cinematic angle
      float camPitch = mix(0.31, 0.08, u_scroll); // angle above disk plane (y=0)
      float camYaw = t_var * 0.055 + u_scroll * 0.4 + u_mouse.x * 0.08; // slow orbital drift around y-axis
      float camRadius = mix(6.2, 5.0, u_scroll); // pan closer during scroll
      
      // Subtly raise/lower view with mouse
      camPitch += u_mouse.y * 0.04;

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
        
        if (starDensity > 0.997) {
          float intensity = smoothstep(0.997, 1.0, starDensity) * 0.72;
          // Stars have cool visual colors
          float cHash = hash(floor(starDir * 120.0));
          vec3 starTint = vec3(0.72, 0.74, 0.76);
          if (cHash > 0.7) starTint = vec3(0.92, 0.90, 0.86);
          if (cHash < 0.25) starTint = vec3(0.98, 0.98, 0.97);
          
          // Pulsing twinkle
          float twinkle = mix(0.82, 1.0, sin(u_time * 0.7 + hash(floor(starDir * 100.0)) * 6.0) * 0.5 + 0.5);
          starColor = starTint * intensity * twinkle;
        }
        
        // Draw deep galactic cloud / cosmic dust behind disk
        float dustNoise = fbm(starDir.xy * 2.5 + vec2(t_var * 0.015, t_var * 0.005));
        vec3 dustColor = mix(
          vec3(0.006, 0.006, 0.007),
          vec3(0.012, 0.012, 0.013),
          dustNoise
        ) * (1.0 - smoothstep(0.35, 0.85, length(starDir.xy)));
        
        vec3 bg = starColor + dustColor * 0.24;
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
      if (brightness > 0.72) {
        finalCol += (brightness - 0.72) * vec3(0.025, 0.024, 0.022) * (0.2 + u_scroll * 0.25);
      }
      
      finalCol = finalCol / (vec3(1.0) + finalCol * 0.3);
      gl_FragColor = vec4(finalCol, 1.0);
    }
  `;

  // Initialize WebGL once. Scroll and pointer input are eased through refs inside the frame loop.
  useEffect(() => {
    if (glError) return;

    const canvas = canvasRef.current;
    if (!canvas) return;

    const gl = (canvas.getContext("webgl") ||
      canvas.getContext("experimental-webgl")) as WebGLRenderingContext | null;
    if (!gl) {
      console.warn("WebGL is unavailable; using the 2D black-hole renderer.");
      setGlError(true);
      return;
    }

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
      if (vs) gl.deleteShader(vs);
      if (fs) gl.deleteShader(fs);
      setGlError(true);
      return;
    }

    const program = gl.createProgram();
    if (!program) {
      gl.deleteShader(vs);
      gl.deleteShader(fs);
      setGlError(true);
      return;
    }

    gl.attachShader(program, vs);
    gl.attachShader(program, fs);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      console.error("Program linking error:", gl.getProgramInfoLog(program));
      gl.deleteProgram(program);
      gl.deleteShader(vs);
      gl.deleteShader(fs);
      setGlError(true);
      return;
    }

    const vertices = new Float32Array([
      -1, -1, 1, -1, -1, 1,
      -1, 1, 1, -1, 1, 1,
    ]);
    const buffer = gl.createBuffer();
    if (!buffer) {
      gl.deleteProgram(program);
      gl.deleteShader(vs);
      gl.deleteShader(fs);
      setGlError(true);
      return;
    }

    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, vertices, gl.STATIC_DRAW);

    const positionLoc = gl.getAttribLocation(program, "position");
    gl.enableVertexAttribArray(positionLoc);
    gl.vertexAttribPointer(positionLoc, 2, gl.FLOAT, false, 0, 0);

    const resolutionLoc = gl.getUniformLocation(program, "u_resolution");
    const timeLoc = gl.getUniformLocation(program, "u_time");
    const scrollLoc = gl.getUniformLocation(program, "u_scroll");
    const mouseLoc = gl.getUniformLocation(program, "u_mouse");

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const startTime = performance.now();
    let animationFrameId = 0;
    let smoothedScroll = scrollRef.current;
    let smoothedMouseX = mouseRef.current.x;
    let smoothedMouseY = mouseRef.current.y;

    const resizeCanvas = () => {
      const displayWidth = containerRef.current?.clientWidth || window.innerWidth;
      const displayHeight = containerRef.current?.clientHeight || window.innerHeight;
      const renderScale = window.innerWidth < 768 ? 0.78 : 1;
      const renderWidth = Math.max(1, Math.floor(displayWidth * renderScale));
      const renderHeight = Math.max(1, Math.floor(displayHeight * renderScale));

      if (canvas.width !== renderWidth || canvas.height !== renderHeight) {
        canvas.width = renderWidth;
        canvas.height = renderHeight;
        gl.viewport(0, 0, renderWidth, renderHeight);
      }
    };

    const render = (now: number) => {
      if (!document.hidden) {
        smoothedScroll += (scrollRef.current - smoothedScroll) * 0.045;
        smoothedMouseX += (mouseRef.current.x - smoothedMouseX) * 0.035;
        smoothedMouseY += (mouseRef.current.y - smoothedMouseY) * 0.035;

        gl.useProgram(program);
        gl.uniform2f(resolutionLoc, canvas.width, canvas.height);
        gl.uniform1f(timeLoc, reduceMotion ? 4 : (now - startTime) / 1000);
        gl.uniform1f(scrollLoc, smoothedScroll);
        gl.uniform2f(mouseLoc, smoothedMouseX, smoothedMouseY);
        gl.drawArrays(gl.TRIANGLES, 0, 6);
      }

      if (!reduceMotion) animationFrameId = requestAnimationFrame(render);
    };

    const handleResize = () => {
      resizeCanvas();
      if (reduceMotion) render(performance.now());
    };

    window.addEventListener("resize", handleResize);
    resizeCanvas();
    render(performance.now());

    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener("resize", handleResize);
      gl.deleteBuffer(buffer);
      gl.deleteProgram(program);
      gl.deleteShader(vs);
      gl.deleteShader(fs);
    };
  }, [fragmentShaderSource, glError, vertexShaderSource]);
  const fallbackCanvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!glError) return;

    const canvas = fallbackCanvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    interface Particle {
      angle: number;
      radius: number;
      speed: number;
      size: number;
      alpha: number;
    }

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const particles: Particle[] = Array.from({ length: 170 }, () => ({
      angle: Math.random() * Math.PI * 2,
      radius: 54 + Math.random() * 230,
      speed: 0.0018 + Math.random() * 0.0022,
      size: 0.7 + Math.random() * 1.7,
      alpha: 0.12 + Math.random() * 0.52,
    }));
    const stars = Array.from({ length: 90 }, () => ({
      x: Math.random(),
      y: Math.random(),
      size: 0.45 + Math.random() * 1.1,
      brightness: 0.12 + Math.random() * 0.42,
    }));

    let animationId = 0;
    let smoothedScroll = scrollRef.current;
    let smoothedMouseX = mouseRef.current.x;
    let smoothedMouseY = mouseRef.current.y;
    const startTime = performance.now();

    const resize = () => {
      const width = containerRef.current?.clientWidth || window.innerWidth;
      const height = containerRef.current?.clientHeight || window.innerHeight;
      canvas.width = Math.max(1, Math.floor(width));
      canvas.height = Math.max(1, Math.floor(height));
    };

    const draw = (now: number) => {
      smoothedScroll += (scrollRef.current - smoothedScroll) * 0.045;
      smoothedMouseX += (mouseRef.current.x - smoothedMouseX) * 0.035;
      smoothedMouseY += (mouseRef.current.y - smoothedMouseY) * 0.035;

      const elapsed = reduceMotion ? 4 : (now - startTime) / 1000;
      const width = canvas.width;
      const height = canvas.height;
      const wide = width / Math.max(height, 1) > 1.2;
      const cx = width * (wide ? 0.64 : 0.5) + smoothedMouseX * 10;
      const cy = height * 0.53 - smoothedScroll * 45 - smoothedMouseY * 6;
      const scale = Math.min(width, height) / 720;

      ctx.globalAlpha = 1;
      ctx.fillStyle = "#000000";
      ctx.fillRect(0, 0, width, height);

      ctx.fillStyle = "rgba(238, 238, 234, 0.7)";
      for (const star of stars) {
        const flicker = 0.82 + Math.sin(elapsed * 0.5 + star.x * 20) * 0.08;
        ctx.globalAlpha = star.brightness * flicker;
        ctx.beginPath();
        ctx.arc(star.x * width, star.y * height, star.size, 0, Math.PI * 2);
        ctx.fill();
      }

      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(-0.08 + smoothedScroll * 0.04);
      ctx.scale(1, 0.28 + smoothedScroll * 0.04);

      const halo = ctx.createRadialGradient(0, 0, 35 * scale, 0, 0, 280 * scale);
      halo.addColorStop(0, "rgba(255, 252, 242, 0.12)");
      halo.addColorStop(0.32, "rgba(205, 205, 201, 0.045)");
      halo.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.globalAlpha = 1;
      ctx.fillStyle = halo;
      ctx.beginPath();
      ctx.arc(0, 0, 280 * scale, 0, Math.PI * 2);
      ctx.fill();

      for (const particle of particles) {
        const x = Math.cos(particle.angle) * particle.radius * scale;
        const y = Math.sin(particle.angle) * particle.radius * scale;
        const approaching = Math.max(0, -Math.sin(particle.angle));
        ctx.globalAlpha = particle.alpha * (0.34 + approaching * 0.66);
        ctx.fillStyle = approaching > 0.55 ? "#fffaf0" : "#a7a7a4";
        ctx.beginPath();
        ctx.arc(x, y, particle.size * scale, 0, Math.PI * 2);
        ctx.fill();

        if (!reduceMotion) particle.angle += particle.speed;
        particle.radius -= reduceMotion ? 0 : 0.014;
        if (particle.radius < 47) particle.radius = 220 + Math.random() * 65;
      }

      const disk = ctx.createLinearGradient(-150 * scale, 0, 170 * scale, 0);
      disk.addColorStop(0, "rgba(255, 252, 242, 0.9)");
      disk.addColorStop(0.34, "rgba(193, 110, 67, 0.24)");
      disk.addColorStop(0.72, "rgba(117, 118, 120, 0.25)");
      disk.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.globalAlpha = 0.8;
      ctx.strokeStyle = disk;
      ctx.lineWidth = 7 * scale;
      ctx.beginPath();
      ctx.ellipse(0, 0, 120 * scale, 18 * scale, 0, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();

      const shadow = ctx.createRadialGradient(cx, cy, 24 * scale, cx, cy, 62 * scale);
      shadow.addColorStop(0, "rgba(0, 0, 0, 1)");
      shadow.addColorStop(0.7, "rgba(0, 0, 0, 1)");
      shadow.addColorStop(0.86, "rgba(232, 230, 222, 0.28)");
      shadow.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.globalAlpha = 1;
      ctx.fillStyle = shadow;
      ctx.beginPath();
      ctx.arc(cx, cy, 66 * scale, 0, Math.PI * 2);
      ctx.fill();

      if (!reduceMotion) animationId = requestAnimationFrame(draw);
    };

    const handleResize = () => {
      resize();
      if (reduceMotion) draw(performance.now());
    };

    window.addEventListener("resize", handleResize);
    resize();
    draw(performance.now());

    return () => {
      cancelAnimationFrame(animationId);
      window.removeEventListener("resize", handleResize);
    };
  }, [glError]);
  return (
    <div ref={containerRef} className="absolute inset-0 h-full w-full overflow-hidden pointer-events-none">
      {glError ? (
        <canvas
          ref={fallbackCanvasRef}
          className="absolute inset-0 h-full w-full opacity-[0.82] transition-opacity duration-700"
        />
      ) : (
        <canvas
          ref={canvasRef}
          className="absolute inset-0 h-full w-full opacity-[0.86] transition-opacity duration-700"
        />
      )}
    </div>
  );
};