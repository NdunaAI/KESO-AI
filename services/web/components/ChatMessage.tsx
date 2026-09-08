import type { Citation } from "@/lib/api";
import { formatClockTime } from "@/lib/format";
import { BotIcon, DocIcon, RecordIcon } from "@/components/icons";

export interface DisplayMessage {
  role: "user" | "assistant";
  text: string;
  citations: Citation[];
  createdAt: Date;
}

export function ChatMessage({ message, isStreaming }: { message: DisplayMessage; isStreaming: boolean }) {
  const time = formatClockTime(message.createdAt);

  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="flex max-w-[62%] flex-col items-end gap-1">
          <div className="rounded-[16px_16px_4px_16px] bg-keso-indigo px-4 py-3 text-[14.5px] leading-relaxed text-white">
            {message.text}
          </div>
          <span className="text-[11px] text-keso-ink-faint">{time}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-start gap-3">
      <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-keso-green">
        <BotIcon className="text-white" />
      </div>
      <div className="flex max-w-[66%] flex-col gap-1">
        <div className="rounded-[16px_16px_16px_4px] border border-keso-border bg-white px-[18px] py-4 shadow-[0_1px_3px_rgba(42,42,56,0.06)]">
          <p className="whitespace-pre-wrap text-[14.5px] leading-relaxed text-keso-ink">
            {message.text || (isStreaming ? "…" : "")}
          </p>

          {message.citations.length > 0 && (
            <>
              <div className="mb-2 mt-3 text-[11px] font-bold uppercase tracking-wider text-keso-ink-faint">
                Sources
              </div>
              <div className="flex flex-wrap gap-2">
                {message.citations.map((c) => (
                  <a
                    key={c.id}
                    href={c.uri ?? "#"}
                    className="flex items-center gap-1.5 rounded-chip border border-keso-border bg-keso-surface px-3 py-1.5 text-[12.5px] font-medium text-keso-ink hover:border-keso-indigo hover:text-keso-ink"
                  >
                    {c.source_type === "document" ? (
                      <DocIcon className="shrink-0 text-keso-orange" />
                    ) : (
                      <RecordIcon className="shrink-0 text-keso-indigo" />
                    )}
                    {c.title}
                  </a>
                ))}
              </div>
            </>
          )}
        </div>
        <span className="text-[11px] text-keso-ink-faint">KESO Assistant · {time}</span>
      </div>
    </div>
  );
}
