import { useState, useRef, useEffect } from "react";
import { Send, RefreshCw, MessageSquare, Trash2, HelpCircle } from "lucide-react";
import { useQA } from "../hooks/useQA";

interface AdvisorQAProps {
  qa: ReturnType<typeof useQA>;
}

export function AdvisorQA({ qa }: AdvisorQAProps) {
  const { messages, conversationId, loading, error, sendMessage, clearChat } = qa;
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const handleSend = () => {
    if (!input.trim() || loading) return;
    sendMessage(input.trim());
    setInput("");
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="flex flex-col h-full bg-slate-900/30 rounded-xl border border-slate-800/80 shadow-xl overflow-hidden">
      {/* Header */}
      <div className="bg-slate-950/45 px-5 py-3.5 border-b border-slate-800/60 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <MessageSquare className="w-5 h-5 text-blue-400" />
          <h2 className="font-bold text-slate-100 text-sm tracking-wide uppercase">
            WCAG Accessibility Q&A
          </h2>
        </div>
        <div className="flex items-center gap-2">
          {conversationId && (
            <button
              onClick={clearChat}
              disabled={loading}
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-slate-805 bg-slate-950/40 hover:bg-slate-950/80 text-xs font-semibold text-blue-400 hover:text-blue-300 transition-colors disabled:opacity-50"
            >
              New Chat
            </button>
          )}
          {messages.length > 0 && (
            <button
              onClick={clearChat}
              disabled={loading}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-slate-800 hover:border-slate-705 bg-slate-950/40 hover:bg-slate-955 text-xs font-semibold text-slate-400 hover:text-slate-250 transition-colors disabled:opacity-50"
            >
              <Trash2 className="w-3.5 h-3.5" /> Clear conversation
            </button>
          )}
        </div>
      </div>

      {/* Message History */}
      <div className="flex-1 overflow-y-auto p-5 space-y-4 scrollbar-thin">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full min-h-[250px] text-center gap-4 text-slate-500 py-8">
            <div className="text-5xl opacity-40 bg-slate-900 p-4 rounded-2xl border border-slate-800/50 shadow-inner">💬</div>
            <div className="space-y-1">
              <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">Ask the Advisor</h3>
              <p className="text-xs text-slate-500 max-w-xs leading-relaxed">
                Ask any question about WCAG 2.2 guidelines, contrast rules, keyboard operations, or semantic markup.
              </p>
            </div>
            {/* Quick prompts */}
            <div className="grid grid-cols-2 gap-2 max-w-md pt-2">
              {[
                "How do I make an icon button accessible?",
                "What are the contrast requirements for non-text components?",
                "How does WCAG 2.2 define Focus Not Obscured?",
                "Provide an accessible HTML autocomplete form example.",
              ].map((prompt, i) => (
                <button
                  key={i}
                  onClick={() => setInput(prompt)}
                  className="text-left text-xs bg-slate-950/30 hover:bg-slate-950/80 border border-slate-850 hover:border-slate-700 p-3 rounded-lg text-slate-400 hover:text-slate-200 transition-all font-medium leading-relaxed"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((m, idx) => (
            <div
              key={idx}
              className={`flex gap-3 max-w-[85%] ${
                m.role === "user" ? "ml-auto flex-row-reverse" : "mr-auto"
              }`}
            >
              {/* Profile Icon */}
              <div
                className={`w-8 h-8 rounded-full shrink-0 flex items-center justify-center border font-bold text-xs select-none shadow-sm ${
                  m.role === "user"
                    ? "bg-slate-850 border-slate-750 text-slate-300"
                    : "bg-blue-600/15 border-blue-500/30 text-blue-400"
                }`}
              >
                {m.role === "user" ? "U" : "AI"}
              </div>

              {/* Speech Bubble */}
              <div className="space-y-1">
                <div
                  className={`rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-lg ${
                    m.role === "user"
                      ? "bg-slate-800/90 text-white rounded-tr-none border border-slate-700/30"
                      : "bg-slate-900/60 border border-slate-850 text-slate-200 rounded-tl-none"
                  }`}
                >
                  <div className="whitespace-pre-wrap font-sans">{m.content}</div>
                </div>
                {/* Loader for active streaming */}
                {m.role === "assistant" && m.content === "" && loading && (
                  <div className="flex items-center gap-1.5 px-3 py-1 rounded bg-slate-900/25 border border-slate-850 w-fit">
                    <div className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce [animation-delay:-0.3s]" />
                    <div className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce [animation-delay:-0.15s]" />
                    <div className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce" />
                  </div>
                )}
              </div>
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Form */}
      <div className="p-4 border-t border-slate-850/65 bg-slate-950/20 shrink-0 space-y-2">
        {error && (
          <div className="text-xs text-red-400 bg-red-950/15 border border-red-900/20 px-3 py-2 rounded-lg flex items-center gap-2">
            <HelpCircle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={loading}
            placeholder="Ask a question about WCAG guidelines..."
            className="flex-1 min-h-[44px] max-h-[120px] bg-slate-950/80 border border-slate-800 rounded-xl px-4 py-2.5 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-500/80 focus:ring-1 focus:ring-blue-500/20 transition-all font-medium disabled:opacity-50 resize-none font-sans scrollbar-thin"
            rows={1}
            spellCheck={false}
          />
          <button
            onClick={handleSend}
            disabled={loading || !input.trim()}
            className="flex items-center justify-center w-[44px] h-[44px] rounded-xl bg-blue-600 hover:bg-blue-500 text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed select-none shadow-md shadow-blue-600/10 shrink-0"
          >
            {loading ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4 fill-current ml-0.5" />
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
