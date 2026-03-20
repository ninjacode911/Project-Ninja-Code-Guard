"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";

interface HealthScoreRingProps {
  score: number;
  size?: number;
  strokeWidth?: number;
  previousScore?: number;
  label?: string;
}

function scoreColor(score: number): string {
  if (score >= 80) return "#34d399"; // emerald-400
  if (score >= 60) return "#fbbf24"; // amber-400
  return "#f87171"; // red-400
}

function scoreColorClass(score: number): string {
  if (score >= 80) return "text-emerald-400";
  if (score >= 60) return "text-amber-400";
  return "text-red-400";
}

function scoreGlow(score: number): string {
  if (score >= 80) return "rgba(52,211,153,0.2)";
  if (score >= 60) return "rgba(251,191,36,0.15)";
  return "rgba(248,113,113,0.2)";
}

export default function HealthScoreRing({
  score,
  size = 180,
  strokeWidth = 10,
  previousScore,
  label,
}: HealthScoreRingProps) {
  const [animatedScore, setAnimatedScore] = useState(0);

  useEffect(() => {
    let raf: number;
    const start = performance.now();
    const duration = 1200;

    function tick(now: number) {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      const ease = 1 - Math.pow(1 - progress, 4);
      setAnimatedScore(Math.round(score * ease));
      if (progress < 1) raf = requestAnimationFrame(tick);
    }

    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [score]);

  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference - (animatedScore / 100) * circumference;
  const color = scoreColor(animatedScore);
  const delta =
    previousScore !== undefined ? score - previousScore : undefined;

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.6, ease: [0.25, 0.46, 0.45, 0.94] }}
      className="flex flex-col items-center gap-3"
    >
      <div className="relative" style={{ width: size, height: size }}>
        <svg
          width={size}
          height={size}
          className="transform -rotate-90"
          style={{ filter: `drop-shadow(0 0 20px ${scoreGlow(animatedScore)})` }}
        >
          {/* background track */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke="rgba(255,255,255,0.04)"
            strokeWidth={strokeWidth}
          />
          {/* gradient arc */}
          <defs>
            <linearGradient id={`scoreGrad-${size}`} x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity="1" />
              <stop offset="100%" stopColor={color} stopOpacity="0.5" />
            </linearGradient>
          </defs>
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={`url(#scoreGrad-${size})`}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
            style={{ transition: "stroke-dashoffset 0.05s linear" }}
          />
        </svg>

        {/* centered text */}
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span
            className={`text-4xl font-bold tabular-nums ${scoreColorClass(animatedScore)}`}
          >
            {animatedScore}
          </span>
          {delta !== undefined && (
            <motion.span
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 1, duration: 0.4 }}
              className={`text-xs font-medium mt-0.5 ${
                delta > 0
                  ? "text-emerald-400"
                  : delta < 0
                  ? "text-red-400"
                  : "text-zinc-600"
              }`}
            >
              {delta > 0 ? "+" : ""}
              {delta} pts
            </motion.span>
          )}
        </div>
      </div>
      {label && (
        <span className="text-xs text-zinc-500 font-medium tracking-wide uppercase">
          {label}
        </span>
      )}
    </motion.div>
  );
}
