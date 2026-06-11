import { useState } from "react";
import { Copy, Check, ChevronDown, ChevronUp, AlertTriangle, HelpCircle } from "lucide-react";
import type { Violation } from "../types/wcag";

const LEVEL_STYLES = {
  A: "bg-red-500/10 text-red-400 border border-red-500/30 hover:bg-red-500/20",
  AA: "bg-amber-500/10 text-amber-400 border border-amber-500/30 hover:bg-amber-500/20",
  AAA: "bg-blue-500/10 text-blue-400 border border-blue-500/30 hover:bg-blue-500/20",
} as const;

export function ViolationCard({ v }: { v: Violation }) {
  const [showFix, setShowFix] = useState(true);
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(v.fix);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      // ignore
    }
  };

  return (
    <div className="group rounded-xl border border-slate-800 bg-slate-900/50 hover:bg-slate-900/80 transition-all duration-300 p-5 space-y-4 shadow-lg backdrop-blur-sm">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs text-slate-500 font-semibold tracking-wider">
              CRITERION {v.criterion_id}
            </span>
            {v.level === "A" && (
              <span className="flex h-2 w-2 relative">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-red-500"></span>
              </span>
            )}
          </div>
          <h3 className="font-semibold text-base text-slate-100 group-hover:text-white transition-colors">
            {v.title}
          </h3>
        </div>
        <span
          className={`text-xs font-semibold px-2.5 py-1 rounded-md shrink-0 transition-colors uppercase tracking-wider ${
            LEVEL_STYLES[v.level] || LEVEL_STYLES.A
          }`}
        >
          Level {v.level}
        </span>
      </div>

      {/* Issue details */}
      <div className="flex gap-2.5 bg-slate-950/40 p-3 rounded-lg border border-slate-800/60">
        <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
        <p className="text-sm text-slate-300 leading-relaxed font-medium">{v.issue}</p>
      </div>

      {/* Target element code */}
      {v.element && (
        <div className="space-y-1.5">
          <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider block">
            Offending Code Element
          </span>
          <pre className="text-xs bg-slate-950/80 rounded-lg border border-slate-800/80 px-4 py-3 text-amber-200 overflow-x-auto font-mono scrollbar-thin">
            <code>{v.element}</code>
          </pre>
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center justify-between pt-1">
        <button
          onClick={() => setShowFix((f) => !f)}
          className="flex items-center gap-1.5 text-xs font-medium text-slate-400 hover:text-white transition-colors"
        >
          {showFix ? (
            <>
              <ChevronUp className="w-3.5 h-3.5" /> Hide Fix Proposal
            </>
          ) : (
            <>
              <ChevronDown className="w-3.5 h-3.5" /> Show Fix Proposal
            </>
          )}
        </button>

        {showFix && (
          <button
            onClick={handleCopy}
            className="flex items-center gap-1.5 text-xs font-medium text-slate-400 hover:text-white transition-colors"
          >
            {copied ? (
              <>
                <Check className="w-3.5 h-3.5 text-green-400" /> Copied!
              </>
            ) : (
              <>
                <Copy className="w-3.5 h-3.5" /> Copy Code Fix
              </>
            )}
          </button>
        )}
      </div>

      {/* Fix block */}
      {showFix && (
        <div className="space-y-3 pt-2 border-t border-slate-800/60 animate-in fade-in slide-in-from-top-1 duration-200">
          <div className="space-y-1.5">
            <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider block">
              Suggested Fix
            </span>
            <pre className="text-xs bg-slate-950/80 rounded-lg border border-slate-800/80 px-4 py-3 text-green-400 overflow-x-auto font-mono scrollbar-thin">
              <code>{v.fix}</code>
            </pre>
          </div>
          <div className="flex gap-2 text-xs text-slate-400 bg-slate-900/30 p-3 rounded-lg border border-slate-850">
            <HelpCircle className="w-4 h-4 text-blue-400 shrink-0 mt-0.5" />
            <p className="leading-relaxed italic">{v.explanation}</p>
          </div>
        </div>
      )}
    </div>
  );
}
