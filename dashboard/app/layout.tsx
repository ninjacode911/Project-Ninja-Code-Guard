import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Ninja Code Guard",
  description:
    "Multi-agent AI code review dashboard — security, performance & style analysis at a glance.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased dark`}
    >
      <body className="noise min-h-full flex flex-col bg-[#050507] text-zinc-100">
        {/* ── Gradient orbs (ambient background) ── */}
        <div className="fixed inset-0 overflow-hidden pointer-events-none z-0">
          <div className="gradient-orb gradient-orb-1" />
          <div className="gradient-orb gradient-orb-2" />
          <div className="gradient-orb gradient-orb-3" />
        </div>

        {/* ── Navigation ── */}
        <header className="sticky top-0 z-50 border-b border-white/[0.06] bg-[#050507]/70 backdrop-blur-2xl">
          <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6 lg:px-8">
            <Link href="/" className="flex items-center gap-3 group">
              <span className="relative flex items-center justify-center w-9 h-9 rounded-xl bg-gradient-to-br from-violet-600 to-violet-800 shadow-lg shadow-violet-900/30 group-hover:shadow-violet-700/40 transition-shadow">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 24 24"
                  fill="currentColor"
                  className="w-5 h-5 text-white"
                >
                  <path
                    fillRule="evenodd"
                    d="M12.516 2.17a.75.75 0 00-1.032 0 11.209 11.209 0 01-7.877 3.08.75.75 0 00-.722.515A12.74 12.74 0 002.25 9.75c0 5.942 4.064 10.933 9.563 12.348a.749.749 0 00.374 0c5.499-1.415 9.563-6.406 9.563-12.348 0-1.39-.223-2.73-.635-3.985a.75.75 0 00-.722-.516 11.209 11.209 0 01-7.877-3.08z"
                    clipRule="evenodd"
                  />
                </svg>
              </span>
              <div className="flex flex-col">
                <span className="text-[15px] font-semibold tracking-tight text-white leading-tight">
                  Ninja Code Guard
                </span>
                <span className="text-[10px] font-medium text-zinc-500 tracking-widest uppercase">
                  AI Review Platform
                </span>
              </div>
            </Link>

            <nav className="flex items-center gap-1">
              <Link
                href="/"
                className="px-4 py-2 text-sm text-zinc-400 hover:text-white hover:bg-white/[0.04] rounded-lg transition-all duration-200"
              >
                Dashboard
              </Link>
              <a
                href="https://github.com"
                target="_blank"
                rel="noopener noreferrer"
                className="px-4 py-2 text-sm text-zinc-400 hover:text-white hover:bg-white/[0.04] rounded-lg transition-all duration-200"
              >
                GitHub
              </a>
            </nav>
          </div>
        </header>

        {/* ── Content ── */}
        <main className="relative z-10 flex-1">{children}</main>

        {/* ── Footer ── */}
        <footer className="relative z-10 border-t border-white/[0.04] py-8">
          <div className="mx-auto max-w-7xl px-6 lg:px-8 flex items-center justify-between">
            <p className="text-xs text-zinc-600">
              &copy; {new Date().getFullYear()} Ninja Code Guard
            </p>
            <p className="text-xs text-zinc-700">
              Multi-Agent AI Code Review Platform
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
