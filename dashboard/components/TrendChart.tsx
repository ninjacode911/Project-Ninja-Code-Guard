"use client";

import { motion } from "framer-motion";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
  Area,
  AreaChart,
} from "recharts";

interface TrendChartProps {
  scores: number[];
  height?: number;
}

export default function TrendChart({ scores, height = 280 }: TrendChartProps) {
  const data = scores.map((score, i) => ({
    review: `#${i + 1}`,
    score,
  }));

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.2 }}
      className="w-full glass rounded-2xl p-5"
    >
      <div className="flex items-center justify-between mb-5">
        <h3 className="text-sm font-medium text-zinc-400">
          Health Score Trend
        </h3>
        <span className="text-xs text-zinc-600 font-mono">
          {scores.length} reviews
        </span>
      </div>
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={data}>
          <defs>
            <linearGradient id="scoreArea" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#8b5cf6" stopOpacity={0.15} />
              <stop offset="100%" stopColor="#8b5cf6" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid
            strokeDasharray="3 3"
            stroke="rgba(255,255,255,0.03)"
            vertical={false}
          />
          <XAxis
            dataKey="review"
            tick={{ fill: "#52525b", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            domain={[0, 100]}
            tick={{ fill: "#52525b", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            width={30}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "rgba(24, 24, 27, 0.9)",
              border: "1px solid rgba(255,255,255,0.06)",
              borderRadius: "12px",
              color: "#e4e4e7",
              fontSize: "0.8rem",
              backdropFilter: "blur(12px)",
              boxShadow: "0 8px 32px rgba(0,0,0,0.3)",
            }}
            itemStyle={{ color: "#a78bfa" }}
            labelStyle={{ color: "#71717a", marginBottom: 4 }}
          />
          <ReferenceLine
            y={80}
            stroke="rgba(52,211,153,0.2)"
            strokeDasharray="6 4"
            label={{
              value: "Healthy",
              fill: "#34d399",
              fontSize: 10,
              position: "insideTopRight",
            }}
          />
          <Area
            type="monotone"
            dataKey="score"
            fill="url(#scoreArea)"
            stroke="none"
          />
          <Line
            type="monotone"
            dataKey="score"
            stroke="#a78bfa"
            strokeWidth={2}
            dot={{ r: 3, fill: "#a78bfa", strokeWidth: 0 }}
            activeDot={{
              r: 5,
              fill: "#c4b5fd",
              strokeWidth: 0,
              filter: "drop-shadow(0 0 6px rgba(167,139,250,0.4))",
            }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </motion.div>
  );
}
