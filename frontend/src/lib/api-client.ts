const API_BASE = (process.env.NEXT_PUBLIC_API_URL 
  ? `${process.env.NEXT_PUBLIC_API_URL.replace(/\/$/, '')}/api/v1` 
  : "https://inquira-2iwm.onrender.com/api/v1");

export interface KnowledgeBase {
  id: string;
  name: string;
  description: string;
  document_count: number;
  created_at: string;
}

export interface DocumentItem {
  id: string;
  file_name: string;
  file_type: string;
  file_size_bytes: number;
  status: "PENDING" | "PROCESSING" | "INDEXED" | "FAILED";
  chunk_count: number;
  created_at: string;
}

export interface Citation {
  document_id?: string;
  document_name: string;
  page_number?: number;
  chunk_index: number;
  content: string;
  relevance_score?: number;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  created_at?: string;
}

export class ApiClient {
  private static token: string | null = null;

  static setToken(token: string) {
    this.token = token;
    if (typeof window !== "undefined") {
      localStorage.setItem("inquira_token", token);
    }
  }

  static getToken(): string | null {
    if (!this.token && typeof window !== "undefined") {
      this.token = localStorage.getItem("inquira_token");
    }
    return this.token;
  }

  static async fetchWithAuth(endpoint: string, options: RequestInit = {}) {
    const token = this.getToken();
    const headers = new Headers(options.headers || {});
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
    if (!headers.has("Content-Type") && !(options.body instanceof FormData)) {
      headers.set("Content-Type", "application/json");
    }

    const response = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: "Request failed" }));
      throw new Error(errorData.detail || `HTTP Error ${response.status}`);
    }

    return response.json();
  }

  // Automatic authentication (creates or logs into a demo session)
  static async ensureAuth(): Promise<string> {
    const existing = this.getToken();
    if (existing) {
      try {
        await this.fetchWithAuth("/auth/me");
        return existing;
      } catch {
        this.setToken("");
      }
    }

    const demoEmail = "demo@inquira.ai";
    const demoPassword = "InquiraDemo123!";

    try {
      // Try logging in
      const formData = new URLSearchParams();
      formData.append("username", demoEmail);
      formData.append("password", demoPassword);

      const res = await fetch(`${API_BASE}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: formData.toString(),
      });

      if (res.ok) {
        const data = await res.json();
        this.setToken(data.access_token);
        return data.access_token;
      }
    } catch (e) {
      console.warn("Login error:", e);
    }

    // Otherwise register the user
    try {
      await fetch(`${API_BASE}/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: demoEmail,
          password: demoPassword,
          full_name: "Demo User",
        }),
      });

      const formData = new URLSearchParams();
      formData.append("username", demoEmail);
      formData.append("password", demoPassword);

      const res = await fetch(`${API_BASE}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: formData.toString(),
      });

      if (res.ok) {
        const data = await res.json();
        this.setToken(data.access_token);
        return data.access_token;
      }
    } catch (e) {
      console.error("Auto registration failed:", e);
    }

    return "";
  }

  static async getKnowledgeBases(): Promise<KnowledgeBase[]> {
    return this.fetchWithAuth("/knowledge-bases");
  }

  static async createKnowledgeBase(name: string, description: string): Promise<KnowledgeBase> {
    return this.fetchWithAuth("/knowledge-bases", {
      method: "POST",
      body: JSON.stringify({ name, description }),
    });
  }

  static async getDocuments(kbId: string): Promise<DocumentItem[]> {
    return this.fetchWithAuth(`/documents?knowledge_base_id=${kbId}`);
  }

  static async uploadDocuments(kbId: string, files: FileList | File[]): Promise<any> {
    const token = this.getToken();
    const formData = new FormData();
    formData.append("knowledge_base_id", kbId);
    for (let i = 0; i < files.length; i++) {
      formData.append("files", files[i]);
    }

    const res = await fetch(`${API_BASE}/documents/upload`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: formData,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Upload failed" }));
      throw new Error(err.detail || `Upload Error ${res.status}`);
    }
    return res.json();
  }

  static async createChatSession(kbId: string, title?: string): Promise<{ id: string }> {
    return this.fetchWithAuth("/chat/sessions", {
      method: "POST",
      body: JSON.stringify({ knowledge_base_id: kbId, title: title || "New Conversation" }),
    });
  }

  static async streamChatQuery(
    sessionId: string,
    query: string,
    onToken: (token: string) => void,
    onStatus: (stage: string, message: string) => void,
    onDone: (score: number, citations: Citation[]) => void,
    onError: (err: string) => void
  ) {
    const token = this.getToken();
    try {
      const response = await fetch(`${API_BASE}/chat/sessions/${sessionId}/query`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ query, stream: true }),
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: "Chat query failed" }));
        throw new Error(err.detail || `HTTP ${response.status}`);
      }

      if (!response.body) {
        throw new Error("No response body received for streaming");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed.startsWith("data: ")) {
            try {
              const data = JSON.parse(trimmed.slice(6));
              if (data.type === "token") {
                onToken(data.content);
              } else if (data.type === "status") {
                onStatus(data.stage, data.message || data.stage);
              } else if (data.type === "done") {
                onDone(data.verification_score, data.citations || []);
              } else if (data.type === "error") {
                onError(data.message || "An error occurred in RAG pipeline");
              }
            } catch (e) {
              console.warn("Could not parse SSE chunk:", trimmed, e);
            }
          }
        }
      }
    } catch (e: any) {
      onError(e.message || "Network error");
    }
  }
}
