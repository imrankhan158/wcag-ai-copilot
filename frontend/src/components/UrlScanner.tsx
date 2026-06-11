import { useState } from "react";
import { Globe, ArrowRight } from "lucide-react";

interface UrlScannerProps {
  onScan: (url: string) => void;
  loading: boolean;
}

export function UrlScanner({ onScan, loading }: UrlScannerProps) {
  const [url, setUrl] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim() || loading) return;
    
    let targetUrl = url.trim();
    if (!/^https?:\/\//i.test(targetUrl)) {
      targetUrl = "https://" + targetUrl;
    }
    
    onScan(targetUrl);
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="bg-slate-900/30 border border-slate-800/80 rounded-xl p-5 space-y-3 shadow-xl shadow-slate-950/20 backdrop-blur-sm"
    >
      <div className="flex items-center gap-2 border-b border-slate-800/60 pb-3">
        <Globe className="w-4 h-4 text-blue-400" />
        <h3 className="font-semibold text-sm text-slate-200">Public URL Scanner</h3>
      </div>

      <p className="text-xs text-slate-400 leading-relaxed">
        Paste a public URL (e.g. <code>example.com</code>). Playwright will render the page and analyze its accessibility.
      </p>

      <div className="flex gap-2">
        <div className="relative flex-1">
          <Globe className="absolute left-3 top-2.5 w-4 h-4 text-slate-500" />
          <label htmlFor="url-scanner-input" className="sr-only">
            URL to scan
          </label>
          <input
            id="url-scanner-input"
            type="text"
            placeholder="example.com"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            disabled={loading}
            className="w-full bg-slate-950/80 border border-slate-800 rounded-lg pl-9 pr-4 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-500/80 focus:ring-1 focus:ring-blue-500/30 transition-all font-medium disabled:opacity-50"
          />
        </div>
        <button
          type="submit"
          disabled={loading || !url.trim()}
          className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold transition-colors disabled:opacity-45 disabled:cursor-not-allowed select-none shadow-md shadow-blue-600/10"
        >
          {loading ? (
            <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
          ) : (
            <>
              Scan <ArrowRight className="w-3.5 h-3.5" />
            </>
          )}
        </button>
      </div>
    </form>
  );
}
