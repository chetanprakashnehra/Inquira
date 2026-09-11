const API_BASE = (process.env.NEXT_PUBLIC_API_URL ? `${process.env.NEXT_PUBLIC_API_URL}/api/v1` : "https://inquira-2iwm.onrender.com/api/v1");


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
}
