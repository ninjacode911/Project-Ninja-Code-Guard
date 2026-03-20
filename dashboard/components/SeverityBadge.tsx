import type { Severity } from "@/lib/types";

const CONFIG: Record<
  Severity,
  { bg: string; text: string; label: string; dot: string }
> = {
  critical: {
    bg: "bg-red-500/10",
    text: "text-red-400",
    label: "Critical",
    dot: "bg-red-400",
  },
  high: {
    bg: "bg-orange-500/10",
    text: "text-orange-400",
    label: "High",
    dot: "bg-orange-400",
  },
  medium: {
    bg: "bg-amber-500/10",
    text: "text-amber-400",
    label: "Medium",
    dot: "bg-amber-400",
  },
  low: {
    bg: "bg-zinc-500/10",
    text: "text-zinc-400",
    label: "Low",
    dot: "bg-zinc-500",
  },
};

export default function SeverityBadge({ severity }: { severity: Severity }) {
  const c = CONFIG[severity];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold tracking-wide uppercase ${c.bg} ${c.text}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${c.dot}`} />
      {c.label}
    </span>
  );
}
