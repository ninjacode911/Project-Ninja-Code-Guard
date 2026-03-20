import Link from "next/link";
import { getRepoReviews, getRepoStats } from "@/lib/api";
import HealthScoreRing from "@/components/HealthScoreRing";
import TrendChart from "@/components/TrendChart";
import AgentBreakdown from "@/components/AgentBreakdown";
import SeverityBadge from "@/components/SeverityBadge";
import type { Severity } from "@/lib/types";

export default async function RepoPage({
  params,
}: {
  params: Promise<{ owner: string; repo: string }>;
}) {
  const { owner, repo } = await params;
  const [reviews, stats] = await Promise.all([
    getRepoReviews(owner, repo),
    getRepoStats(owner, repo),
  ]);

  const latestScore = reviews[0]?.health_score ?? 0;
  const previousScore = reviews[1]?.health_score;
  const allFindings = reviews.flatMap((r) => r.findings);

  return (
    <div className="dot-grid">
      <div className="mx-auto max-w-7xl px-6 lg:px-8 py-10">
        {/* ── Breadcrumb ── */}
        <nav className="flex items-center gap-2 text-sm text-zinc-600 mb-8">
          <Link href="/" className="hover:text-zinc-400 transition-colors">
            Dashboard
          </Link>
          <svg className="w-3.5 h-3.5 text-zinc-700" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>
          <span className="text-zinc-400 font-medium">
            {owner}/{repo}
          </span>
        </nav>

        {/* ── Header ── */}
        <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-6 mb-12">
          <div>
            <p className="text-xs text-zinc-600 font-mono mb-1">{owner}/</p>
            <h1 className="text-3xl font-bold text-white">{repo}</h1>
          </div>
          <div className="flex items-center gap-8 text-sm">
            {[
              { label: "Reviews", value: stats.total_reviews },
              { label: "Findings", value: stats.total_findings },
              { label: "Avg Score", value: `${stats.average_health_score}%` },
            ].map((s) => (
              <div key={s.label} className="text-center">
                <p className="text-2xl font-bold text-white tabular-nums">
                  {s.value}
                </p>
                <p className="text-[10px] text-zinc-600 uppercase tracking-wider mt-0.5">
                  {s.label}
                </p>
              </div>
            ))}
          </div>
        </div>

        {/* ── Score + Trend ── */}
        <div className="grid grid-cols-1 lg:grid-cols-[200px_1fr] gap-8 mb-12">
          <div className="flex items-center justify-center">
            <HealthScoreRing
              score={latestScore}
              previousScore={previousScore}
              label="Latest Score"
            />
          </div>
          <TrendChart scores={stats.recent_scores} />
        </div>

        {/* ── Agent Breakdown ── */}
        <section className="mb-12">
          <h2 className="text-sm font-semibold text-zinc-400 mb-4 uppercase tracking-wider">
            Agent Breakdown
          </h2>
          <AgentBreakdown findings={allFindings} />
        </section>

        {/* ── PR Reviews Table ── */}
        <section>
          <h2 className="text-sm font-semibold text-zinc-400 mb-4 uppercase tracking-wider">
            Recent PR Reviews
          </h2>
          <div className="overflow-x-auto glass rounded-2xl">
            <table className="w-full text-sm text-left">
              <thead>
                <tr className="border-b border-white/[0.04] text-zinc-500 text-[11px] uppercase tracking-wider">
                  <th className="px-5 py-3.5 font-medium">PR</th>
                  <th className="px-5 py-3.5 font-medium">Score</th>
                  <th className="px-5 py-3.5 font-medium">Critical</th>
                  <th className="px-5 py-3.5 font-medium">High</th>
                  <th className="px-5 py-3.5 font-medium">Medium</th>
                  <th className="px-5 py-3.5 font-medium">Low</th>
                  <th className="px-5 py-3.5 font-medium">Summary</th>
                  <th className="px-5 py-3.5 font-medium">Duration</th>
                </tr>
              </thead>
              <tbody>
                {reviews.map((r) => {
                  const scoreClass =
                    r.health_score >= 80
                      ? "text-emerald-400"
                      : r.health_score >= 60
                      ? "text-amber-400"
                      : "text-red-400";

                  return (
                    <tr
                      key={r.id}
                      className="border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors"
                    >
                      <td className="px-5 py-3.5">
                        <Link
                          href={`/repos/${owner}/${repo}/prs/${r.pr_number}`}
                          className="text-violet-400 hover:text-violet-300 font-medium transition-colors"
                        >
                          #{r.pr_number}
                        </Link>
                      </td>
                      <td className={`px-5 py-3.5 font-bold tabular-nums ${scoreClass}`}>
                        {r.health_score}
                      </td>
                      <td className="px-5 py-3.5">
                        {r.critical_count > 0 ? (
                          <SeverityBadge severity={"critical" as Severity} />
                        ) : (
                          <span className="text-zinc-700">0</span>
                        )}
                      </td>
                      <td className="px-5 py-3.5">
                        {r.high_count > 0 ? (
                          <span className="text-orange-400 font-medium tabular-nums">
                            {r.high_count}
                          </span>
                        ) : (
                          <span className="text-zinc-700">0</span>
                        )}
                      </td>
                      <td className="px-5 py-3.5">
                        {r.medium_count > 0 ? (
                          <span className="text-amber-400 tabular-nums">
                            {r.medium_count}
                          </span>
                        ) : (
                          <span className="text-zinc-700">0</span>
                        )}
                      </td>
                      <td className="px-5 py-3.5 text-zinc-600 tabular-nums">
                        {r.low_count}
                      </td>
                      <td className="px-5 py-3.5 text-zinc-500 truncate max-w-[240px] text-xs">
                        {r.summary}
                      </td>
                      <td className="px-5 py-3.5 text-zinc-600 tabular-nums text-xs font-mono">
                        {(r.duration_ms / 1000).toFixed(1)}s
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  );
}
