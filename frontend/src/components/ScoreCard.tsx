import type { AnalysisResult } from "../types/wcag";

export function ScoreCard({ score }: { score: AnalysisResult["score"] }) {
  const categories = [
    { level: "A", label: "Level A", color: "text-red-400", bg: "bg-red-500/5", border: "border-red-500/10" },
    { level: "AA", label: "Level AA", color: "text-amber-400", bg: "bg-amber-500/5", border: "border-amber-500/10" },
    { level: "AAA", label: "Level AAA", color: "text-blue-400", bg: "bg-blue-500/5", border: "border-blue-500/10" },
  ] as const;

  return (
    <div className="grid grid-cols-4 gap-4 rounded-xl border border-slate-800 bg-slate-900/40 p-5 shadow-inner">
      {categories.map((c) => (
        <div
          key={c.level}
          className={`flex flex-col items-center justify-center p-3 rounded-lg border ${c.bg} ${c.border} transition-transform hover:scale-[1.02] duration-250`}
        >
          <div className={`text-3xl font-extrabold tracking-tight ${c.color}`}>
            {score[c.level] ?? 0}
          </div>
          <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mt-1.5">
            {c.label}
          </div>
        </div>
      ))}
      <div className="flex flex-col items-center justify-center p-3 rounded-lg border border-red-500/20 bg-red-500/10 transition-transform hover:scale-[1.02] duration-250 shadow-lg shadow-red-500/5">
        <div className="text-3xl font-extrabold tracking-tight text-red-500">
          {score.total ?? 0}
        </div>
        <div className="text-xs font-semibold text-red-400 uppercase tracking-wider mt-1.5">
          Violations
        </div>
      </div>
    </div>
  );
}
