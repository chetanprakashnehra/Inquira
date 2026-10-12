import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import ConfirmModal from "../components/ConfirmModal";
import {
  IconOverview,
  IconDatabase,
  IconBrain,
  IconDocuments,
  IconChat,
  IconPlus,
  IconTrash,
  IconUpload,
  IconRefresh,
  IconCheck,
  IconAlert,
  IconLogout,
  IconSparkles,
  IconFile,
  IconSend,
  IconClose,
  IconCopy,
  IconLayers,
  IconSearch,
} from "../components/Icons";

const API =
  (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");

async function request(path, options = {}) {
  const token = localStorage.getItem("access_token");
  const headers = { ...options.headers };

  if (token) headers.Authorization = `Bearer ${token}`;

  if (options.body instanceof FormData) {
    // Browser sets multipart boundary
  } else if (options.body instanceof URLSearchParams) {
    headers["Content-Type"] = "application/x-www-form-urlencoded";
  } else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(`${API}${path}`, {
    ...options,
    headers,
  });

  const contentType = response.headers.get("content-type");
  const data = contentType?.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const detail = data?.detail;
    const message = Array.isArray(detail)
      ? detail.map((item) => item.msg).join(", ")
      : typeof detail === "string"
        ? detail
        : typeof data === "string"
          ? data
          : "Request failed";

    throw new Error(message);
  }

  return data;
}

function asList(data, keys = []) {
  if (Array.isArray(data)) return data;
  for (const key of keys) {
    if (Array.isArray(data?.[key])) return data[key];
  }
  return [];
}

const STARTER_PROMPTS = [
  "Summarize the main points of this document.",
  "What are the key takeaways or conclusions?",
  "List the core topics and definitions covered.",
  "What questions can this document answer?",
];

export default function Dashboard() {
  const { user, logout } = useAuth();

  const [section, setSection] = useState("overview");
  const [knowledgeBases, setKnowledgeBases] = useState([]);
  const [selectedKB, setSelectedKB] = useState("");
  const [documents, setDocuments] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [activeSession, setActiveSession] = useState(null);
  const [messages, setMessages] = useState([]);

  const [kbName, setKbName] = useState("");
  const [kbDescription, setKbDescription] = useState("");
  const [kbSearch, setKbSearch] = useState("");
  const [file, setFile] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [question, setQuestion] = useState("");

  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [progress, setProgress] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [copiedIndex, setCopiedIndex] = useState(null);

  // Confirmation Modal state
  const [confirmModal, setConfirmModal] = useState({
    isOpen: false,
    title: "",
    message: "",
    confirmText: "Delete",
    isDanger: true,
    loading: false,
    onConfirm: () => {},
  });

  const bottomRef = useRef(null);
  const fileInputRef = useRef(null);

  const loadKnowledgeBases = useCallback(async () => {
    const data = await request("/knowledge-bases");
    const list = asList(data, ["knowledge_bases", "items"]);
    setKnowledgeBases(list);

    setSelectedKB((current) => {
      if (current && list.some((kb) => kb.id === current)) {
        return current;
      }
      return list[0]?.id || "";
    });

    return list;
  }, []);

  const loadSessions = useCallback(async () => {
    const data = await request("/sessions");
    setSessions(asList(data, ["sessions", "items"]));
  }, []);

  const loadDocuments = useCallback(async (kbId) => {
    if (!kbId) {
      setDocuments([]);
      return;
    }

    const data = await request(`/knowledge-bases/${kbId}/documents`);
    setDocuments(asList(data, ["documents", "items"]));
  }, []);

  const loadMessages = useCallback(async (sessionId) => {
    const data = await request(`/sessions/${sessionId}/messages`);
    setMessages(asList(data, ["messages", "items"]));
  }, []);

  useEffect(() => {
    async function initialize() {
      setLoading(true);
      setError("");

      try {
        await Promise.all([loadKnowledgeBases(), loadSessions()]);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }

    initialize();
  }, [loadKnowledgeBases, loadSessions]);

  useEffect(() => {
    if (!selectedKB) {
      setDocuments([]);
      setActiveSession(null);
      setMessages([]);
      return;
    }

    loadDocuments(selectedKB).catch((err) => setError(err.message));

    const existingSession = sessions.find(
      (session) => session.knowledge_base_id === selectedKB
    );

    if (!activeSession || activeSession.knowledge_base_id !== selectedKB) {
      setActiveSession(null);
      setMessages([]);

      if (existingSession) {
        setActiveSession(existingSession);
        loadMessages(existingSession.id).catch((err) => setError(err.message));
      }
    }
  }, [selectedKB, sessions, activeSession, loadDocuments, loadMessages]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, progress]);

  // Poll pending document ingestion
  useEffect(() => {
    const pending = documents.filter((doc) =>
      ["pending", "processing", "queued"].includes(
        String(doc.status || "").toLowerCase()
      )
    );

    if (!pending.length) return;

    const timer = setInterval(async () => {
      try {
        const updated = await Promise.all(
          pending.map(async (doc) => {
            const id = doc.id || doc.document_id;
            if (!id) return doc;
            const status = await request(`/knowledge-bases/documents/${id}/status`);
            return { ...doc, ...status };
          })
        );

        setDocuments((current) =>
          current.map((doc) => {
            const id = doc.id || doc.document_id;
            return (
              updated.find((item) => (item.id || item.document_id) === id) || doc
            );
          })
        );
      } catch (err) {
        console.error("Document status check failed:", err);
      }
    }, 3000);

    return () => clearInterval(timer);
  }, [documents]);

  // Create Knowledge Base
  async function createKnowledgeBase(event) {
    event.preventDefault();
    setError("");
    setNotice("");

    try {
      const params = new URLSearchParams({ name: kbName.trim() });
      if (kbDescription.trim()) {
        params.set("description", kbDescription.trim());
      }

      const newKB = await request(`/knowledge-bases?${params.toString()}`, {
        method: "POST",
      });

      setKbName("");
      setKbDescription("");
      const list = await loadKnowledgeBases();
      if (newKB?.id) {
        setSelectedKB(newKB.id);
      }
      setNotice("Knowledge base created successfully.");
      setSection("documents");
    } catch (err) {
      setError(err.message);
    }
  }

  // Delete Knowledge Base with Confirm Modal
  function handleDeleteKB(kbId, kbName) {
    const targetName = kbName || "this knowledge base";
    setConfirmModal({
      isOpen: true,
      title: `Delete "${targetName}"?`,
      message: `Are you sure you want to delete "${targetName}"? All associated documents, vector embeddings, and chat history will be permanently deleted. This action cannot be undone.`,
      confirmText: "Delete Knowledge Base",
      isDanger: true,
      loading: false,
      onConfirm: async () => {
        try {
          setConfirmModal((m) => ({ ...m, loading: true }));
          await request(`/knowledge-bases/${kbId}`, { method: "DELETE" });

          if (selectedKB === kbId) {
            setSelectedKB("");
            setDocuments([]);
            setActiveSession(null);
            setMessages([]);
          }

          await loadKnowledgeBases();
          await loadSessions();
          setNotice(`Knowledge base "${targetName}" was permanently deleted.`);
          setConfirmModal({ isOpen: false });
        } catch (err) {
          setError(err.message || "Failed to delete knowledge base");
          setConfirmModal({ isOpen: false });
        }
      },
    });
  }

  // Delete Document with Confirm Modal
  function handleDeleteDocument(docId, docName) {
    const targetName = docName || "this document";
    setConfirmModal({
      isOpen: true,
      title: `Delete "${targetName}"?`,
      message: `Are you sure you want to delete "${targetName}"? Its chunked text and vector embeddings will be removed from your AI index.`,
      confirmText: "Delete Document",
      isDanger: true,
      loading: false,
      onConfirm: async () => {
        try {
          setConfirmModal((m) => ({ ...m, loading: true }));
          await request(`/knowledge-bases/documents/${docId}`, {
            method: "DELETE",
          });
          await loadDocuments(selectedKB);
          setNotice(`Document "${targetName}" was deleted.`);
          setConfirmModal({ isOpen: false });
        } catch (err) {
          setError(err.message || "Failed to delete document");
          setConfirmModal({ isOpen: false });
        }
      },
    });
  }

  // Delete Chat Session with Confirm Modal
  function handleDeleteSession(sessionId, sessionTitle) {
    const targetTitle = sessionTitle || "this chat conversation";
    setConfirmModal({
      isOpen: true,
      title: "Delete chat conversation?",
      message: `Are you sure you want to delete "${targetTitle}"? All messages in this conversation will be permanently removed.`,
      confirmText: "Delete Chat",
      isDanger: true,
      loading: false,
      onConfirm: async () => {
        try {
          setConfirmModal((m) => ({ ...m, loading: true }));
          await request(`/sessions/${sessionId}`, { method: "DELETE" });
          if (activeSession?.id === sessionId) {
            setActiveSession(null);
            setMessages([]);
          }
          await loadSessions();
          setNotice("Chat conversation deleted.");
          setConfirmModal({ isOpen: false });
        } catch (err) {
          setError(err.message || "Failed to delete chat session");
          setConfirmModal({ isOpen: false });
        }
      },
    });
  }

  // Upload Document
  async function uploadDocument(event) {
    event?.preventDefault();

    if (!selectedKB || !file) {
      setError("Please select a knowledge base and a file to upload.");
      return;
    }

    setError("");
    setNotice("");

    try {
      const formData = new FormData();
      formData.append("file", file);

      const result = await request(
        `/knowledge-bases/${selectedKB}/documents`,
        {
          method: "POST",
          body: formData,
        }
      );

      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";

      await loadDocuments(selectedKB);
      setNotice(
        `Upload submitted: ${result.filename || result.message || "processing in background"}`
      );
    } catch (err) {
      setError(err.message);
    }
  }

  function handleDragOver(e) {
    e.preventDefault();
    setIsDragging(true);
  }

  function handleDragLeave(e) {
    e.preventDefault();
    setIsDragging(false);
  }

  function handleDrop(e) {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setFile(e.dataTransfer.files[0]);
    }
  }

  // Create Chat Session
  async function createChatSession() {
    if (!selectedKB) {
      setError("Select a knowledge base first.");
      return;
    }

    setError("");
    setNotice("");

    try {
      const session = await request("/sessions", {
        method: "POST",
        body: JSON.stringify({
          knowledge_base_id: selectedKB,
          title: "New chat",
        }),
      });

      await loadSessions();
      setActiveSession(session);
      setMessages([]);
      setSection("chat");
    } catch (err) {
      setError(err.message);
    }
  }

  async function openSession(session) {
    setError("");
    setActiveSession(session);
    setSelectedKB(session.knowledge_base_id);
    setSection("chat");

    try {
      await loadMessages(session.id);
    } catch (err) {
      setError(err.message);
    }
  }

  function copyAnswer(text, index) {
    navigator.clipboard.writeText(text);
    setCopiedIndex(index);
    setTimeout(() => setCopiedIndex(null), 2000);
  }

  // Send Chat Message
  async function sendMessage(event) {
    event?.preventDefault();

    const text = question.trim();
    if (!text || sending) return;

    if (!selectedKB) {
      setError("Please select a knowledge base first.");
      return;
    }

    setError("");
    setNotice("");

    let session = activeSession;

    try {
      if (!session || session.knowledge_base_id !== selectedKB) {
        session = await request("/sessions", {
          method: "POST",
          body: JSON.stringify({
            knowledge_base_id: selectedKB,
            title: text.slice(0, 60),
          }),
        });

        setActiveSession(session);
        await loadSessions();
      }

      setQuestion("");
      setSending(true);
      setProgress("Starting agent...");
      setMessages((current) => [
        ...current,
        { role: "user", content: text },
      ]);

      const response = await fetch(`${API}/chat/stream`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${localStorage.getItem("access_token")}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          session_id: session.id,
          question: text,
        }),
      });

      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || "Chat request failed");
      }

      if (!response.body) {
        throw new Error("Streaming is not supported by this browser.");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let finished = false;

      while (!finished) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() || "";

        for (const rawEvent of events) {
          const line = rawEvent
            .split("\n")
            .find((item) => item.startsWith("data: "));

          if (!line) continue;

          const event = JSON.parse(line.slice(6));

          if (event.type === "progress") {
            setProgress(
              event.status === "started"
                ? `${event.message}...`
                : `${event.message} complete`
            );
          }

          if (event.type === "done") {
            setMessages((current) => [
              ...current,
              {
                role: "assistant",
                content: event.answer,
                citations: event.citations || [],
                supported: event.supported ?? event.is_supported ?? false,
                retry_count: event.retry_count ?? 0,
              },
            ]);

            setProgress(
              event.supported ?? event.is_supported
                ? "Answer verified from documents"
                : "Answer generated"
            );

            finished = true;
          }

          if (event.type === "error") {
            throw new Error(event.message || "Agent failed to generate answer");
          }
        }
      }

      await loadSessions();
    } catch (err) {
      setError(err.message);
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: `Error: ${err.message}`,
        },
      ]);
      setProgress("");
    } finally {
      setSending(false);
    }
  }

  const currentSessions = sessions.filter(
    (item) => !selectedKB || item.knowledge_base_id === selectedKB
  );

  const selectedKBObj = knowledgeBases.find((kb) => kb.id === selectedKB);

  const filteredKBs = knowledgeBases.filter((kb) => {
    if (!kbSearch.trim()) return true;
    const q = kbSearch.toLowerCase();
    return (
      kb.name?.toLowerCase().includes(q) ||
      kb.description?.toLowerCase().includes(q)
    );
  });

  return (
    <div className="workspace-shell">
      {/* Sidebar Navigation */}
      <aside className="workspace-sidebar">
        <div className="sidebar-brand">
          <div className="brand-logo-glow">
            <span className="brand-icon">I</span>
          </div>
          <div className="brand-title-wrap">
            <span className="brand-name">Inquira</span>
            <span className="brand-tag">RAG v2.0</span>
          </div>
        </div>

        <p className="sidebar-label">NAVIGATION</p>

        <button
          className={`nav-item ${section === "overview" ? "active" : ""}`}
          onClick={() => setSection("overview")}
        >
          <IconOverview size={17} /> Overview
        </button>

        <button
          className={`nav-item ${section === "kbs" ? "active" : ""}`}
          onClick={() => setSection("kbs")}
        >
          <IconDatabase size={17} /> Knowledge Bases
        </button>

        <button
          className={`nav-item ${section === "documents" ? "active" : ""}`}
          onClick={() => setSection("documents")}
        >
          <IconDocuments size={17} /> Documents
        </button>

        <button
          className={`nav-item ${section === "chat" ? "active" : ""}`}
          onClick={() => setSection("chat")}
        >
          <IconChat size={17} /> AI Assistant
        </button>

        {/* Knowledge Base Switcher */}
        <div className="sidebar-section">
          <div className="sidebar-section-header">
            <p className="sidebar-label">ACTIVE WORKSPACE</p>
            {selectedKBObj && (
              <button
                className="icon-btn-danger icon-btn-small"
                onClick={() => handleDeleteKB(selectedKBObj.id, selectedKBObj.name)}
                title="Delete active knowledge base"
              >
                <IconTrash size={14} />
              </button>
            )}
          </div>

          <select
            className="kb-select"
            value={selectedKB}
            onChange={(event) => setSelectedKB(event.target.value)}
          >
            <option value="">Choose knowledge base...</option>
            {knowledgeBases.map((kb) => (
              <option key={kb.id} value={kb.id}>
                {kb.name}
              </option>
            ))}
          </select>

          <button
            className="nav-item add-kb-btn"
            onClick={() => setSection("create-kb")}
          >
            <IconPlus size={15} /> New knowledge base
          </button>
        </div>

        {/* Recent Chats Section */}
        <div className="sidebar-section">
          <div className="sidebar-section-header">
            <p className="sidebar-label">CONVERSATIONS</p>
            {selectedKB && (
              <button
                className="icon-btn-small"
                onClick={createChatSession}
                title="Start a new chat"
              >
                <IconPlus size={14} />
              </button>
            )}
          </div>

          <div className="sessions-list">
            {currentSessions.map((session) => (
              <div key={session.id} className="session-item-row">
                <button
                  className={`nav-item session-link ${
                    activeSession?.id === session.id ? "active" : ""
                  }`}
                  onClick={() => openSession(session)}
                  title={session.title || "Chat"}
                >
                  <IconChat size={14} />
                  <span>{(session.title || "New chat").slice(0, 22)}</span>
                </button>
                <button
                  className="session-delete-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDeleteSession(session.id, session.title);
                  }}
                  title="Delete chat"
                >
                  <IconTrash size={13} />
                </button>
              </div>
            ))}

            {currentSessions.length === 0 && (
              <p className="sidebar-empty-text">No conversations yet.</p>
            )}
          </div>
        </div>

        {/* User Footer */}
        <div className="sidebar-user">
          <div className="avatar">
            {(user?.full_name || user?.email || "U").charAt(0).toUpperCase()}
          </div>
          <div className="user-info">
            <strong>{user?.full_name || "Workspace User"}</strong>
            <span>{user?.email}</span>
          </div>
          <button
            className="logout-button"
            onClick={logout}
            title="Log out of Inquira"
          >
            <IconLogout size={16} />
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="workspace-main">
        {/* Workspace Header */}
        <header className="workspace-header">
          <div>
            <p className="eyebrow">HYBRID AGENTIC RAG SYSTEM</p>
            <h1>
              {section === "overview" && "Workspace Overview"}
              {section === "kbs" && "Knowledge Bases"}
              {section === "create-kb" && "New Knowledge Base"}
              {section === "documents" && "Document Library"}
              {section === "chat" && "AI Knowledge Assistant"}
            </h1>
          </div>

          {selectedKBObj && (
            <div className="kb-badge-actions">
              <span className="workspace-badge">
                <IconBrain size={14} /> {selectedKBObj.name}
              </span>
              <button
                className="badge-delete-btn"
                onClick={() => handleDeleteKB(selectedKBObj.id, selectedKBObj.name)}
                title="Delete this knowledge base"
              >
                <IconTrash size={13} /> Delete KB
              </button>
            </div>
          )}
        </header>

        {/* Alerts */}
        {error && (
          <div className="alert error-alert">
            <div className="alert-content">
              <IconAlert size={16} />
              <span>{error}</span>
            </div>
            <button onClick={() => setError("")} aria-label="Dismiss error">
              <IconClose size={15} />
            </button>
          </div>
        )}

        {notice && (
          <div className="alert success-alert">
            <div className="alert-content">
              <IconCheck size={16} />
              <span>{notice}</span>
            </div>
            <button onClick={() => setNotice("")} aria-label="Dismiss notice">
              <IconClose size={15} />
            </button>
          </div>
        )}

        {loading && <p className="muted">Loading workspace data...</p>}

        {/* =========================================================
            SECTION: OVERVIEW
        ========================================================= */}
        {!loading && section === "overview" && (
          <>
            <section className="welcome-panel">
              <p className="eyebrow">INTELLIGENT KNOWLEDGE RETRIEVAL</p>
              <h2>Your documents, fully understood.</h2>
              <p>
                Inquira combines dense neural search, BM25 keyword matching, Reciprocal
                Rank Fusion, and Groq LLM verification to deliver accurate, citation-backed answers.
              </p>
              <div className="welcome-actions">
                <button
                  className="primary-button"
                  onClick={() =>
                    setSection(knowledgeBases.length ? "chat" : "create-kb")
                  }
                >
                  <IconSparkles size={16} />
                  {knowledgeBases.length ? "Start AI Chat" : "Create first Knowledge Base"}
                </button>
                <button
                  className="secondary-button"
                  onClick={() => setSection("kbs")}
                >
                  <IconDatabase size={16} /> Manage Knowledge Bases
                </button>
              </div>
            </section>

            {/* Metrics Grid */}
            <section className="stats-grid">
              <div className="stat-card">
                <div className="stat-card-header">
                  <IconDatabase size={20} className="stat-icon-indigo" />
                  <span>Knowledge Bases</span>
                </div>
                <strong>{knowledgeBases.length}</strong>
              </div>

              <div className="stat-card">
                <div className="stat-card-header">
                  <IconDocuments size={20} className="stat-icon-emerald" />
                  <span>Active Documents</span>
                </div>
                <strong>{documents.length}</strong>
              </div>

              <div className="stat-card">
                <div className="stat-card-header">
                  <IconChat size={20} className="stat-icon-amber" />
                  <span>Conversations</span>
                </div>
                <strong>{currentSessions.length}</strong>
              </div>
            </section>

            {/* Knowledge Bases Quick Grid */}
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <h2>Your Knowledge Bases</h2>
                  <p>Select a knowledge base to inspect documents or chat with your files.</p>
                </div>
                <button
                  className="primary-button"
                  onClick={() => setSection("create-kb")}
                >
                  <IconPlus size={15} /> New Knowledge Base
                </button>
              </div>

              {knowledgeBases.length === 0 ? (
                <div className="empty-inline">
                  No knowledge bases created yet. Click above to create your first one.
                </div>
              ) : (
                <div className="kb-grid">
                  {knowledgeBases.map((kb) => {
                    const isActive = kb.id === selectedKB;
                    return (
                      <div
                        key={kb.id}
                        className={`kb-card ${isActive ? "active" : ""}`}
                      >
                        <div>
                          <div className="kb-card-top">
                            <div className="kb-card-icon">
                              <IconBrain size={20} />
                            </div>
                            {isActive && (
                              <span className="kb-card-active-pill">Active</span>
                            )}
                          </div>
                          <h3 className="kb-card-title">{kb.name}</h3>
                          <p className="kb-card-desc">
                            {kb.description || "No description provided."}
                          </p>
                        </div>

                        <div className="kb-card-bottom">
                          <span className="kb-card-meta">
                            {new Date(kb.created_at || Date.now()).toLocaleDateString()}
                          </span>
                          <div className="kb-card-actions">
                            <button
                              className="icon-btn"
                              onClick={() => {
                                setSelectedKB(kb.id);
                                setSection("documents");
                              }}
                              title="View Documents"
                            >
                              <IconDocuments size={15} />
                            </button>
                            <button
                              className="icon-btn"
                              onClick={() => {
                                setSelectedKB(kb.id);
                                setSection("chat");
                              }}
                              title="Start AI Chat"
                            >
                              <IconChat size={15} />
                            </button>
                            <button
                              className="icon-btn icon-btn-danger"
                              onClick={() => handleDeleteKB(kb.id, kb.name)}
                              title="Delete Knowledge Base"
                            >
                              <IconTrash size={15} />
                            </button>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </section>
          </>
        )}

        {/* =========================================================
            SECTION: KNOWLEDGE BASES (FULL VIEW)
        ========================================================= */}
        {section === "kbs" && (
          <div className="content-stack">
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <h2>All Knowledge Bases</h2>
                  <p>Organize, search, and manage your isolated document collections.</p>
                </div>
                <div className="panel-heading-actions">
                  <div className="search-input-wrapper">
                    <IconSearch size={15} className="search-icon" />
                    <input
                      type="text"
                      placeholder="Search knowledge bases..."
                      value={kbSearch}
                      onChange={(e) => setKbSearch(e.target.value)}
                    />
                  </div>
                  <button
                    className="primary-button"
                    onClick={() => setSection("create-kb")}
                  >
                    <IconPlus size={15} /> New Knowledge Base
                  </button>
                </div>
              </div>

              {filteredKBs.length === 0 ? (
                <div className="empty-inline">
                  {kbSearch ? "No matching knowledge bases found." : "No knowledge bases yet."}
                </div>
              ) : (
                <div className="kb-grid">
                  {filteredKBs.map((kb) => {
                    const isActive = kb.id === selectedKB;
                    return (
                      <div
                        key={kb.id}
                        className={`kb-card ${isActive ? "active" : ""}`}
                      >
                        <div>
                          <div className="kb-card-top">
                            <div className="kb-card-icon">
                              <IconDatabase size={20} />
                            </div>
                            {isActive ? (
                              <span className="kb-card-active-pill">Active</span>
                            ) : (
                              <button
                                className="icon-btn icon-btn-small"
                                onClick={() => setSelectedKB(kb.id)}
                                title="Set as active workspace"
                              >
                                Select
                              </button>
                            )}
                          </div>
                          <h3 className="kb-card-title">{kb.name}</h3>
                          <p className="kb-card-desc">
                            {kb.description || "No description provided."}
                          </p>
                        </div>

                        <div className="kb-card-bottom">
                          <span className="kb-card-meta">
                            {new Date(kb.created_at || Date.now()).toLocaleDateString()}
                          </span>
                          <div className="kb-card-actions">
                            <button
                              className="icon-btn"
                              onClick={() => {
                                setSelectedKB(kb.id);
                                setSection("documents");
                              }}
                              title="Manage Documents"
                            >
                              <IconDocuments size={15} />
                            </button>
                            <button
                              className="icon-btn"
                              onClick={() => {
                                setSelectedKB(kb.id);
                                setSection("chat");
                              }}
                              title="AI Chat"
                            >
                              <IconChat size={15} />
                            </button>
                            <button
                              className="icon-btn icon-btn-danger"
                              onClick={() => handleDeleteKB(kb.id, kb.name)}
                              title="Delete Knowledge Base"
                            >
                              <IconTrash size={15} />
                            </button>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </section>
          </div>
        )}

        {/* =========================================================
            SECTION: CREATE KNOWLEDGE BASE
        ========================================================= */}
        {section === "create-kb" && (
          <section className="panel form-panel">
            <div className="panel-heading">
              <div>
                <h2>Create Knowledge Base</h2>
                <p>Create an isolated repository for your documents and AI embeddings.</p>
              </div>
            </div>

            <form onSubmit={createKnowledgeBase} className="stack-form">
              <label htmlFor="kb-name">Knowledge Base Name</label>
              <input
                id="kb-name"
                value={kbName}
                onChange={(event) => setKbName(event.target.value)}
                placeholder="e.g. Technical Documentation, Resumes, Financial Reports"
                required
              />

              <label htmlFor="kb-description">Description (Optional)</label>
              <textarea
                id="kb-description"
                value={kbDescription}
                onChange={(event) => setKbDescription(event.target.value)}
                placeholder="Explain what topics or files belong to this knowledge base..."
                rows={4}
              />

              <div className="form-button-row">
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => setSection("overview")}
                >
                  Cancel
                </button>
                <button type="submit" className="primary-button">
                  <IconPlus size={16} /> Create Knowledge Base
                </button>
              </div>
            </form>
          </section>
        )}

        {/* =========================================================
            SECTION: DOCUMENTS
        ========================================================= */}
        {section === "documents" && (
          <div className="content-stack">
            {!selectedKB ? (
              <section className="empty-state">
                <div className="empty-state-icon">
                  <IconDatabase size={32} />
                </div>
                <h2>No knowledge base selected</h2>
                <p>Please select an existing knowledge base or create a new one to manage documents.</p>
                <button
                  className="primary-button"
                  onClick={() => setSection("create-kb")}
                >
                  <IconPlus size={15} /> Create Knowledge Base
                </button>
              </section>
            ) : (
              <>
                {/* Upload Panel */}
                <section className="panel">
                  <div className="panel-heading">
                    <div>
                      <h2>Upload Documents</h2>
                      <p>
                        Adding to: <strong>{selectedKBObj?.name}</strong>. Files will be parsed,
                        chunked, and embedded into Qdrant vector storage.
                      </p>
                    </div>
                  </div>

                  <form className="upload-form-wrap" onSubmit={uploadDocument}>
                    <div
                      className={`upload-dropzone ${isDragging ? "dragging" : ""}`}
                      onDragOver={handleDragOver}
                      onDragLeave={handleDragLeave}
                      onDrop={handleDrop}
                      onClick={() => fileInputRef.current?.click()}
                    >
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept=".pdf,.docx,.txt,.json"
                        style={{ display: "none" }}
                        onChange={(e) => setFile(e.target.files?.[0] || null)}
                      />

                      <div className="dropzone-icon">
                        <IconUpload size={24} />
                      </div>
                      <p className="dropzone-text">
                        {file ? file.name : "Drag and drop your file here, or browse"}
                      </p>
                      <p className="dropzone-subtext">
                        {file
                          ? `${(file.size / (1024 * 1024)).toFixed(2)} MB · Click to replace`
                          : "Upload documents to index into your RAG engine"}
                      </p>

                      <div className="dropzone-formats">
                        <span className="format-badge">PDF</span>
                        <span className="format-badge">DOCX</span>
                        <span className="format-badge">TXT</span>
                        <span className="format-badge">JSON</span>
                      </div>
                    </div>

                    {file && (
                      <div className="file-selected-box">
                        <div className="file-selected-info">
                          <IconFile size={18} />
                          <strong>{file.name}</strong>
                          <span className="muted">
                            ({(file.size / 1024).toFixed(1)} KB)
                          </span>
                        </div>
                        <button type="submit" className="primary-button">
                          <IconUpload size={16} /> Process & Ingest
                        </button>
                      </div>
                    )}
                  </form>
                </section>

                {/* Documents List */}
                <section className="panel">
                  <div className="panel-heading">
                    <div>
                      <h2>Indexed Documents ({documents.length})</h2>
                      <p>
                        Status automatically updates as background workers process chunks.
                      </p>
                    </div>

                    <button
                      className="secondary-button"
                      onClick={() => loadDocuments(selectedKB)}
                    >
                      <IconRefresh size={14} /> Refresh
                    </button>
                  </div>

                  {documents.length === 0 ? (
                    <div className="empty-inline">
                      No documents uploaded to this knowledge base yet.
                    </div>
                  ) : (
                    <div className="document-list">
                      {documents.map((doc, index) => {
                        const id = doc.id || doc.document_id || index;
                        const status = String(doc.status || "unknown").toLowerCase();
                        const ext = (doc.filename || doc.name || "")
                          .split(".")
                          .pop()
                          ?.toUpperCase() || "DOC";

                        return (
                          <div className="document-row" key={id}>
                            <span
                              className={`doc-badge ${
                                ext === "PDF"
                                  ? "badge-pdf"
                                  : ext === "DOCX"
                                    ? "badge-docx"
                                    : "badge-txt"
                              }`}
                            >
                              {ext}
                            </span>

                            <div className="document-info">
                              <strong>{doc.filename || doc.name || "Document"}</strong>
                              <span>
                                {doc.chunk_count != null
                                  ? `${doc.chunk_count} chunks indexed`
                                  : "Processing"}
                                {doc.error_message
                                  ? ` · Error: ${doc.error_message}`
                                  : ""}
                              </span>
                            </div>

                            <span className={`status-pill status-${status}`}>
                              {status}
                            </span>

                            <div className="doc-actions">
                              <button
                                className="icon-btn icon-btn-danger"
                                onClick={() =>
                                  handleDeleteDocument(
                                    doc.id || doc.document_id,
                                    doc.filename || doc.name
                                  )
                                }
                                title="Delete document and remove embeddings"
                              >
                                <IconTrash size={15} />
                              </button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </section>
              </>
            )}
          </div>
        )}

        {/* =========================================================
            SECTION: AI CHAT
        ========================================================= */}
        {section === "chat" && (
          <section className="chat-panel">
            {!selectedKB ? (
              <div className="empty-state">
                <div className="empty-state-icon">
                  <IconBrain size={32} />
                </div>
                <h2>Select a knowledge base</h2>
                <p>Choose a knowledge base to ground AI answers in your documents.</p>
                <button
                  className="primary-button"
                  onClick={() => setSection("overview")}
                >
                  <IconOverview size={15} /> Go to Overview
                </button>
              </div>
            ) : (
              <>
                {/* Chat Toolbar */}
                <div className="chat-toolbar">
                  <div>
                    <strong>
                      {activeSession?.title || "New conversation"}
                    </strong>
                    <span>
                      Grounded in: <em>{selectedKBObj?.name}</em>
                    </span>
                  </div>

                  <button className="secondary-button" onClick={createChatSession}>
                    <IconPlus size={14} /> New Chat
                  </button>
                </div>

                {/* Messages Thread */}
                <div className="chat-messages">
                  {messages.length === 0 && (
                    <div className="chat-empty">
                      <div className="chat-spark">
                        <IconSparkles size={28} />
                      </div>
                      <h2>Ask anything about your documents</h2>
                      <p>
                        Answers are generated using Groq LLMs and verified against
                        retrieved vectors from Qdrant.
                      </p>

                      <div className="starter-prompts">
                        {STARTER_PROMPTS.map((promptText, i) => (
                          <button
                            key={i}
                            type="button"
                            className="starter-prompt-chip"
                            onClick={() => {
                              setQuestion(promptText);
                            }}
                          >
                            <IconSparkles size={13} />
                            {promptText}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {messages.map((message, index) => (
                    <article
                      key={`${index}-${message.role}`}
                      className={`message ${
                        message.role === "user" ? "user-message" : ""
                      }`}
                    >
                      <div className="message-avatar">
                        {message.role === "user" ? "Y" : "I"}
                      </div>

                      <div className="message-body">
                        <div className="message-header-row">
                          <strong>
                            {message.role === "user" ? "You" : "Inquira AI"}
                          </strong>
                          {message.role === "assistant" && (
                            <button
                              className="copy-btn"
                              onClick={() => copyAnswer(message.content, index)}
                              title="Copy answer"
                            >
                              <IconCopy size={13} />
                              {copiedIndex === index ? "Copied!" : "Copy"}
                            </button>
                          )}
                        </div>

                        <p className="message-text">{message.content}</p>

                        {message.role === "assistant" &&
                          message.supported !== undefined && (
                            <div className="answer-meta">
                              <span
                                className={
                                  message.supported
                                    ? "verified-label"
                                    : "unverified-label"
                                }
                              >
                                {message.supported
                                  ? "✓ Grounded in sources"
                                  : "⚠ Synthesized response"}
                              </span>
                              <span>Retries: {message.retry_count || 0}</span>
                            </div>
                          )}

                        {message.citations?.length > 0 && (
                          <div className="citations">
                            <strong>Sources ({message.citations.length})</strong>
                            <div className="citations-grid">
                              {message.citations.map((citation, i) => (
                                <div
                                  className="citation"
                                  key={citation.chunk_id || i}
                                >
                                  [{citation.id ?? i + 1}]{" "}
                                  {citation.source || "Document"}
                                  {citation.page != null
                                    ? ` · Page ${citation.page}`
                                    : ""}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    </article>
                  ))}

                  {sending && (
                    <div className="progress-indicator">
                      <span className="spinner" />
                      <span>{progress || "Agent is synthesizing answer..."}</span>
                    </div>
                  )}

                  <div ref={bottomRef} />
                </div>

                {/* Composer */}
                <form className="chat-composer" onSubmit={sendMessage}>
                  <textarea
                    value={question}
                    onChange={(event) => setQuestion(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && !event.shiftKey) {
                        event.preventDefault();
                        sendMessage();
                      }
                    }}
                    placeholder={`Ask questions about ${selectedKBObj?.name || "your files"}... (Press Enter to send, Shift+Enter for new line)`}
                    rows={2}
                    disabled={sending}
                  />

                  <div className="composer-footer">
                    <span>
                      Grounded hybrid search · 5-stage agentic verification pipeline
                    </span>

                    <button
                      type="submit"
                      className="primary-button send-button"
                      disabled={sending || !question.trim()}
                    >
                      {sending ? (
                        <span className="spinner" />
                      ) : (
                        <>
                          <IconSend size={15} /> Send
                        </>
                      )}
                    </button>
                  </div>
                </form>
              </>
            )}
          </section>
        )}
      </main>

      {/* Confirmation Modal */}
      <ConfirmModal
        isOpen={confirmModal.isOpen}
        title={confirmModal.title}
        message={confirmModal.message}
        confirmText={confirmModal.confirmText}
        isDanger={confirmModal.isDanger}
        loading={confirmModal.loading}
        onConfirm={confirmModal.onConfirm}
        onCancel={() => setConfirmModal((m) => ({ ...m, isOpen: false }))}
      />
    </div>
  );
}
