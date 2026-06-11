import { useState } from "react";
import type { AnalysisResult } from "../types/wcag";

export function useCheck() {
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const analyze = async (input: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("http://localhost:8000/api/check", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ input }),
      });
      if (!res.ok) throw new Error(`API error: ${res.status}`);
      const data = await res.json();
      setResult(data);
      return data;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
      return null;
    } finally {
      setLoading(false);
    }
  };

  return { result, setResult, loading, error, analyze };
}
