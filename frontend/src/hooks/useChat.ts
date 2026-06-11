import { useState, useCallback } from "react";
import type { AnalysisResult, StreamEvent } from "../types/wcag";

export function useChat() {
  const [tokens, setTokens] = useState("");
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [node, setNode] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const analyze = useCallback(async (input: string) => {
    setLoading(true);
    setTokens("");
    setResult(null);
    setNode(null);
    setError(null);

    try {
      const token = localStorage.getItem("token");
      const res = await fetch("http://localhost:8000/api/chat", {
        method: "POST",
        headers: { 
          "Content-Type": "application/json",
          ...(token ? { "Authorization": `Bearer ${token}` } : {})
        },
        body: JSON.stringify({ input }),
      });

      if (!res.ok) {
        throw new Error(`SSE request failed with status: ${res.status}`);
      }

      const reader = res.body?.getReader();
      if (!reader) {
        throw new Error("No response body available for streaming");
      }

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed || !trimmed.startsWith("data: ")) continue;

          const raw = trimmed.substring(6).trim();
          if (raw === "[DONE]") {
            setLoading(false);
            break;
          }

          try {
            const event: StreamEvent = JSON.parse(raw);
            if (event.type === "token") setTokens((t) => t + (event.content || ""));
            if (event.type === "node_done") setNode(event.node ?? null);
            if (event.type === "result") setResult(event.data ?? null);
          } catch (e) {
            // Json parse error on malformed/partial tokens
          }
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error in stream");
    } finally {
      setLoading(false);
    }
  }, []);

  return { tokens, result, setResult, node, loading, error, analyze };
}
