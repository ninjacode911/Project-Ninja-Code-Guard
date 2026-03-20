"use client";

import { useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { Finding, Severity } from "@/lib/types";
import SeverityBadge from "./SeverityBadge";

const AGENT_ICON: Record<string, React.ReactNode> = {
  security: (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 text-red-400">
      <path fillRule="evenodd" d="M12.516 2.17a.75.75 0 00-1.032 0 11.209 11.209 0 01-7.877 3.08.75.75 0 00-.722.515A12.74 12.74 0 002.25 9.75c0 5.942 4.064 10.933 9.563 12.348a.749.749 0 00.374 0c5.499-1.415 9.563-6.406 9.563-12.348 0-1.39-.223-2.73-.635-3.985a.75.75 0 00-.722-.516 11.209 11.209 0 01-7.877-3.08z" clipRule="evenodd" />
    </svg>
  ),
  performance: (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 text-amber-400">
      <path fillRule="evenodd" d="M14.615 1.595a.75.75 0 01.359.852L12.982 9.75h7.268a.75.75 0 01.548 1.262l-10.5 11.25a.75.75 0 01-1.272-.71l1.992-7.302H3.75a.75.75 0 01-.548-1.262l10.5-11.25a.75.75 0 01.913-.143z" clipRule="evenodd" />
    </svg>
  ),
  style: (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 text-cyan-400">
      <path d="M11.7 2.805a.75.75 0 01.6 0A60.65 60.65 0 0122.83 8.72a.75.75 0 01-.231 1.337 49.949 49.949 0 00-9.902 3.912l-.003.002-.34.18a.75.75 0 01-.707 0A50.009 50.009 0 007.5 12.174v-.224c0-.131.067-.248.172-.311a54.614 54.614 0 014.653-2.52.75.75 0 00-.65-1.352 56.129 56.129 0 00-4.78 2.589 1.858 1.858 0 00-.859 1.228 49.803 49.803 0 00-4.634-1.527.75.75 0 01-.231-1.337A60.653 60.653 0 0111.7 2.805z" />
      <path d="M13.06 15.473a48.45 48.45 0 017.666-3.282c.134 1.414.22 2.843.255 4.285a.75.75 0 01-.46.71 47.878 47.878 0 00-8.105 4.342.75.75 0 01-.832 0 47.877 47.877 0 00-8.104-4.342.75.75 0 01-.461-.71c.035-1.442.121-2.87.255-4.286z" />
    </svg>
  ),
};

const SEVERITY_ORDER: Record<Severity, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
};

type SortKey = "severity" | "agent" | "file_path" | "category" | "title";

export default function FindingsTable({
  findings,
}: {
  findings: Finding[];
}) {
  const [sortKey, setSortKey] = useState<SortKey>("severity");
  const [sortAsc, setSortAsc] = useState(true);
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);

  const sorted = useMemo(() => {
    const copy = [...findings];
    copy.sort((a, b) => {
      let cmp = 0;
      if (sortKey === "severity") {
        cmp = SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity];
      } else {
        cmp = (a[sortKey] as string).localeCompare(b[sortKey] as string);
      }
      return sortAsc ? cmp : -cmp;
    });
    return copy;
  }, [findings, sortKey, sortAsc]);

  function handleSort(key: SortKey) {
    if (key === sortKey) setSortAsc((v) => !v);
    else {
      setSortKey(key);
      setSortAsc(true);
    }
  }

  const arrow = (key: SortKey) =>
    sortKey === key ? (sortAsc ? " \u25B2" : " \u25BC") : "";

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 0.1 }}
      className="overflow-x-auto glass rounded-2xl"
    >
      <table className="w-full text-sm text-left">
        <thead>
          <tr className="border-b border-white/[0.04] text-zinc-500 text-[11px] uppercase tracking-wider">
            {(
              [
                ["severity", "Severity"],
                ["agent", "Agent"],
                ["file_path", "File"],
                ["category", "Category"],
                ["title", "Title"],
              ] as [SortKey, string][]
            ).map(([key, label]) => (
              <th
                key={key}
                onClick={() => handleSort(key)}
                className="px-4 py-3.5 cursor-pointer select-none hover:text-zinc-300 transition-colors font-medium"
              >
                {label}
                <span className="text-violet-400/70">{arrow(key)}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((f, i) => {
            const isExpanded = expandedIdx === i;
            return (
              <tr key={i} className="group">
                <td colSpan={5} className="p-0">
                  <button
                    onClick={() => setExpandedIdx(isExpanded ? null : i)}
                    className="w-full grid grid-cols-[100px_50px_1fr_130px_1fr] items-center text-left px-4 py-3 border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors cursor-pointer"
                  >
                    <span>
                      <SeverityBadge severity={f.severity} />
                    </span>
                    <span title={f.agent}>
                      {AGENT_ICON[f.agent] ?? f.agent}
                    </span>
                    <span className="font-mono text-zinc-400 text-xs truncate pr-2">
                      {f.file_path}
                      <span className="text-zinc-700 ml-1">
                        :{f.line_start}
                      </span>
                    </span>
                    <span className="text-zinc-500 text-xs">{f.category}</span>
                    <span className="text-zinc-300 text-xs truncate">
                      {f.title}
                    </span>
                  </button>

                  <AnimatePresence>
                    {isExpanded && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.25, ease: "easeInOut" }}
                        className="overflow-hidden"
                      >
                        <div className="bg-white/[0.01] border-b border-white/[0.04] px-6 py-5 space-y-4">
                          <div>
                            <h4 className="text-[10px] text-zinc-600 uppercase tracking-widest mb-1.5 font-medium">
                              Description
                            </h4>
                            <p className="text-zinc-300 text-sm leading-relaxed">
                              {f.description}
                            </p>
                          </div>
                          {f.suggested_fix && (
                            <div>
                              <h4 className="text-[10px] text-zinc-600 uppercase tracking-widest mb-1.5 font-medium">
                                Suggested Fix
                              </h4>
                              <pre className="text-emerald-400/90 text-xs bg-emerald-500/[0.04] border border-emerald-500/10 rounded-xl px-4 py-3 overflow-x-auto whitespace-pre-wrap font-mono">
                                {f.suggested_fix}
                              </pre>
                            </div>
                          )}
                          <div className="flex gap-5 text-[11px] text-zinc-600 pt-1">
                            {f.cwe_id && (
                              <span className="font-mono">{f.cwe_id}</span>
                            )}
                            <span>
                              Confidence:{" "}
                              <span className="text-zinc-400">
                                {(f.confidence * 100).toFixed(0)}%
                              </span>
                            </span>
                            <span>
                              Lines{" "}
                              <span className="text-zinc-400 font-mono">
                                {f.line_start}–{f.line_end}
                              </span>
                            </span>
                          </div>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </motion.div>
  );
}
