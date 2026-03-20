"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { MOCK_REPOS } from "@/lib/api";
import {
  StaggerContainer,
  StaggerItem,
  FadeIn,
  HoverCard,
} from "@/components/motion";
import { AnimatedCounter } from "@/components/AnimatedCounter";

function scoreColor(score: number): string {
  if (score >= 80) return "text-emerald-400";
  if (score >= 60) return "text-amber-400";
  return "text-red-400";
}

function scoreGlow(score: number): string {
  if (score >= 80) return "group-hover:shadow-emerald-500/10";
  if (score >= 60) return "group-hover:shadow-amber-500/10";
  return "group-hover:shadow-red-500/10";
}

function scoreDot(score: number): string {
  if (score >= 80) return "bg-emerald-400";
  if (score >= 60) return "bg-amber-400";
  return "bg-red-400";
}

const STATS = [
  { label: "Repos Monitored", value: MOCK_REPOS.length, suffix: "" },
  {
    label: "Avg Health Score",
    value: Math.round(
      MOCK_REPOS.reduce((s, r) => s + r.health_score, 0) / MOCK_REPOS.length
    ),
    suffix: "%",
  },
  { label: "PRs Reviewed", value: 47, suffix: "" },
  { label: "Issues Found", value: 132, suffix: "" },
];

const AGENTS = [
  {
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-6 h-6">
        <path fillRule="evenodd" d="M12.516 2.17a.75.75 0 00-1.032 0 11.209 11.209 0 01-7.877 3.08.75.75 0 00-.722.515A12.74 12.74 0 002.25 9.75c0 5.942 4.064 10.933 9.563 12.348a.749.749 0 00.374 0c5.499-1.415 9.563-6.406 9.563-12.348 0-1.39-.223-2.73-.635-3.985a.75.75 0 00-.722-.516 11.209 11.209 0 01-7.877-3.08z" clipRule="evenodd" />
      </svg>
    ),
    title: "Security Agent",
    desc: "Scans for vulnerabilities, injection flaws, auth issues, and CWE-classified risks using Bandit and detect-secrets.",
    color: "text-red-400",
    bg: "from-red-500/10 via-red-500/5 to-transparent",
    iconBg: "bg-red-500/10 text-red-400",
    border: "border-red-500/10 hover:border-red-500/20",
  },
  {
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-6 h-6">
        <path fillRule="evenodd" d="M14.615 1.595a.75.75 0 01.359.852L12.982 9.75h7.268a.75.75 0 01.548 1.262l-10.5 11.25a.75.75 0 01-1.272-.71l1.992-7.302H3.75a.75.75 0 01-.548-1.262l10.5-11.25a.75.75 0 01.913-.143z" clipRule="evenodd" />
      </svg>
    ),
    title: "Performance Agent",
    desc: "Detects N+1 queries, memory leaks, blocking operations, and algorithmic inefficiencies with Radon analysis.",
    color: "text-amber-400",
    bg: "from-amber-500/10 via-amber-500/5 to-transparent",
    iconBg: "bg-amber-500/10 text-amber-400",
    border: "border-amber-500/10 hover:border-amber-500/20",
  },
  {
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-6 h-6">
        <path d="M11.7 2.805a.75.75 0 01.6 0A60.65 60.65 0 0122.83 8.72a.75.75 0 01-.231 1.337 49.949 49.949 0 00-9.902 3.912l-.003.002-.34.18a.75.75 0 01-.707 0A50.009 50.009 0 007.5 12.174v-.224c0-.131.067-.248.172-.311a54.614 54.614 0 014.653-2.52.75.75 0 00-.65-1.352 56.129 56.129 0 00-4.78 2.589 1.858 1.858 0 00-.859 1.228 49.803 49.803 0 00-4.634-1.527.75.75 0 01-.231-1.337A60.653 60.653 0 0111.7 2.805z" />
        <path d="M13.06 15.473a48.45 48.45 0 017.666-3.282c.134 1.414.22 2.843.255 4.285a.75.75 0 01-.46.71 47.878 47.878 0 00-8.105 4.342.75.75 0 01-.832 0 47.877 47.877 0 00-8.104-4.342.75.75 0 01-.461-.71c.035-1.442.121-2.87.255-4.286A48.4 48.4 0 016 13.18v1.27a1.5 1.5 0 00-.14 2.508c-.09.38-.222.753-.397 1.11.452.213.901.434 1.346.661a6.729 6.729 0 00.551-1.608 1.5 1.5 0 00.14-2.67v-.645a48.549 48.549 0 013.44 1.668 2.25 2.25 0 002.12 0z" />
        <path d="M4.462 19.462c.42-.419.753-.89 1-1.394.453.213.902.434 1.347.661a6.743 6.743 0 01-1.286 1.794.75.75 0 11-1.06-1.06z" />
      </svg>
    ),
    title: "Style Agent",
    desc: "Enforces naming conventions, reduces complexity, and ensures code consistency via Ruff linting.",
    color: "text-cyan-400",
    bg: "from-cyan-500/10 via-cyan-500/5 to-transparent",
    iconBg: "bg-cyan-500/10 text-cyan-400",
    border: "border-cyan-500/10 hover:border-cyan-500/20",
  },
];

export default function HomePage() {
  return (
    <div className="dot-grid">
      <div className="mx-auto max-w-7xl px-6 lg:px-8 py-16">
        {/* ── Hero ── */}
        <section className="text-center mb-20 pt-8">
          <FadeIn delay={0}>
            <div className="inline-flex items-center gap-2 rounded-full border border-violet-500/20 bg-violet-500/[0.06] px-4 py-1.5 text-sm text-violet-300 mb-8">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-violet-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-violet-500" />
              </span>
              Multi-Agent AI Review Platform
            </div>
          </FadeIn>

          <FadeIn delay={0.1}>
            <h1 className="text-5xl sm:text-7xl font-bold tracking-tight mb-6">
              <span className="text-white">Code reviews,</span>
              <br />
              <span className="text-gradient">reimagined.</span>
            </h1>
          </FadeIn>

          <FadeIn delay={0.2}>
            <p className="text-lg sm:text-xl text-zinc-400 max-w-2xl mx-auto leading-relaxed">
              Three specialised AI agents analyse every pull request for{" "}
              <span className="text-red-400 font-medium">security</span>,{" "}
              <span className="text-amber-400 font-medium">performance</span>,
              and{" "}
              <span className="text-cyan-400 font-medium">style</span>{" "}
              — then synthesise a single, actionable review.
            </p>
          </FadeIn>
        </section>

        {/* ── Stats ── */}
        <FadeIn delay={0.3}>
          <section className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-20">
            {STATS.map((s, i) => (
              <div
                key={s.label}
                className="glass rounded-2xl p-5 text-center"
              >
                <p className="text-3xl sm:text-4xl font-bold text-white tabular-nums">
                  <AnimatedCounter
                    value={s.value}
                    suffix={s.suffix}
                    duration={1200 + i * 200}
                  />
                </p>
                <p className="text-xs text-zinc-500 mt-2 font-medium tracking-wide uppercase">
                  {s.label}
                </p>
              </div>
            ))}
          </section>
        </FadeIn>

        {/* ── Repositories ── */}
        <section className="mb-24">
          <FadeIn delay={0.15}>
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-semibold text-white">
                Repositories
              </h2>
              <span className="text-xs text-zinc-600 font-mono">
                {MOCK_REPOS.length} monitored
              </span>
            </div>
          </FadeIn>

          <StaggerContainer className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {MOCK_REPOS.map((repo) => (
              <StaggerItem key={repo.full_name}>
                <HoverCard>
                  <Link
                    href={`/repos/${repo.owner}/${repo.repo}`}
                    className={`group block glass glass-hover rounded-2xl p-6 transition-all duration-300 hover:shadow-xl ${scoreGlow(
                      repo.health_score
                    )}`}
                  >
                    <div className="flex items-start justify-between mb-5">
                      <div>
                        <p className="text-xs text-zinc-600 font-mono mb-1">
                          {repo.owner}/
                        </p>
                        <p className="text-base font-semibold text-zinc-200 group-hover:text-white transition-colors">
                          {repo.repo}
                        </p>
                      </div>
                      <div className="text-right">
                        <span
                          className={`text-3xl font-bold tabular-nums ${scoreColor(
                            repo.health_score
                          )}`}
                        >
                          {repo.health_score}
                        </span>
                      </div>
                    </div>

                    {/* Mini bar */}
                    <div className="w-full h-1.5 rounded-full bg-white/[0.04] mb-4 overflow-hidden">
                      <motion.div
                        initial={{ width: 0 }}
                        animate={{ width: `${repo.health_score}%` }}
                        transition={{
                          duration: 1,
                          delay: 0.5,
                          ease: [0.25, 0.46, 0.45, 0.94],
                        }}
                        className={`h-full rounded-full ${
                          repo.health_score >= 80
                            ? "bg-emerald-500"
                            : repo.health_score >= 60
                            ? "bg-amber-500"
                            : "bg-red-500"
                        }`}
                      />
                    </div>

                    <div className="flex items-center justify-between text-xs text-zinc-500">
                      <span className="flex items-center gap-1.5">
                        <span className={`w-1.5 h-1.5 rounded-full ${scoreDot(repo.health_score)}`} />
                        {repo.open_prs} open PRs
                      </span>
                      <span>{repo.last_review}</span>
                    </div>
                  </Link>
                </HoverCard>
              </StaggerItem>
            ))}
          </StaggerContainer>
        </section>

        {/* ── How It Works ── */}
        <section className="mb-12">
          <FadeIn>
            <div className="text-center mb-12">
              <h2 className="text-2xl font-bold text-white mb-3">
                How It Works
              </h2>
              <p className="text-sm text-zinc-500 max-w-lg mx-auto">
                Each PR triggers three specialised agents that run in parallel,
                then a synthesizer merges their findings into one review.
              </p>
            </div>
          </FadeIn>

          {/* Pipeline visualization */}
          <FadeIn delay={0.1}>
            <div className="flex items-center justify-center mb-12">
              <div className="flex items-center gap-2 text-xs font-mono text-zinc-500">
                <span className="px-3 py-1.5 rounded-lg glass border border-white/[0.06]">
                  PR Opened
                </span>
                <svg className="w-4 h-4 text-zinc-700" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>
                <span className="px-3 py-1.5 rounded-lg glass border border-violet-500/20 text-violet-400">
                  3 Agents
                </span>
                <svg className="w-4 h-4 text-zinc-700" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>
                <span className="px-3 py-1.5 rounded-lg glass border border-cyan-500/20 text-cyan-400">
                  Synthesize
                </span>
                <svg className="w-4 h-4 text-zinc-700" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>
                <span className="px-3 py-1.5 rounded-lg glass border border-emerald-500/20 text-emerald-400">
                  Review Posted
                </span>
              </div>
            </div>
          </FadeIn>

          <StaggerContainer className="grid grid-cols-1 sm:grid-cols-3 gap-5">
            {AGENTS.map((agent) => (
              <StaggerItem key={agent.title}>
                <HoverCard>
                  <div
                    className={`glass rounded-2xl p-6 border ${agent.border} transition-all duration-300 h-full`}
                  >
                    <div
                      className={`w-11 h-11 rounded-xl ${agent.iconBg} flex items-center justify-center mb-4`}
                    >
                      {agent.icon}
                    </div>
                    <h3
                      className={`text-base font-semibold mb-2 ${agent.color}`}
                    >
                      {agent.title}
                    </h3>
                    <p className="text-sm text-zinc-500 leading-relaxed">
                      {agent.desc}
                    </p>
                  </div>
                </HoverCard>
              </StaggerItem>
            ))}
          </StaggerContainer>
        </section>
      </div>
    </div>
  );
}
