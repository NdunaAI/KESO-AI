"use client";

import { useEffect, useRef, useState } from "react";
import {
  streamChat,
  fetchMe,
  fetchConversations,
  fetchConversation,
  type ChatFilters,
  type ConversationSummary,
  type UserProfile,
} from "@/lib/api";
import { Header } from "@/components/Header";
import { Sidebar } from "@/components/Sidebar";
import { FilterBar } from "@/components/FilterBar";
import { ChatMessage, type DisplayMessage } from "@/components/ChatMessage";
import { ChatInput } from "@/components/ChatInput";

export default function ChatPage() {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState("");
  const [filters, setFilters] = useState<ChatFilters>({});
  const [isStreaming, setIsStreaming] = useState(false);
  const threadEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchMe().then(setProfile);
    fetchConversations().then(setConversations);
  }, []);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleSelectConversation(id: string) {
    setConversationId(id);
    const history = await fetchConversation(id);
    setMessages(
      (history ?? []).map((m) => ({
        role: m.role,
        text: m.text,
        citations: m.citations,
        createdAt: new Date(m.created_at),
      }))
    );
  }

  function handleNewConversation() {
    setConversationId(null);
    setMessages([]);
  }

  async function handleSubmit() {
    const question = input.trim();
    if (!question || isStreaming) return;

    setMessages((prev) => [...prev, { role: "user", text: question, citations: [], createdAt: new Date() }]);
    setMessages((prev) => [...prev, { role: "assistant", text: "", citations: [], createdAt: new Date() }]);
    setInput("");
    setIsStreaming(true);

    const updateLastAssistant = (fn: (m: DisplayMessage) => DisplayMessage) => {
      setMessages((prev) => {
        const next = [...prev];
        const lastIndex = next.length - 1;
        next[lastIndex] = fn(next[lastIndex]!);
        return next;
      });
    };

    try {
      await streamChat(question, conversationId, filters, {
        onMeta: (meta) => {
          setConversationId(meta.conversation_id);
        },
        onToken: (text) => {
          updateLastAssistant((m) => ({ ...m, text: m.text + text }));
        },
        onCitation: (citation) => {
          updateLastAssistant((m) => ({ ...m, citations: [...m.citations, citation] }));
        },
        onDone: () => {
          setIsStreaming(false);
          fetchConversations().then(setConversations);
        },
        onError: (err) => {
          updateLastAssistant((m) => ({ ...m, text: m.text || `Error: ${err.message}` }));
          setIsStreaming(false);
        },
      });
    } catch {
      setIsStreaming(false);
    }
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <div className="h-[3px] shrink-0 bg-gradient-to-r from-keso-orange via-keso-indigo to-keso-green" />
      <Header profile={profile} />

      <div className="flex min-h-0 flex-1">
        <Sidebar
          conversations={conversations}
          activeConversationId={conversationId}
          onSelectConversation={handleSelectConversation}
          onNewConversation={handleNewConversation}
        />

        <div className="flex min-w-0 flex-1 flex-col">
          <div className="keso-scroll flex-1 overflow-y-auto px-10 py-8">
            <div className="flex flex-col gap-6">
              {messages.map((m, i) => (
                <ChatMessage key={i} message={m} isStreaming={isStreaming && i === messages.length - 1} />
              ))}
              <div ref={threadEndRef} />
            </div>
          </div>

          <FilterBar
            filters={filters}
            onChange={setFilters}
            availableProjects={(profile?.scope.projects ?? []).filter((p) => p !== "*")}
            availableSettlements={(profile?.scope.settlements ?? []).filter((s) => s !== "*")}
          />

          <ChatInput value={input} onChange={setInput} onSubmit={handleSubmit} disabled={isStreaming} />
        </div>
      </div>
    </div>
  );
}
