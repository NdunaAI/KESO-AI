"use client";

import { useRef, useState } from "react";
import { streamChat, type Citation } from "@/lib/api";

interface DisplayMessage {
  role: "user" | "assistant";
  text: string;
  citations: Citation[];
}

export default function ChatPage() {
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const conversationIdRef = useRef<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const question = input.trim();
    if (!question || isStreaming) return;

    setMessages((prev) => [...prev, { role: "user", text: question, citations: [] }]);
    setMessages((prev) => [...prev, { role: "assistant", text: "", citations: [] }]);
    setInput("");
    setIsStreaming(true);

    const updateLastAssistant = (fn: (m: DisplayMessage) => DisplayMessage) => {
      setMessages((prev) => {
        const next = [...prev];
        const lastIndex = next.length - 1;
        next[lastIndex] = fn(next[lastIndex]);
        return next;
      });
    };

    try {
      await streamChat(question, conversationIdRef.current, {}, {
        onMeta: (meta) => {
          conversationIdRef.current = meta.conversation_id;
        },
        onToken: (text) => {
          updateLastAssistant((m) => ({ ...m, text: m.text + text }));
        },
        onCitation: (citation) => {
          updateLastAssistant((m) => ({ ...m, citations: [...m.citations, citation] }));
        },
        onDone: () => setIsStreaming(false),
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
    <main className="mx-auto flex h-screen max-w-3xl flex-col p-4">
      <h1 className="mb-4 text-xl font-semibold">KESO AI</h1>

      <div className="flex-1 space-y-4 overflow-y-auto">
        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "text-right" : "text-left"}>
            <div
              className={
                "inline-block max-w-[80%] rounded-lg px-3 py-2 " +
                (m.role === "user" ? "bg-blue-600 text-white" : "bg-white shadow-sm")
              }
            >
              <p className="whitespace-pre-wrap">{m.text || (isStreaming && i === messages.length - 1 ? "…" : "")}</p>
              {m.citations.length > 0 && (
                <ul className="mt-2 space-y-1 border-t border-slate-200 pt-2 text-xs text-slate-500">
                  {m.citations.map((c) => (
                    <li key={c.id}>
                      [{c.id}] {c.title} ({c.source_system})
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        ))}
      </div>

      <form onSubmit={handleSubmit} className="mt-4 flex gap-2">
        <input
          className="flex-1 rounded border border-slate-300 px-3 py-2"
          placeholder="Ask about a project, milestone, or policy…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={isStreaming}
        />
        <button
          type="submit"
          className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
          disabled={isStreaming || !input.trim()}
        >
          Ask
        </button>
      </form>
    </main>
  );
}
