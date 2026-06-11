import { useState } from "react";
import { useChat } from "./hooks/useChat";
import { useAuth } from "./hooks/useAuth";
import { useQA } from "./hooks/useQA";
import { Editor } from "./components/Editor";
import { UrlScanner } from "./components/UrlScanner";
import { AdvisorPane } from "./components/AdvisorPane";
import { CriteriaExplorer } from "./components/CriteriaExplorer";
import { AdvisorQA } from "./components/AdvisorQA";
import { HistorySidebar } from "./components/HistorySidebar";
import { ShieldAlert, BookOpen, Code2, Play, Activity, MessageSquare, Loader2, Mail, Lock, AlertTriangle, LogOut } from "lucide-react";

export default function App() {
  const { user, logout, loading: authLoading, login, register, error: authError, clearError } = useAuth();
  const [activeTab, setActiveTab] = useState<"workspace" | "chat" | "explorer">("workspace");
  const [inputTab, setInputTab] = useState<"code" | "url">("code");
  const [code, setCode] = useState("<!-- Paste HTML or JSX here -->\n<button style=\"color: #aaa; background: #bbb;\">\n  Click me\n</button>\n<img src=\"logo.png\" />");
  const [sidebarOpen, setSidebarOpen] = useState(true);

  // Authentication Gate States
  const [isLoginTab, setIsLoginTab] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const { tokens, result, setResult, node, loading, error, analyze } = useChat();
  const qa = useQA();

  const handleRunAnalysis = () => {
    if (loading) return;
    if (inputTab === "code") {
      analyze(code);
    }
  };

  const handleScanUrl = (url: string) => {
    if (loading) return;
    analyze(url);
  };

  const handleSelectAudit = (audit: any) => {
    setInputTab(audit.input_type === "url" ? "url" : "code");
    if (audit.input_type === "code") {
      setCode(audit.input_content);
    }
    setResult({
      violations: audit.violations,
      summary: audit.summary,
      score: audit.score,
    });
    setActiveTab("workspace");
  };

  const handleSelectChat = (chatId: string, messages: any[]) => {
    qa.loadConversation(chatId, messages);
    setActiveTab("chat");
  };

  const handleAuthSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    clearError();

    if (!email.trim() || !password.trim()) {
      setFormError("Please fill in all fields.");
      return;
    }

    if (password.length < 6) {
      setFormError("Password must be at least 6 characters long.");
      return;
    }

    setSubmitting(true);
    try {
      if (isLoginTab) {
        await login(email, password);
      } else {
        await register(email, password);
      }
    } catch (err) {
      // Handled by useAuth error state
    } finally {
      setSubmitting(false);
    }
  };

  // Loading Screen
  if (authLoading) {
    return (
      <div className="h-screen w-screen bg-slate-950 flex flex-col items-center justify-center gap-4 text-slate-400 font-sans">
        <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
        <span className="text-[10px] font-bold uppercase tracking-widest font-mono text-slate-500">Checking Active Session...</span>
      </div>
    );
  }

  // Login / Register Gate Page
  if (!user) {
    const activeError = formError || authError;
    return (
      <div className="h-screen w-screen bg-slate-950 flex items-center justify-center relative overflow-hidden font-sans">
        {/* Decorative Blur Backgrounds */}
        <div className="absolute -top-40 -right-40 w-96 h-96 bg-blue-500/10 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute -bottom-40 -left-40 w-96 h-96 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none" />

        <div className="relative w-full max-w-md bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl p-8 mx-4 z-10">
          <div className="flex flex-col items-center mb-6 select-none text-center">
            <div className="flex items-center gap-2 mb-2">
              <div className="w-3.5 h-3.5 rounded-full bg-blue-500 shadow-md shadow-blue-500/50 animate-pulse" />
              <h1 className="font-bold tracking-wider text-slate-200 text-lg uppercase">
                WCAG AI Copilot
              </h1>
            </div>
            <p className="text-xs text-slate-400 font-medium">
              Enterprise Accessibility Evaluator & RAG Advisor
            </p>
          </div>

          {/* Login/Signup Tab Selector */}
          <div className="flex rounded-lg border border-slate-800 p-0.5 bg-slate-950 mb-6">
            <button
              onClick={() => {
                setIsLoginTab(true);
                setFormError(null);
                clearError();
              }}
              className={`flex-1 py-2 text-xs font-semibold uppercase tracking-wider rounded-md transition-all ${
                isLoginTab
                  ? "bg-slate-900 text-blue-400 border border-slate-850"
                  : "text-slate-500 hover:text-slate-350"
              }`}
            >
              Sign In
            </button>
            <button
              onClick={() => {
                setIsLoginTab(false);
                setFormError(null);
                clearError();
              }}
              className={`flex-1 py-2 text-xs font-semibold uppercase tracking-wider rounded-md transition-all ${
                !isLoginTab
                  ? "bg-slate-900 text-blue-400 border border-slate-850"
                  : "text-slate-500 hover:text-slate-350"
              }`}
            >
              Register
            </button>
          </div>

          {/* Error Alert Box */}
          {activeError && (
            <div
              role="alert"
              className="flex items-start gap-3 p-3 bg-red-950/45 border border-red-900/50 rounded-xl text-red-200 text-xs mb-4"
            >
              <AlertTriangle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold">Authentication Error</p>
                <p className="opacity-90 mt-0.5">{activeError}</p>
              </div>
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleAuthSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="gate-email" className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
                Email Address
              </label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                <input
                  id="gate-email"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@example.com"
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-10 pr-4 py-2.5 text-sm text-slate-200 placeholder-slate-650 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/30 transition-all"
                />
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="gate-password" className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
                Password
              </label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                <input
                  id="gate-password"
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-10 pr-4 py-2.5 text-sm text-slate-200 placeholder-slate-650 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/30 transition-all"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="w-full mt-2 flex items-center justify-center gap-2 py-3 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-semibold text-sm transition-all shadow-lg shadow-blue-600/10 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {submitting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Authenticating...
                </>
              ) : isLoginTab ? (
                "Log In"
              ) : (
                "Create Account"
              )}
            </button>
          </form>

          <p className="text-[10px] text-slate-500 text-center mt-6 leading-relaxed">
            By signing in, you access the PostgreSQL session vault, enabling real-time streaming audits and historical RAG Q&A lookup.
          </p>
        </div>
      </div>
    );
  }

  // Dashboard Interface (Only accessible if logged in)
  return (
    <div className="h-screen w-screen flex flex-col bg-slate-950 text-slate-100 font-sans overflow-hidden">
      {/* Header Bar */}
      <header className="h-[56px] border-b border-slate-900 px-6 flex items-center justify-between bg-slate-950/80 backdrop-blur-md shrink-0">
        <div className="flex items-center gap-3 select-none">
          <div className="w-2.5 h-2.5 rounded-full bg-blue-500 shadow-md shadow-blue-500/50 animate-pulse" />
          <h1 className="font-bold tracking-tight text-slate-200 text-sm flex items-center gap-1.5 uppercase">
            WCAG AI Copilot <span className="text-[10px] text-slate-500 font-mono tracking-normal capitalize bg-slate-900 border border-slate-800 px-1.5 py-0.5 rounded">v2.2</span>
          </h1>
        </div>

        {/* Workspace Mode Selection */}
        <nav className="flex rounded-lg border border-slate-900 p-0.5 bg-slate-950">
          <button
            onClick={() => setActiveTab("workspace")}
            className={`flex items-center gap-1.5 px-4 py-1.5 rounded-md text-xs font-semibold uppercase tracking-wider transition-all duration-200 ${
              activeTab === "workspace"
                ? "bg-slate-900 text-blue-400 border border-slate-800"
                : "text-slate-500 hover:text-slate-350"
            }`}
          >
            <ShieldAlert className="w-3.5 h-3.5" /> Advisor Workspace
          </button>
          <button
            onClick={() => setActiveTab("chat")}
            className={`flex items-center gap-1.5 px-4 py-1.5 rounded-md text-xs font-semibold uppercase tracking-wider transition-all duration-200 ${
              activeTab === "chat"
                ? "bg-slate-900 text-blue-400 border border-slate-800"
                : "text-slate-500 hover:text-slate-350"
            }`}
          >
            <MessageSquare className="w-3.5 h-3.5" /> Q&A Chat
          </button>
          <button
            onClick={() => setActiveTab("explorer")}
            className={`flex items-center gap-1.5 px-4 py-1.5 rounded-md text-xs font-semibold uppercase tracking-wider transition-all duration-200 ${
              activeTab === "explorer"
                ? "bg-slate-900 text-blue-400 border border-slate-800"
                : "text-slate-500 hover:text-slate-350"
            }`}
          >
            <BookOpen className="w-3.5 h-3.5" /> Criteria Database
          </button>
        </nav>
        
        {/* Auth status & indicator */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-3">
            <span className="text-xs text-slate-400 bg-slate-900 border border-slate-800 px-2.5 py-1 rounded-lg font-mono">
              {user.email}
            </span>
            <button
              onClick={logout}
              title="Sign Out"
              aria-label="Sign Out"
              className="p-1.5 rounded-lg border border-slate-800 bg-slate-950 text-slate-400 hover:text-red-400 transition-colors hover:bg-slate-900 flex items-center gap-1"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
          
          <div className="flex items-center gap-2 text-slate-500 font-mono text-[10px] border-l border-slate-900 pl-4 h-5">
            <Activity className={`w-3 h-3 ${loading ? "text-blue-400 animate-spin" : "text-green-500"}`} />
            <span>SERVER ONLINE</span>
          </div>
        </div>
      </header>

      {/* Main Workspace Area with HistorySidebar */}
      <main className="flex-1 flex overflow-hidden">
        <HistorySidebar
          isOpen={sidebarOpen}
          setIsOpen={setSidebarOpen}
          onSelectAudit={handleSelectAudit}
          onSelectChat={handleSelectChat}
        />
        
        <div className="flex-1 h-full overflow-hidden">
          {activeTab === "workspace" ? (
            <div className="flex h-full p-6 gap-6 overflow-hidden">
              {/* Left Column (40% Width): Inputs */}
              <div className="w-[42%] flex flex-col gap-4 overflow-hidden h-full">
                {/* Input Tab Selector */}
                <div className="flex rounded-xl border border-slate-900 p-1 bg-slate-900/10 shrink-0">
                  <button
                    onClick={() => setInputTab("code")}
                    className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-xs font-semibold uppercase tracking-wider transition-all duration-255 ${
                      inputTab === "code"
                        ? "bg-slate-900 border border-slate-800 text-slate-200 shadow-md"
                        : "text-slate-500 hover:text-slate-350"
                    }`}
                  >
                    <Code2 className="w-4 h-4" /> Code Snippet
                  </button>
                  <button
                    onClick={() => setInputTab("url")}
                    className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-xs font-semibold uppercase tracking-wider transition-all duration-255 ${
                      inputTab === "url"
                        ? "bg-slate-900 border border-slate-800 text-slate-200 shadow-md"
                        : "text-slate-500 hover:text-slate-350"
                    }`}
                  >
                    <BookOpen className="w-4 h-4" /> URL Scanner
                  </button>
                </div>

                {/* Input Body */}
                <div className="flex-1 flex flex-col overflow-hidden">
                  {inputTab === "code" ? (
                    <div className="flex-1 flex flex-col gap-4 overflow-hidden">
                      <Editor
                        value={code}
                        onChange={setCode}
                        placeholder="<!-- Paste HTML, CSS, or JSX code here to audit accessibility -->"
                      />
                      <button
                        onClick={handleRunAnalysis}
                        disabled={loading || !code.trim()}
                        className="w-full flex items-center justify-center gap-2 py-3.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-semibold text-sm transition-all duration-300 disabled:opacity-40 disabled:cursor-not-allowed select-none shadow-lg shadow-blue-600/20 active:scale-[0.98] shrink-0"
                      >
                        {loading ? (
                          <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                        ) : (
                          <>
                            <Play className="w-4 h-4 fill-current" /> Run Accessibility Audit
                          </>
                        )}
                      </button>
                    </div>
                  ) : (
                    <UrlScanner onScan={handleScanUrl} loading={loading} />
                  )}
                </div>
              </div>

              {/* Right Column (58% Width): Output */}
              <div className="flex-1 h-full overflow-hidden flex flex-col">
                <AdvisorPane
                  tokens={tokens}
                  result={result}
                  node={node}
                  loading={loading}
                  error={error}
                />
              </div>
            </div>
          ) : activeTab === "chat" ? (
            <div className="h-full p-6 overflow-hidden">
              <AdvisorQA qa={qa} />
            </div>
          ) : (
            <div className="h-full p-6 overflow-hidden">
              <CriteriaExplorer />
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
