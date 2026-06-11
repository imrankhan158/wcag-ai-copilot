import { useState, useEffect } from "react";
import { Search, ExternalLink, BookOpen } from "lucide-react";
import type { WCAGCriterion } from "../types/wcag";

export function CriteriaExplorer() {
  const [criteria, setCriteria] = useState<WCAGCriterion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Filters
  const [search, setSearch] = useState("");
  const [levelFilter, setLevelFilter] = useState<string>("");
  const [principleFilter, setPrincipleFilter] = useState<string>("");
  
  // Expanded item
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    async function fetchCriteria() {
      try {
        setLoading(true);
        setError(null);
        
        let url = "http://localhost:8000/api/criteria";
        const params = new URLSearchParams();
        if (levelFilter) params.append("level", levelFilter);
        if (principleFilter) params.append("principle", principleFilter);
        
        if (params.toString()) {
          url += `?${params.toString()}`;
        }
        
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        setCriteria(data.criteria || []);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load criteria");
      } finally {
        setLoading(false);
      }
    }
    fetchCriteria();
  }, [levelFilter, principleFilter]);

  const filteredCriteria = criteria.filter(c => {
    if (!search.trim()) return true;
    const s = search.toLowerCase();
    return (
      c.criterion_id.toLowerCase().includes(s) ||
      c.title.toLowerCase().includes(s) ||
      c.text.toLowerCase().includes(s)
    );
  });

  return (
    <div className="flex flex-col h-full bg-slate-900/30 rounded-xl border border-slate-800/80 p-5 space-y-4 shadow-xl">
      <div className="flex items-center justify-between border-b border-slate-800/60 pb-3">
        <div className="flex items-center gap-2">
          <BookOpen className="w-5 h-5 text-blue-400" />
          <h2 className="font-bold text-lg text-slate-100">WCAG 2.2 Explorer</h2>
        </div>
        <span className="text-xs font-semibold text-slate-400 bg-slate-800/60 px-2 py-0.5 rounded border border-slate-700/50">
          86 Criteria
        </span>
      </div>

      {/* Filters Toolbar */}
      <div className="space-y-3">
        {/* Search */}
        <div className="relative">
          <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-500" />
          <label htmlFor="criteria-search-input" className="sr-only">
            Search criteria by ID, name, or content
          </label>
          <input
            id="criteria-search-input"
            type="text"
            placeholder="Search by ID, name, or content..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-slate-950/80 border border-slate-800 rounded-lg pl-9 pr-4 py-2 text-sm text-slate-200 placeholder-slate-650 focus:outline-none focus:border-blue-500/80 focus:ring-1 focus:ring-blue-500/30 transition-all font-medium"
          />
        </div>

        {/* Category Filter Pills */}
        <div className="flex flex-wrap gap-2 text-xs">
          {/* Level Pills */}
          <div role="group" aria-label="Filter by WCAG level" className="flex rounded-lg border border-slate-800 p-0.5 bg-slate-950/40">
            {["", "A", "AA", "AAA"].map((level) => (
              <button
                key={level}
                onClick={() => setLevelFilter(level)}
                className={`px-3 py-1 rounded-md font-semibold transition-all ${
                  levelFilter === level
                    ? "bg-blue-600/90 text-white shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                {level === "" ? "All Levels" : `Lvl ${level}`}
              </button>
            ))}
          </div>

          {/* Principle Pills */}
          <div role="group" aria-label="Filter by WCAG principle" className="flex flex-wrap rounded-lg border border-slate-800 p-0.5 bg-slate-950/40">
            {["", "Perceivable", "Operable", "Understandable", "Robust"].map((p) => (
              <button
                key={p}
                onClick={() => setPrincipleFilter(p)}
                className={`px-2.5 py-1 rounded-md font-semibold transition-all ${
                  principleFilter === p
                    ? "bg-indigo-600/90 text-white shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                {p === "" ? "All Principles" : p}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Grid list container */}
      <div className="flex-1 overflow-y-auto min-h-[300px] scrollbar-thin space-y-2.5 pr-1">
        {loading && (
          <div className="flex flex-col items-center justify-center py-12 gap-3 text-slate-500 text-sm">
            <div className="w-5 h-5 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
            Loading criterion database...
          </div>
        )}

        {error && (
          <div className="text-center py-8 text-sm text-red-400 bg-red-950/20 border border-red-900/30 rounded-lg p-4">
            Error loading WCAG data: {error}
          </div>
        )}

        {!loading && !error && filteredCriteria.length === 0 && (
          <div className="text-center py-12 text-sm text-slate-500 italic">
            No matching criteria found for filters.
          </div>
        )}

        {!loading && !error && filteredCriteria.map((c) => {
          const isExpanded = expandedId === c.criterion_id;
          return (
            <div
              key={c.criterion_id}
              className={`rounded-lg border transition-all duration-200 ${
                isExpanded
                  ? "border-blue-500/40 bg-slate-900/60 shadow-md shadow-blue-500/5"
                  : "border-slate-800 bg-slate-950/20 hover:border-slate-700/80 hover:bg-slate-950/40"
              }`}
            >
              <button
                onClick={() => setExpandedId(isExpanded ? null : c.criterion_id)}
                className="w-full flex items-center justify-between text-left p-4.5"
              >
                <div className="space-y-0.5">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs text-slate-400 font-bold bg-slate-900 px-2 py-0.5 rounded border border-slate-850">
                      {c.criterion_id}
                    </span>
                    <span className="text-[10px] uppercase tracking-wider font-extrabold text-blue-400">
                      {c.principle}
                    </span>
                  </div>
                  <h4 className="font-semibold text-slate-100 text-sm">{c.title}</h4>
                </div>
                <span className={`text-[10px] font-bold px-2 py-0.5 rounded border uppercase shrink-0 ${
                  c.level === "A"
                    ? "border-red-500/30 text-red-400 bg-red-500/5"
                    : c.level === "AA"
                    ? "border-amber-500/30 text-amber-400 bg-amber-500/5"
                    : "border-blue-500/30 text-blue-400 bg-blue-500/5"
                }`}>
                  Level {c.level}
                </span>
              </button>

              {isExpanded && (
                <div className="px-4.5 pb-4.5 pt-1 border-t border-slate-800/40 space-y-3 text-sm text-slate-300 animate-in fade-in duration-200">
                  <p className="leading-relaxed bg-slate-950/60 p-3 rounded-lg border border-slate-850 text-slate-300">
                    {c.text}
                  </p>
                  <div className="flex items-center justify-between pt-1">
                    <span className="text-xs text-slate-500 font-medium">
                      Guideline {c.guideline}
                    </span>
                    {c.url && (
                      <a
                        href={c.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-1.5 text-xs text-blue-400 hover:text-blue-300 font-medium transition-colors"
                      >
                        W3C Documentation <ExternalLink className="w-3 h-3" />
                      </a>
                    )}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
