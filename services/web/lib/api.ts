/**
 * Thin client for the API Gateway's streaming chat endpoint.
 * See docs/03-api-specification.md #3.2 for the event contract.
 *
 * TODO: replace DEV_BEARER_TOKEN with a real Keycloak OIDC session (docs
 * #3.4) once next-auth/Keycloak wiring is added -- this scaffold only
 * covers the chat request/stream plumbing.
 */
import { fetchEventSource } from "@microsoft/fetch-event-source";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
const DEV_BEARER_TOKEN = process.env.NEXT_PUBLIC_DEV_BEARER_TOKEN ?? "";

export interface Citation {
  id: string;
  source_type: "document" | "record";
  source_system: string;
  title: string;
  uri?: string;
  snippet?: string;
  confidence?: number;
}

export interface ChatFilters {
  project_ids?: string[];
  settlement_ids?: string[];
  date_from?: string;
  date_to?: string;
}

export interface ChatStreamHandlers {
  onMeta?: (meta: { conversation_id: string; message_id: string }) => void;
  onToken?: (text: string) => void;
  onCitation?: (citation: Citation) => void;
  onWarning?: (warning: { code: string; message: string }) => void;
  onDone?: (info: { finish_reason: "stop" | "refused" | "error" }) => void;
  onError?: (error: { code: string; message: string }) => void;
}

export async function streamChat(
  message: string,
  conversationId: string | null,
  filters: ChatFilters,
  handlers: ChatStreamHandlers,
  signal?: AbortSignal
): Promise<void> {
  await fetchEventSource(`${API_BASE_URL}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${DEV_BEARER_TOKEN}`,
    },
    body: JSON.stringify({ conversation_id: conversationId, message, filters }),
    signal,
    onmessage(ev) {
      const data = ev.data ? JSON.parse(ev.data) : {};
      switch (ev.event) {
        case "meta":
          handlers.onMeta?.(data);
          break;
        case "token":
          handlers.onToken?.(data.text);
          break;
        case "citation":
          handlers.onCitation?.(data);
          break;
        case "warning":
          handlers.onWarning?.(data);
          break;
        case "done":
          handlers.onDone?.(data);
          break;
        case "error":
          handlers.onError?.(data);
          break;
      }
    },
    onerror(err) {
      handlers.onError?.({ code: "STREAM_ERROR", message: String(err) });
      throw err; // stop fetch-event-source's built-in retry; caller decides what's next
    },
  });
}
