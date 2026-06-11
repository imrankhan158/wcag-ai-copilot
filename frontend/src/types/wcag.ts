export interface Violation {
  criterion_id: string; // "1.4.3"
  title: string; // "Contrast (Minimum)"
  level: "A" | "AA" | "AAA";
  issue: string;
  element: string;
  fix: string;
  explanation: string;
}

export interface AnalysisResult {
  violations: Violation[];
  summary: string;
  score: {
    A: number;
    AA: number;
    AAA: number;
    total: number;
  };
}

export interface StreamEvent {
  type: "token" | "node_done" | "result";
  content?: string;
  node?: "analyze" | "evaluate" | "suggest";
  data?: AnalysisResult;
}

export interface WCAGCriterion {
  criterion_id: string;
  title: string;
  level: "A" | "AA" | "AAA";
  principle: string;
  guideline: string;
  text: string;
  url: string;
}
