"use client";

import { useMemo, useState } from "react";
import type { ConversationSummary } from "@/lib/api";
import { formatRelativeTime } from "@/lib/format";
import { PlusIcon, SearchIcon, ShieldCheckIcon } from "@/components/icons";

interface SidebarProps {
  conversations: ConversationSummary[];
  activeConversationId: string | null;
  onSelectConversation: (id: string) => void;
  onNewConversation: () => void;
}

export function Sidebar({ conversations, activeConversationId, onSelectConversation, onNewConversation }: SidebarProps) {
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return conversations;
    return conversations.filter((c) => c.title.toLowerCase().includes(q));
  }, [conversations, query]);

  return (
    <aside className="flex w-[280px] shrink-0 flex-col gap-4 border-r border-keso-border bg-white p-5">
      <button
        type="button"
        onClick={onNewConversation}
        className="flex w-full items-center justify-center gap-2 rounded-chip bg-keso-orange px-4 py-[11px] text-sm font-semibold text-white transition-colors hover:bg-keso-orange-dark"
      >
        <PlusIcon className="text-white" />
        New conversation
      </button>

      <div className="relative">
        <SearchIcon className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-keso-ink-faint" />
        <input
          type="text"
          placeholder="Search conversations"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="w-full rounded-[10px] border border-keso-border bg-keso-surface py-[9px] pl-[34px] pr-3 text-[13px] text-keso-ink placeholder:text-keso-ink-faint focus:border-keso-indigo focus:outline-none"
        />
      </div>

      <div className="mt-1 text-[11px] font-bold uppercase tracking-wider text-keso-ink-faint">Recent</div>

      <div className="keso-scroll flex flex-1 flex-col gap-1 overflow-y-auto">
        {filtered.length === 0 ? (
          <p className="px-1 text-[13px] leading-relaxed text-keso-ink-faint">
            {conversations.length === 0
              ? "Your conversations will appear here."
              : "No conversations match your search."}
          </p>
        ) : (
          filtered.map((c) => {
            const active = c.id === activeConversationId;
            return (
              <button
                key={c.id}
                type="button"
                onClick={() => onSelectConversation(c.id)}
                className={
                  "flex gap-2.5 rounded-[10px] px-3 py-2.5 text-left transition-colors " +
                  (active ? "border-l-[3px] border-keso-indigo bg-keso-indigo-tint" : "hover:bg-keso-surface")
                }
              >
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[13px] font-semibold text-keso-ink">{c.title}</div>
                  <div className="truncate text-xs text-keso-ink-muted">{c.message_count} messages</div>
                </div>
                <span className="shrink-0 text-[11px] text-keso-ink-faint">{formatRelativeTime(c.updated_at)}</span>
              </button>
            );
          })
        )}
      </div>

      <div className="mt-auto flex items-center gap-2 border-t border-keso-border-soft pt-4">
        <ShieldCheckIcon className="shrink-0 text-keso-green" />
        <span className="text-[11.5px] leading-snug text-keso-ink-muted">
          Answers are grounded only in your approved KESO sources.
        </span>
      </div>
    </aside>
  );
}
