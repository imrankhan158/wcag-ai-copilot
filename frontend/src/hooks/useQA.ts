import { useState, useCallback } from "react";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export function useQA() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sendMessage = useCallback(async (messageText: string) => {
    if (!messageText.trim() || loading) return;

    setLoading(true);
    setError(null);

    // Save history to send to API
    const historyToSend = [...messages];

    // Append user message and placeholder assistant message
    const newUserMessage: ChatMessage = { role: "user", content: messageText };
    const newAssistantPlaceholder: ChatMessage = { role: "assistant", content: "" };
    setMessages((prev) => [...prev, newUserMessage, newAssistantPlaceholder]);

    const token = localStorage.getItem("token");

    try {
      const res = await fetch("http://localhost:8000/api/chat/qa", {
        method: "POST",
        headers: { 
          "Content-Type": "application/json",
          ...(token ? { "Authorization": `Bearer ${token}` } : {})
        },
        body: JSON.stringify({
          message: messageText,
          history: historyToSend,
          conversation_id: conversationId || undefined,
        }),
      });

      if (!res.ok) {
        throw new Error(`QA stream failed with status: ${res.status}`);
      }

      const reader = res.body?.getReader();
      if (!reader) {
        throw new Error("No response reader available");
      }

      const decoder = new TextDecoder();
      let buffer = "";
      let accumulatedResponse = "";

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
            const event = JSON.parse(raw);
            if (event.type === "conversation_id" && event.id) {
              setConversationId(event.id);
            } else if (event.type === "token" && event.content) {
              accumulatedResponse += event.content;
              setMessages((prev) => {
                const updated = [...prev];
                // Update the last message (which is the assistant placeholder)
                if (updated.length > 0) {
                  updated[updated.length - 1] = {
                    role: "assistant",
                    content: accumulatedResponse,
                  };
                }
                return updated;
              });
            }
          } catch (e) {
            // Json parse error on partial chunks
          }
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error occurred");
      setMessages((prev) => {
        const updated = [...prev];
        if (updated.length > 0 && updated[updated.length - 1].content === "") {
          updated[updated.length - 1] = {
            role: "assistant",
            content: "⚠️ Sorry, I encountered an error while retrieving the answer. Please check the network connection.",
          };
        }
        return updated;
      });
    } finally {
      setLoading(false);
    }
  }, [messages, loading, conversationId]);

  const loadConversation = useCallback((id: string, msgs: ChatMessage[]) => {
    setConversationId(id);
    setMessages(msgs);
    setError(null);
  }, []);

  const clearChat = useCallback(() => {
    setMessages([]);
    setConversationId(null);
    setError(null);
  }, []);

  return { 
    messages, 
    conversationId, 
    loading, 
    error, 
    sendMessage, 
    loadConversation, 
    clearChat 
  };
}
