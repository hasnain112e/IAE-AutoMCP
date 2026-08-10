// src/components/HeroCanvas.tsx
import React, { useEffect, useRef } from "react";

type ParticleType = "phrase" | "box";

interface Particle {
  type: ParticleType;
  text?: string;
  x: number;
  y: number;
  z: number;
  vx: number;
  vy: number;
  vz: number;
  waveOffset: number;
  life: number;
  maxLife: number;
  colorA: string;
  colorB: string;
  // phrase-only extras
  direction?: "left" | "right";
  rotationBase?: number;
  rotationAmp?: number;
}

const PHRASES: string[] = [
  "AUTO MCP",
  "API EXPLORER",
  "TOOL FORGE",
  "LIVE API CHAT",
  "MCP READY",
  "ZERO-FRICTION FLOWS",
  "DIGITAL PAKISTAN",
  "PAKISTAN → DIGITIZATION → AUTOMATION",
  "FINTECH · REGTECH",
  "OPEN BANKING TOOLS",
  "POSTMAN → OPENAPI → SDK → MCP",
  "EXPLORE SDKS AUTOMATICALLY",
  "ECG · FMP · PLAID · COINGECKO",
  "CSV + JSON TOOL EXPORT",
  "CODE → TOOLS → MCP SERVER",
];

const COLOR_PALETTES: Array<[string, string]> = [
  ["#38bdf8", "#22c55e"], // sky -> emerald
  ["#a855f7", "#38bdf8"], // purple -> sky
  ["#f97316", "#22c55e"], // orange -> emerald
  ["#ef4444", "#eab308"], // red -> amber
  ["#0ea5e9", "#6366f1"], // light blue -> indigo
];

const MAX_PHRASE_PARTICLES = 1; // exactly one phrase at a time
const TOTAL_BOX_PARTICLES = 55;

export const HeroCanvas: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animationFrameId: number;
    const particles: Particle[] = [];

    const getDpr = () => window.devicePixelRatio || 1;

    const resize = () => {
      const dpr = getDpr();
      const w = window.innerWidth;
      const h = window.innerHeight;

      canvas.width = w * dpr;
      canvas.height = h * dpr;
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    resize();
    window.addEventListener("resize", resize);

    const getDims = () => {
      const dpr = getDpr();
      return {
        w: canvas.width / dpr,
        h: canvas.height / dpr,
      };
    };

    const randomPalette = (): [string, string] =>
      COLOR_PALETTES[Math.floor(Math.random() * COLOR_PALETTES.length)];

    const randomPhrase = (): string =>
      PHRASES[Math.floor(Math.random() * PHRASES.length)];

    const spawnPhraseParticle = (): Particle => {
      const { w, h } = getDims();
      const centerY = h / 2;

      const [colorA, colorB] = randomPalette();

      // random direction: slide across from left or right
      const direction: "left" | "right" =
        Math.random() < 0.5 ? "left" : "right";

      const fromLeft = direction === "left";
      const startX = fromLeft ? -w * 0.2 : w * 1.2;
      const targetY = centerY + (Math.random() - 0.5) * (h * 0.25);

      // speed: always towards center / across
      const vxBase = (0.4 + Math.random() * 0.4) * (fromLeft ? 1 : -1);
      const vyBase = (Math.random() - 0.5) * 0.08;

      // random tilt
      const rotationBase = (Math.random() - 0.5) * 0.35; // -20° to 20°
      const rotationAmp = 0.12 + Math.random() * 0.18; // wobble amplitude

      return {
        type: "phrase",
        text: randomPhrase(),
        x: startX,
        y: targetY,
        z: -1100 - Math.random() * 400,
        vx: vxBase,
        vy: vyBase,
        vz: 0.9 + Math.random() * 0.4,
        waveOffset: Math.random() * Math.PI * 2,
        life: 0,
        maxLife: 1600 + Math.random() * 800,
        colorA,
        colorB,
        direction,
        rotationBase,
        rotationAmp,
      };
    };

    const spawnBoxParticle = (): Particle => {
      const { w, h } = getDims();
      const centerX = w / 2;
      const centerY = h / 2;
      const [colorA, colorB] = randomPalette();

      return {
        type: "box",
        x: centerX + (Math.random() - 0.5) * w * 0.9,
        y: centerY + (Math.random() - 0.5) * h * 0.9,
        z: -1300 - Math.random() * 800,
        vx: (Math.random() - 0.5) * 0.25,
        vy: (Math.random() - 0.5) * 0.25,
        vz: 1 + Math.random() * 0.6,
        waveOffset: Math.random() * Math.PI * 2,
        life: 0,
        maxLife: 900 + Math.random() * 800,
        colorA,
        colorB,
      };
    };

    const spawnAllParticles = () => {
      particles.length = 0;
      for (let i = 0; i < MAX_PHRASE_PARTICLES; i++) {
        particles.push(spawnPhraseParticle());
      }
      for (let i = 0; i < TOTAL_BOX_PARTICLES; i++) {
        particles.push(spawnBoxParticle());
      }
    };

    spawnAllParticles();

    const render = () => {
      const { w, h } = getDims();

      // Gradient background across whole viewport (over darkslategray body)
      const bgGrad = ctx.createLinearGradient(0, 0, w, h);
      bgGrad.addColorStop(0, "rgba(15,23,42,0.98)");
      bgGrad.addColorStop(0.3, "rgba(10,37,64,0.98)");
      bgGrad.addColorStop(0.7, "rgba(15,23,42,0.99)");
      bgGrad.addColorStop(1, "rgba(8,47,73,0.98)");
      ctx.fillStyle = bgGrad;
      ctx.fillRect(0, 0, w, h);

      // Soft radial color glow
      const radial = ctx.createRadialGradient(
        w * 0.5,
        h * 0.4,
        0,
        w * 0.5,
        h * 0.4,
        Math.max(w, h) * 0.85
      );
      radial.addColorStop(0, "rgba(56,189,248,0.18)");
      radial.addColorStop(0.35, "rgba(16,185,129,0.08)");
      radial.addColorStop(1, "transparent");
      ctx.fillStyle = radial;
      ctx.fillRect(0, 0, w, h);

      const time = performance.now() / 1000;

      particles.forEach((p, index) => {
        p.z += p.vz;
        p.x += p.vx;
        p.y += p.vy;
        p.life += 1;

        const depthNorm = Math.max(-1, Math.min(1, p.z / 700));
        const scale = 1 + depthNorm * 0.9;
        const appear = (p.z + 1200) / 900;
        const alpha = Math.min(1, Math.max(0, appear));

        const waveX = Math.sin(time * 2 + p.waveOffset) * 24 * (1 - alpha);
        const waveY = Math.cos(time * 1.6 + p.waveOffset) * 16 * (1 - alpha);

        ctx.save();
        ctx.globalAlpha = alpha * 0.95;

        if (p.type === "phrase" && p.text) {
          ctx.translate(p.x + waveX, p.y + waveY);

          // random tilt + subtle wobble
          const base = p.rotationBase ?? 0;
          const amp = p.rotationAmp ?? 0;
          const angle = base + amp * Math.sin(time * 0.9 + p.waveOffset);
          ctx.rotate(angle);

          ctx.scale(scale, scale);

          const baseFontSize = Math.min(Math.max(w * 0.04, 32), 56);
          ctx.font = `700 ${baseFontSize}px system-ui, -apple-system, Segoe UI, sans-serif`;
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";

          ctx.shadowColor = p.colorB;
          ctx.shadowBlur = 26;
          ctx.fillStyle = p.colorA;
          ctx.fillText(p.text, 0, 0);

          ctx.shadowBlur = 0;
          ctx.strokeStyle = "rgba(15,23,42,0.95)";
          ctx.lineWidth = 1.4;
          ctx.strokeText(p.text, 0, 0);
        } else {
          ctx.translate(p.x + waveX, p.y + waveY);
          ctx.scale(scale * 0.9, scale * 0.9);

          const size = 12;
          const grd = ctx.createLinearGradient(-size, -size, size, size);
          grd.addColorStop(0, `${p.colorA}33`);
          grd.addColorStop(1, `${p.colorB}55`);

          ctx.rotate(Math.sin(time * 0.7 + p.waveOffset) * 0.9);

          ctx.fillStyle = grd;
          ctx.strokeStyle = "rgba(148,163,184,0.5)";
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.roundRect(-size, -size, size * 2, size * 2, 4);
          ctx.fill();
          ctx.stroke();
        }

        ctx.restore();

        // Continuous respawn:
        // - phrases: when off-screen on the opposite side OR too old
        // - boxes: when too old or too close
        let expired = false;

        if (p.type === "phrase") {
          const margin = w * 0.25;
          if (p.direction === "left" && p.x > w + margin) expired = true;
          if (p.direction === "right" && p.x < -margin) expired = true;
        }

        if (p.life > p.maxLife || p.z > 250) {
          expired = true;
        }

        if (expired) {
          if (p.type === "phrase") {
            particles[index] = spawnPhraseParticle();
          } else {
            particles[index] = spawnBoxParticle();
          }
        }
      });

      animationFrameId = window.requestAnimationFrame(render);
    };

    animationFrameId = window.requestAnimationFrame(render);

    return () => {
      window.cancelAnimationFrame(animationFrameId);
      window.removeEventListener("resize", resize);
    };
  }, []);

  // IMPORTANT: keep this as w-full/h-full. In App.tsx, wrap it in:
  // <div className="pointer-events-none fixed inset-0 opacity-40"><HeroCanvas /></div>
  return <canvas ref={canvasRef} className="w-full h-full" />;
};
