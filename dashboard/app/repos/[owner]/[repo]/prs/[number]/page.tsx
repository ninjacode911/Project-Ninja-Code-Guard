import Link from "next/link";
import { getReviewDetail } from "@/lib/api";
import HealthScoreRing from "@/components/HealthScoreRing";
import FindingsTable from "@/components/FindingsTable";
import AgentBreakdown from "@/components/AgentBreakdown";
import type { Recommendation } from "@/lib/types";

const RECOMMENDATION_STYLE: Record<
  Recommendation,
  { bg: string; text: string; label: string; dot: string }
> = {
  approve: {
    bg: "bg-emerald-500/10",
    text: "text-emerald-400",
    label: "Approve",
    dot: "bg-emerald-400",
  },
  request_changes: {
    bg: "bg-amber-500/10",
    text: "text-amber-400",
    label: "Request Changes",
    dot: "bg-amber-400",
  },
  block: {
    bg: "bg-red-500/10",
    text: "text-red-400",
    label: "Block",
    dot: "bg-red-400",
  },
};

export default async function PRReviewPage({
  params,
}: {
  params: Promise<{ owner: string; repo: string; number: string }>;
}) {
  const { owner, repo, number: prNum } = await params;
  const prNumber = parseInt(prNum, 10);
  const { review, record } = await getReviewDetail(owner, repo, prNumber);

  const rec = RECOMMENDATION_STYLE[review.recommendation];

  return (
    <div className="dot-grid">
      <div className="mx-auto max-w-7xl px-6 lg:px-8 py-10">
        {/* ── Breadcrumb ── */}
        <nav className="flex items-center gap-2 text-sm text-zinc-600 mb-8">
          <Link href="/" className="hover:text-zinc-400 transition-colors">
            Dashboard
          </Link>
          <svg className="w-3.5 h-3.5 text-zinc-700" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>
          <Link
            href={`/repos/${owner}/${repo}`}
            className="hover:text-zinc-400 transition-colors"
          >
            {owner}/{repo}
          </Link>
          <svg className="w-3.5 h-3.5 text-zinc-700" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>
          <span className="text-zinc-400 font-medium">PR #{prNumber}</span>
        </nav>

        {/* ── Header ── */}
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-6 mb-12">
          <div>
            <p className="text-xs text-zinc-600 font-mono mb-1">
              {owner}/{repo}
            </p>
            <h1 className="text-3xl font-bold text-white mb-4">
              Pull Request #{prNumber}
            </h1>
            <div className="flex items-center gap-3">
              <span
                className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold ${rec.bg} ${rec.text}`}
              >
                <span className={`w-1.5 h-1.5 rounded-full ${rec.dot}`} />
                {rec.label}
              </span>
              <span className="text-[11px] text-zinc-600 font-mono">
                {record.commit_sha}
              </span>
              <span className="text-[11px] text-zinc-700 font-mono">
                {(record.duration_ms / 1000).toFixed(1)}s
              </span>
            </div>
          </div>
          <HealthScoreRing
            score={review.health_score}
            size={140}
            label="Health Score"
          />
        </div>

        {/* ── Executive Summary ── */}
        <section className="glass rounded-2xl p-6 mb-8">
          <h2 className="text-[10px] text-zinc-600 uppercase tracking-widest font-medium mb-3">
            Executive Summary
          </h2>
          <p className="text-zinc-300 leading-relaxed text-[15px]">
            {review.executive_summary}
          </p>
        </section>

        {/* ── Severity Counts ── */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
          {[
            {
              label: "Critical",
              count: review.critical_count,
              color: "text-red-400",
              border: "border-red-500/[0.08]",
              dot: "bg-red-400",
            },
            {
              label: "High",
              count: review.high_count,
              color: "text-orange-400",
              border: "border-orange-500/[0.08]",
              dot: "bg-orange-400",
            },
            {
              label: "Medium",
              count: review.medium_count,
              color: "text-amber-400",
              border: "border-amber-500/[0.08]",
              dot: "bg-amber-400",
            },
            {
              label: "Low",
              count: review.low_count,
              color: "text-zinc-400",
              border: "border-zinc-700/30",
              dot: "bg-zinc-500",
            },
          ].map((s) => (
            <div
              key={s.label}
              className={`glass rounded-2xl border ${s.border} p-5 text-center`}
            >
              <p className={`text-3xl font-bold tabular-nums ${s.color}`}>
                {s.count}
              </p>
              <p className="text-[10px] text-zinc-600 mt-1 uppercase tracking-wider flex items-center justify-center gap-1.5">
                <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} />
                {s.label}
              </p>
            </div>
          ))}
        </div>

        {/* ── Agent Breakdown ── */}
        <section className="mb-8">
          <h2 className="text-sm font-semibold text-zinc-400 mb-4 uppercase tracking-wider">
            Agent Breakdown
          </h2>
          <AgentBreakdown findings={review.findings} />
        </section>

        {/* ── Findings ── */}
        <section>
          <h2 className="text-sm font-semibold text-zinc-400 mb-4 uppercase tracking-wider">
            All Findings ({review.findings.length})
          </h2>
          <FindingsTable findings={review.findings} />
        </section>
      </div>
    </div>
  );
}
