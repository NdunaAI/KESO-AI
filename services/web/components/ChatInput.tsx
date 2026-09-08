"use client";

import { SendIcon } from "@/components/icons";

interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  disabled: boolean;
}

export function ChatInput({ value, onChange, onSubmit, disabled }: ChatInputProps) {
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
      className="flex shrink-0 items-center gap-2.5 border-t border-keso-border bg-white px-10 py-3.5"
    >
      <div className="flex flex-1 items-center rounded-chip border border-keso-border bg-keso-surface pl-[18px] pr-1.5 focus-within:border-keso-indigo">
        <input
          type="text"
          placeholder="Ask about a project, milestone, or policy…"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          className="flex-1 bg-transparent py-2 text-sm text-keso-ink placeholder:text-keso-ink-faint focus:outline-none"
        />
      </div>
      <button
        type="submit"
        disabled={disabled || !value.trim()}
        className="flex h-[42px] w-[42px] shrink-0 items-center justify-center rounded-full bg-keso-orange text-white transition-colors hover:bg-keso-orange-dark disabled:cursor-not-allowed disabled:opacity-50"
      >
        <SendIcon />
      </button>
    </form>
  );
}
