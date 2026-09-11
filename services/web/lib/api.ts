/** Thin client for the API Gateway. See docs/03-api-specification.md. */
import { fetchEventSource } from "@microsoft/fetch-event-source";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

const STORAGE_KEY = "keso_auth_tokens";

interface TokenPair {
  accessToken: string;
  refreshToken: string;
}

function loadStoredTokens(): TokenPair | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as TokenPair) : null;
  } catch {
    return null;
  }
}

function storeTokens(tokens: TokenPair): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(tokens));
  } catch {
    // localStorage unavailable (private mode, quota) -- refresh still works
    // in-memory for the rest of this page load, just doesn't survive reload.
  }
}

function clearStoredTokens(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}

// A session set by login() survives page reloads via localStorage; without
// one, both start empty and every call below resolves to "not signed in"
// until login() is called.
const stored = loadStoredTokens();
let currentAccessToken = stored?.accessToken ?? "";
let currentRefreshToken = stored?.refreshToken ?? "";

function decodeJwtExpMs(token: string): number | null {
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    const json = JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/"))) as { exp?: number };
    return typeof json.exp === "number" ? json.exp * 1000 : null;
  } catch {
    return null;
  }
}

let refreshInFlight: Promise<boolean> | null = null;

async function refreshAccessToken(): Promise<boolean> {
  if (!currentRefreshToken) return false;
  if (refreshInFlight) return refreshInFlight;

  refreshInFlight = (async () => {
    try {
      const resp = await fetch(`${API_BASE_URL}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: currentRefreshToken }),
      });
      if (!resp.ok) return false;
      const body = (await resp.json()) as { access_token: string; refresh_token: string };
      currentAccessToken = body.access_token;
      currentRefreshToken = body.refresh_token;
      storeTokens({ accessToken: currentAccessToken, refreshToken: currentRefreshToken });
      return true;
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();

  return refreshInFlight;
}

/** Called before every API call so a soon-to-expire access token is
 * rotated ahead of time rather than failing the request it's used on. */
async function ensureValidAccessToken(): Promise<void> {
  const expMs = decodeJwtExpMs(currentAccessToken);
  const expiringSoon = expMs !== null && expMs - Date.now() < 30_000;
  if (expiringSoon) {
    await refreshAccessToken();
  }
}

function authHeaders(): Record<string, string> {
  return { Authorization: `Bearer ${currentAccessToken}` };
}

export function isAuthenticated(): boolean {
  return currentAccessToken !== "";
}

export interface UserProfile {
  id: string;
  email: string;
  display_name: string;
  roles: string[];
  scope: { projects: string[]; settlements: string[] };
}

export async function login(email: string, password: string): Promise<UserProfile> {
  const resp = await fetch(`${API_BASE_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!resp.ok) {
    const detail = (await resp.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(detail?.detail ?? "Invalid email or password");
  }
  const body = (await resp.json()) as { access_token: string; refresh_token: string };
  currentAccessToken = body.access_token;
  currentRefreshToken = body.refresh_token;
  storeTokens({ accessToken: currentAccessToken, refreshToken: currentRefreshToken });

  const profile = await fetchMe();
  if (!profile) throw new Error("Logged in, but could not load your profile.");
  return profile;
}

export async function logout(): Promise<void> {
  if (currentRefreshToken) {
    try {
      await fetch(`${API_BASE_URL}/auth/logout`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: currentRefreshToken }),
      });
    } catch {
      // best-effort revoke; local state is cleared below regardless
    }
  }
  currentAccessToken = "";
  currentRefreshToken = "";
  clearStoredTokens();
}

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
  await ensureValidAccessToken();
  await fetchEventSource(`${API_BASE_URL}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify({ conversation_id: conversationId, message, filters }),
    signal,
    // Without this, fetch-event-source closes the connection and opens a
    // brand-new POST /chat when the tab is backgrounded -- easy to trigger
    // here since LLM generation can run for minutes (docs/06-rag-pipeline.md
    // #6.2). Both requests then write into the same "last assistant
    // message" slot (see page.tsx's updateLastAssistant), interleaving two
    // independent answers/citation sets into one garbled bubble.
    openWhenHidden: true,
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

export async function fetchMe(): Promise<UserProfile | null> {
  if (!currentAccessToken) return null;
  await ensureValidAccessToken();
  const resp = await fetch(`${API_BASE_URL}/auth/me`, { headers: authHeaders() });
  if (!resp.ok) return null;
  return (await resp.json()) as UserProfile;
}

export interface ConversationSummary {
  id: string;
  title: string;
  updated_at: string;
  message_count: number;
}

export async function fetchConversations(): Promise<ConversationSummary[]> {
  if (!currentAccessToken) return [];
  await ensureValidAccessToken();
  const resp = await fetch(`${API_BASE_URL}/conversations`, { headers: authHeaders() });
  if (!resp.ok) return [];
  const body = (await resp.json()) as { items: ConversationSummary[] };
  return body.items;
}

export interface ConversationMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  citations: Citation[];
  created_at: string;
}

export async function fetchConversation(id: string): Promise<ConversationMessage[] | null> {
  if (!currentAccessToken) return null;
  await ensureValidAccessToken();
  const resp = await fetch(`${API_BASE_URL}/conversations/${id}`, { headers: authHeaders() });
  if (!resp.ok) return null;
  const body = (await resp.json()) as { messages: ConversationMessage[] };
  return body.messages;
}
