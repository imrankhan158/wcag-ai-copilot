import { Terminal, AlertCircle, CheckCircle, RefreshCw } from "lucide-react";
import { ViolationCard } from "./ViolationCard";
import { ScoreCard } from "./ScoreCard";
import type { AnalysisResult } from "../types/wcag";

interface AdvisorPaneProps {
  tokens: string;
  result: AnalysisResult | null;
  node: string | null;
  loading: boolean;
  error: string | null;
}

export function AdvisorPane({ tokens, result, node, loading, error }: AdvisorPaneProps) {
  // Map graph node names to readable labels
  const getNodeLabel = (n: string) => {
    switch (n) {
      case "analyze":
        return "Context analysis & criteria retrieval...";
      case "evaluate":
        return "Evaluating elements against standards...";
      case "suggest":
        return "Compiling report and code fixes...";
      default:
        return "Processing request...";
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-slate-950/20 rounded-xl border border-slate-800/80 p-5 space-y-4 shadow-xl overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-800/60 pb-3 shrink-0">
        <div className="flex items-center gap-2">
          <Terminal className="w-5 h-5 text-blue-400" />
          <h2 className="font-bold text-lg text-slate-100 font-sans">Advisor Output</h2>
        </div>
        {loading && (
          <span className="flex items-center gap-1.5 text-xs font-semibold text-blue-400 bg-blue-500/10 px-2.5 py-1 rounded-md border border-blue-500/20">
            <RefreshCw className="w-3.5 h-3.5 animate-spin" /> Live Agent Stream
          </span>
        )}
      </div>

      {/* Pane Content */}
      <div className="flex-1 overflow-y-auto space-y-5 pr-1 scrollbar-thin">
        {/* Error State */}
        {error && (
          <div className="flex gap-3 rounded-lg bg-red-950/20 border border-red-900/30 p-4 text-sm text-red-400">
            <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" />
            <div>
              <span className="font-bold">Analysis Failed:</span>
              <p className="mt-1 text-slate-350">{error}</p>
            </div>
          </div>
        )}

        {/* Loading Progress State */}
        {loading && (
          <div className="space-y-3 p-4 rounded-xl border border-slate-800 bg-slate-900/20">
            <div className="flex items-center gap-3 text-slate-350 text-sm font-semibold">
              <div className="w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
              {node ? getNodeLabel(node) : "Waking up WCAG advisor graph..."}
            </div>
            
            {/* Fake progress bar */}
            <div className="h-1.5 w-full bg-slate-950 rounded-full overflow-hidden">
              <div
                className={`h-full bg-blue-500 rounded-full transition-all duration-500 ${
                  node === "analyze"
                    ? "w-1/3"
                    : node === "evaluate"
                    ? "w-2/3"
                    : node === "suggest"
                    ? "w-[90%]"
                    : "w-[15%]"
                }`}
              />
            </div>
          </div>
        )}

        {/* Streaming thought tokens */}
        {loading && tokens && (
          <div className="space-y-2">
            <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider block">
              Agent Stream Feed (Reasoning)
            </span>
            <div
              role="log"
              aria-live="polite"
              className="bg-slate-950/80 rounded-lg border border-slate-850 p-4 font-mono text-xs text-slate-400 max-h-[150px] overflow-y-auto scrollbar-thin whitespace-pre-wrap leading-relaxed shadow-inner"
            >
              {tokens}
            </div>
          </div>
        )}

        {/* Analysis Results Display */}
        {result && (
          <div className="space-y-5 animate-in fade-in duration-300">
            {/* Score Summary */}
            <ScoreCard score={result.score} />

            {/* Assessment Paragraph */}
            {result.summary && (
              <div className="space-y-2">
                <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider block">
                  Overall Assessment
                </span>
                <p className="text-sm text-slate-300 leading-relaxed border-l-2 border-blue-500 pl-4 py-0.5 bg-slate-900/10 rounded-r-lg pr-2">
                  {result.summary}
                </p>
              </div>
            )}

            {/* Violations List */}
            {result.violations.length === 0 ? (
              <div className="flex items-center gap-3 rounded-lg bg-green-950/10 border border-green-900/20 p-4 text-sm text-green-400">
                <CheckCircle className="w-5 h-5 shrink-0" />
                <span className="font-semibold">✓ No accessibility violations detected in the context.</span>
              </div>
            ) : (
              <div className="space-y-3">
                <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider block">
                  Detailed Findings ({result.violations.length} violations)
                </span>
                <div className="space-y-3.5">
                  {result.violations.map((v, i) => (
                    <ViolationCard key={i} v={v} />
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Empty State */}
        {!result && !loading && !error && (
          <div className="flex flex-col items-center justify-center h-full min-h-[300px] text-center gap-4 py-16 text-slate-500">
            <div className="text-5xl opacity-40 bg-slate-900 p-4 rounded-2xl border border-slate-800/50 shadow-inner">♿</div>
            <div className="space-y-1">
              <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">No Analysis Loaded</h3>
              <p className="text-xs text-slate-500 max-w-xs leading-relaxed">
                Provide code input or a website URL on the left panel, then trigger the analyzer.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
