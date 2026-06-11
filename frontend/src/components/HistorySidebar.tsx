import { useState, useEffect, useCallback } from "react";
import { useAuth } from "../hooks/useAuth";
import { History, MessageSquare, ClipboardCheck, ChevronRight, ChevronLeft, Loader2, Clock } from "lucide-react";

interface HistorySidebarProps {
  onSelectAudit: (auditDetail: any) => void;
  onSelectChat: (chatId: string, messages: any[]) => void;
  isOpen: boolean;
  setIsOpen: (isOpen: boolean) => void;
}

export function HistorySidebar({ onSelectAudit, onSelectChat, isOpen, setIsOpen }: HistorySidebarProps) {
  const { user, token } = useAuth();
  const [activeTab, setActiveTab] = useState<"audits" | "chats">("audits");
  const [audits, setAudits] = useState<any[]>([]);
  const [chats, setChats] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [itemLoadingId, setItemLoadingId] = useState<string | null>(null);

  const fetchHistory = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      // Fetch Audits
      const auditsRes = await fetch("http://localhost:8000/api/history/audits", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (auditsRes.ok) {
        const auditsData = await auditsRes.json();
        setAudits(auditsData);
      }

      // Fetch Chats
      const chatsRes = await fetch("http://localhost:8000/api/history/chats", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (chatsRes.ok) {
        const chatsData = await chatsRes.json();
        setChats(chatsData);
      }
    } catch (err) {
      console.error("Failed to load history lists:", err);
    } finally {
      setLoading(false);
    }
  }, [token]);

  // Fetch lists on open or user state change
  useEffect(() => {
    if (isOpen && token) {
      fetchHistory();
    }
  }, [isOpen, token, fetchHistory]);

  const handleAuditClick = async (auditId: string) => {
    if (!token) return;
    setItemLoadingId(auditId);
    try {
      const res = await fetch(`http://localhost:8000/api/history/audits/${auditId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const detail = await res.json();
        onSelectAudit(detail);
      }
    } catch (err) {
      console.error("Failed to load audit details:", err);
    } finally {
      setItemLoadingId(null);
    }
  };

  const handleChatClick = async (chatId: string) => {
    if (!token) return;
    setItemLoadingId(chatId);
    try {
      const res = await fetch(`http://localhost:8000/api/history/chats/${chatId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const detail = await res.json();
        onSelectChat(detail.id, detail.messages);
      }
    } catch (err) {
      console.error("Failed to load chat details:", err);
    } finally {
      setItemLoadingId(null);
    }
  };

  const formatDate = (dateStr: string) => {
    try {
      const date = new Date(dateStr);
      return date.toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch (e) {
      return dateStr;
    }
  };

  return (
    <div
      className={`relative h-full border-r border-slate-900 bg-slate-950/95 flex flex-col transition-all duration-300 z-30 shrink-0 ${
        isOpen ? "w-[280px]" : "w-0 border-r-0"
      }`}
    >
      {/* Toggle button outside or absolute */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        aria-label={isOpen ? "Collapse history sidebar" : "Expand history sidebar"}
        className="absolute top-1/2 -translate-y-1/2 -right-3.5 w-7 h-7 rounded-full bg-slate-900 border border-slate-800 flex items-center justify-center text-slate-400 hover:text-slate-200 shadow-md cursor-pointer hover:bg-slate-800 transition-colors z-40"
      >
        {isOpen ? <ChevronLeft className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
      </button>

      {isOpen && (
        <div className="flex flex-col h-full overflow-hidden w-[280px]">
          {/* Header */}
          <div className="p-4 border-b border-slate-900 flex items-center gap-2 select-none">
            <History className="w-4 h-4 text-blue-400" />
            <h2 className="text-xs font-bold text-slate-350 uppercase tracking-widest">
              My History
            </h2>
            {user && (
              <button
                onClick={fetchHistory}
                disabled={loading}
                aria-label="Refresh history"
                className="ml-auto text-[10px] font-semibold text-blue-400 hover:text-blue-300 disabled:opacity-50"
              >
                Refresh
              </button>
            )}
          </div>

          {/* User state check */}
          {!user ? (
            <div className="flex-1 flex flex-col items-center justify-center p-6 text-center text-slate-500 gap-2">
              <History className="w-8 h-8 opacity-20" />
              <p className="text-xs font-semibold text-slate-400">Save Your Progress</p>
              <p className="text-[11px] opacity-75 leading-relaxed">
                Log in to automatically save your code audits and conversational QA chat histories.
              </p>
            </div>
          ) : (
            <>
              {/* Tab Selector */}
              <div className="flex border-b border-slate-900 p-2 gap-2 bg-slate-900/10 shrink-0">
                <button
                  onClick={() => setActiveTab("audits")}
                  className={`flex-1 py-1.5 flex items-center justify-center gap-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wider transition-all ${
                    activeTab === "audits"
                      ? "bg-slate-900 text-slate-200 border border-slate-800"
                      : "text-slate-500 hover:text-slate-300"
                  }`}
                >
                  <ClipboardCheck className="w-3.5 h-3.5" /> Audits
                </button>
                <button
                  onClick={() => setActiveTab("chats")}
                  className={`flex-1 py-1.5 flex items-center justify-center gap-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wider transition-all ${
                    activeTab === "chats"
                      ? "bg-slate-900 text-slate-200 border border-slate-800"
                      : "text-slate-500 hover:text-slate-300"
                  }`}
                >
                  <MessageSquare className="w-3.5 h-3.5" /> Chats
                </button>
              </div>

              {/* Lists content */}
              <div className="flex-1 overflow-y-auto p-2 flex flex-col gap-1.5 custom-scrollbar">
                {loading && (
                  <div className="flex items-center justify-center py-8 text-slate-500 gap-2">
                    <Loader2 className="w-4 h-4 animate-spin text-blue-500" />
                    <span className="text-xs">Loading history...</span>
                  </div>
                )}

                {!loading && activeTab === "audits" && (
                  <>
                    {audits.length === 0 ? (
                      <div className="text-center py-8 text-slate-600 text-xs">
                        No audits saved yet.
                      </div>
                    ) : (
                      audits.map((item) => {
                        const isLoading = itemLoadingId === item.id;
                        const isUrl = item.input_type === "url";
                        return (
                          <button
                            key={item.id}
                            disabled={!!itemLoadingId}
                            onClick={() => handleAuditClick(item.id)}
                            className="w-full text-left p-3 rounded-xl border border-slate-900 hover:border-slate-800 bg-slate-950 hover:bg-slate-900/60 transition-all flex flex-col gap-1.5 group disabled:opacity-60"
                          >
                            <div className="flex items-center justify-between w-full">
                              <span className="text-[10px] font-semibold text-slate-500 flex items-center gap-1">
                                <Clock className="w-3 h-3" />
                                {formatDate(item.created_at)}
                              </span>
                              {isLoading ? (
                                <Loader2 className="w-3 h-3 animate-spin text-blue-500" />
                              ) : (
                                <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${
                                  item.score.total === 0 
                                    ? "bg-green-950/20 text-green-400 border-green-900/50" 
                                    : item.score.total <= 3 
                                      ? "bg-yellow-950/20 text-yellow-400 border-yellow-900/50" 
                                      : "bg-red-950/20 text-red-400 border-red-900/50"
                                }`}>
                                  {item.score.total} {item.score.total === 1 ? "Violation" : "Violations"}
                                </span>
                              )}
                            </div>
                            <div className="text-xs font-semibold text-slate-300 truncate group-hover:text-blue-400 transition-colors">
                              {isUrl ? item.input_content : item.summary || "Code Snippet Audit"}
                            </div>
                            <div className="text-[10px] text-slate-500 truncate font-mono bg-slate-900/40 p-1 rounded border border-slate-900/60">
                              {item.input_content}
                            </div>
                          </button>
                        );
                      })
                    )}
                  </>
                )}

                {!loading && activeTab === "chats" && (
                  <>
                    {chats.length === 0 ? (
                      <div className="text-center py-8 text-slate-600 text-xs">
                        No conversations saved yet.
                      </div>
                    ) : (
                      chats.map((item) => {
                        const isLoading = itemLoadingId === item.id;
                        return (
                          <button
                            key={item.id}
                            disabled={!!itemLoadingId}
                            onClick={() => handleChatClick(item.id)}
                            className="w-full text-left p-3 rounded-xl border border-slate-900 hover:border-slate-800 bg-slate-950 hover:bg-slate-900/60 transition-all flex flex-col gap-1 group disabled:opacity-60"
                          >
                            <div className="flex items-center justify-between w-full">
                              <span className="text-[10px] font-semibold text-slate-500 flex items-center gap-1">
                                <Clock className="w-3 h-3" />
                                {formatDate(item.created_at)}
                              </span>
                              {isLoading && <Loader2 className="w-3 h-3 animate-spin text-blue-500" />}
                            </div>
                            <div className="text-xs font-semibold text-slate-300 truncate group-hover:text-blue-400 transition-colors">
                              {item.title || "Accessibility Discussion"}
                            </div>
                          </button>
                        );
                      })
                    )}
                  </>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
