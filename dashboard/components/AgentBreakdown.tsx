"use client";

import { motion } from "framer-motion";
import type { Finding, AgentKind } from "@/lib/types";

interface AgentBreakdownProps {
  findings: Finding[];
}

const AGENT_META: Record<
  AgentKind,
  {
    icon: React.ReactNode;
    label: string;
    color: string;
    iconBg: string;
    border: string;
  }
> = {
  security: {
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
        <path fillRule="evenodd" d="M12.516 2.17a.75.75 0 00-1.032 0 11.209 11.209 0 01-7.877 3.08.75.75 0 00-.722.515A12.74 12.74 0 002.25 9.75c0 5.942 4.064 10.933 9.563 12.348a.749.749 0 00.374 0c5.499-1.415 9.563-6.406 9.563-12.348 0-1.39-.223-2.73-.635-3.985a.75.75 0 00-.722-.516 11.209 11.209 0 01-7.877-3.08z" clipRule="evenodd" />
      </svg>
    ),
    label: "Security",
    color: "text-red-400",
    iconBg: "bg-red-500/10 text-red-400",
    border: "border-red-500/[0.08]",
  },
  performance: {
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
        <path fillRule="evenodd" d="M14.615 1.595a.75.75 0 01.359.852L12.982 9.75h7.268a.75.75 0 01.548 1.262l-10.5 11.25a.75.75 0 01-1.272-.71l1.992-7.302H3.75a.75.75 0 01-.548-1.262l10.5-11.25a.75.75 0 01.913-.143z" clipRule="evenodd" />
      </svg>
    ),
    label: "Performance",
    color: "text-amber-400",
    iconBg: "bg-amber-500/10 text-amber-400",
    border: "border-amber-500/[0.08]",
  },
  style: {
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
        <path d="M11.7 2.805a.75.75 0 01.6 0A60.65 60.65 0 0122.83 8.72a.75.75 0 01-.231 1.337 49.949 49.949 0 00-9.902 3.912l-.003.002-.34.18a.75.75 0 01-.707 0A50.009 50.009 0 007.5 12.174v-.224c0-.131.067-.248.172-.311a54.614 54.614 0 014.653-2.52.75.75 0 00-.65-1.352 56.129 56.129 0 00-4.78 2.589 1.858 1.858 0 00-.859 1.228 49.803 49.803 0 00-4.634-1.527.75.75 0 01-.231-1.337A60.653 60.653 0 0111.7 2.805z" />
        <path d="M13.06 15.473a48.45 48.45 0 017.666-3.282c.134 1.414.22 2.843.255 4.285a.75.75 0 01-.46.71 47.878 47.878 0 00-8.105 4.342.75.75 0 01-.832 0 47.877 47.877 0 00-8.104-4.342.75.75 0 01-.461-.71c.035-1.442.121-2.87.255-4.286A48.4 48.4 0 016 13.18v1.27a1.5 1.5 0 00-.14 2.508c-.09.38-.222.753-.397 1.11.452.213.901.434 1.346.661a6.729 6.729 0 00.551-1.608 1.5 1.5 0 00.14-2.67v-.645a48.549 48.549 0 013.44 1.668 2.25 2.25 0 002.12 0z" />
        <path d="M4.462 19.462c.42-.419.753-.89 1-1.394.453.213.902.434 1.347.661a6.743 6.743 0 01-1.286 1.794.75.75 0 11-1.06-1.06z" />
      </svg>
    ),
    label: "Style",
    color: "text-cyan-400",
    iconBg: "bg-cyan-500/10 text-cyan-400",
    border: "border-cyan-500/[0.08]",
  },
};

export default function AgentBreakdown({ findings }: AgentBreakdownProps) {
  const agents: AgentKind[] = ["security", "performance", "style"];

  const stats = agents.map((agent) => {
    const agentFindings = findings.filter((f) => f.agent === agent);
    const catCounts: Record<string, number> = {};
    agentFindings.forEach((f) => {
      catCounts[f.category] = (catCounts[f.category] ?? 0) + 1;
    });
    const topCategory =
      Object.entries(catCounts).sort((a, b) => b[1] - a[1])[0]?.[0] ?? "—";
    return {
      agent,
      count: agentFindings.length,
      topCategory,
      meta: AGENT_META[agent],
    };
  });

  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
      {stats.map(({ agent, count, topCategory, meta }, i) => (
        <motion.div
          key={agent}
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: i * 0.08 }}
          whileHover={{ y: -2, transition: { duration: 0.15 } }}
          className={`glass rounded-2xl p-5 border ${meta.border} transition-colors duration-300`}
        >
          <div className="flex items-center gap-3 mb-4">
            <div
              className={`w-9 h-9 rounded-xl ${meta.iconBg} flex items-center justify-center`}
            >
              {meta.icon}
            </div>
            <h3 className={`text-sm font-semibold ${meta.color}`}>
              {meta.label}
            </h3>
          </div>
          <p className="text-3xl font-bold text-white tabular-nums">{count}</p>
          <p className="text-[11px] text-zinc-600 mt-0.5 uppercase tracking-wider">
            findings
          </p>
          <div className="mt-4 pt-3 border-t border-white/[0.04]">
            <p className="text-[10px] text-zinc-600 uppercase tracking-wider">
              Top category
            </p>
            <p className="text-xs text-zinc-400 font-medium truncate mt-0.5">
              {topCategory}
            </p>
          </div>
        </motion.div>
      ))}
    </div>
  );
}
