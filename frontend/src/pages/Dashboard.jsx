
import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "../auth/AuthContext";

const API =
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

async function request(path, options = {}) {
  const token = localStorage.getItem("access_token");

  const headers = { ...options.headers };

  if (token) headers.Authorization = `Bearer ${token}`;

  if (options.body instanceof FormData) {
    // Browser sets the multipart boundary.
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

function Dashboard() {
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
  const [file, setFile] = useState(null);
  const [question, setQuestion] = useState("");

  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [progress, setProgress] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const bottomRef = useRef(null);

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

    const data = await request(
      `/knowledge-bases/${kbId}/documents`
    );

    setDocuments(asList(data, ["documents", "items"]));
  }, []);

  const loadMessages = useCallback(async (sessionId) => {
    const data = await request(
      `/sessions/${sessionId}/messages`
    );

    setMessages(asList(data, ["messages", "items"]));
  }, []);

  useEffect(() => {
    async function initialize() {
      setLoading(true);
      setError("");

      try {
        await Promise.all([
          loadKnowledgeBases(),
          loadSessions(),
        ]);
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

    if (
      !activeSession ||
      activeSession.knowledge_base_id !== selectedKB
    ) {
      setActiveSession(null);
      setMessages([]);

      if (existingSession) {
        setActiveSession(existingSession);
        loadMessages(existingSession.id).catch(
          (err) => setError(err.message)
        );
      }
    }
  }, [
    selectedKB,
    sessions,
    activeSession,
    loadDocuments,
    loadMessages,
  ]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, progress]);

  // Poll document status while ingestion is in progress.
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

            const status = await request(
              `/knowledge-bases/documents/${id}/status`
            );

            return { ...doc, ...status };
          })
        );

        setDocuments((current) =>
          current.map((doc) => {
            const id = doc.id || doc.document_id;

            return updated.find(
              (item) => (item.id || item.document_id) === id
            ) || doc;
          })
        );
      } catch (err) {
        console.error("Document status check failed:", err);
      }
    }, 3000);

    return () => clearInterval(timer);
  }, [documents]);

  async function createKnowledgeBase(event) {
    event.preventDefault();
    setError("");
    setNotice("");

    try {
      const params = new URLSearchParams({
        name: kbName,
      });

      if (kbDescription.trim()) {
        params.set("description", kbDescription.trim());
      }

      await request(`/knowledge-bases?${params.toString()}`, {
        method: "POST",
      });

      setKbName("");
      setKbDescription("");
      await loadKnowledgeBases();
      setNotice("Knowledge base created.");
      setSection("documents");
    } catch (err) {
      setError(err.message);
    }
  }

  async function uploadDocument(event) {
    event.preventDefault();

    if (!selectedKB || !file) {
      setError("Select a knowledge base and a file first.");
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
      event.target.reset();

      await loadDocuments(selectedKB);
      setNotice(
        `Upload submitted: ${result.filename || result.message || "document received"}`
      );
    } catch (err) {
      setError(err.message);
    }
  }

  async function createChatSession() {
    if (!selectedKB) {
      setError("Create or select a knowledge base first.");
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

  async function sendMessage(event) {
    event.preventDefault();

    const text = question.trim();

    if (!text || sending) return;

    if (!selectedKB) {
      setError("Select a knowledge base first.");
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
        throw new Error("Streaming is not supported by this response.");
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
                supported:
                  event.supported ?? event.is_supported ?? false,
                retry_count: event.retry_count ?? 0,
              },
            ]);

            setProgress(
              event.supported ?? event.is_supported
                ? "Answer verified"
                : "Answer generated; verification was unsuccessful"
            );

            finished = true;
          }

          if (event.type === "error") {
            throw new Error(event.message || "Agent failed");
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
    } finally {
      setSending(false);
      setProgress("");
    }
  }

  const currentSessions = sessions.filter(
    (session) => session.knowledge_base_id === selectedKB
  );

  return (
    <div className="workspace">
      <aside className="sidebar">
        <a className="brand" href="/">
          <span className="brand-icon">I</span>
          Inquira
        </a>

        <p className="sidebar-label">WORKSPACE</p>

        <button
          className={`nav-item ${section === "overview" ? "active" : ""}`}
          onClick={() => setSection("overview")}
        >
          ◫ Overview
        </button>

        <button
          className={`nav-item ${section === "documents" ? "active" : ""}`}
          onClick={() => setSection("documents")}
        >
          ▤ Documents
        </button>

        <button
          className={`nav-item ${section === "chat" ? "active" : ""}`}
          onClick={() => setSection("chat")}
        >
          ◉ AI Chat
        </button>

        <div className="sidebar-section">
          <p className="sidebar-label">KNOWLEDGE BASE</p>

          <select
            className="kb-select"
            value={selectedKB}
            onChange={(event) => setSelectedKB(event.target.value)}
          >
            <option value="">Select a knowledge base</option>
            {knowledgeBases.map((kb) => (
              <option key={kb.id} value={kb.id}>
                {kb.name}
              </option>
            ))}
          </select>

          <button
            className="nav-item"
            onClick={() => setSection("create-kb")}
          >
            + New knowledge base
          </button>
        </div>

        <div className="sidebar-section">
          <p className="sidebar-label">RECENT CHATS</p>

          {currentSessions.map((session) => (
            <button
              key={session.id}
              className={`nav-item session-link ${
                activeSession?.id === session.id ? "active" : ""
              }`}
              onClick={() => openSession(session)}
              title={session.title || "Chat"}
            >
              ◌ {(session.title || "New chat").slice(0, 24)}
            </button>
          ))}

          {selectedKB && (
            <button className="nav-item" onClick={createChatSession}>
              + New chat
            </button>
          )}
        </div>

        <div className="sidebar-user">
          <div className="avatar">
            {(user?.full_name || user?.email || "U")
              .charAt(0)
              .toUpperCase()}
          </div>

          <div className="user-info">
            <strong>{user?.full_name || "User"}</strong>
            <span>{user?.email}</span>
          </div>

          <button
            className="logout-button"
            onClick={logout}
            title="Log out"
          >
            ↗
          </button>
        </div>
      </aside>

      <main className="workspace-main">
        <header className="workspace-header">
          <div>
            <p className="eyebrow">AGENTIC RAG PLATFORM</p>
            <h1>
              {section === "overview" && "Your workspace"}
              {section === "create-kb" && "Create knowledge base"}
              {section === "documents" && "Documents"}
              {section === "chat" && "AI assistant"}
            </h1>
          </div>

          {selectedKB && (
            <span className="workspace-badge">
              {knowledgeBases.find((kb) => kb.id === selectedKB)?.name}
            </span>
          )}
        </header>

        {error && (
          <div className="alert error-alert">
            {error}
            <button onClick={() => setError("")}>×</button>
          </div>
        )}

        {notice && (
          <div className="alert success-alert">
            {notice}
            <button onClick={() => setNotice("")}>×</button>
          </div>
        )}

        {loading && (
          <p className="muted">Loading your workspace...</p>
        )}

        {!loading && section === "overview" && (
          <>
            <section className="welcome-panel">
              <p className="eyebrow">WELCOME TO INQUIRA</p>
              <h2>Your documents, understood.</h2>
              <p>
                Create a knowledge base, upload documents, and ask your
                AI assistant questions grounded in your files.
              </p>

              <button
                className="primary-button"
                onClick={() =>
                  setSection(
                    knowledgeBases.length ? "documents" : "create-kb"
                  )
                }
              >
                {knowledgeBases.length
                  ? "Manage documents"
                  : "Create your first knowledge base"}
              </button>
            </section>

            <section className="stats-grid">
              <div className="stat-card">
                <span>Knowledge bases</span>
                <strong>{knowledgeBases.length}</strong>
              </div>

              <div className="stat-card">
                <span>Documents</span>
                <strong>{documents.length}</strong>
              </div>

              <div className="stat-card">
                <span>Chat sessions</span>
                <strong>{currentSessions.length}</strong>
              </div>
            </section>

            <section className="panel">
              <div className="panel-heading">
                <div>
                  <h2>Get started</h2>
                  <p>Set up your personal AI knowledge workspace.</p>
                </div>
              </div>

              <div className="quick-actions">
                <button
                  className="quick-action"
                  onClick={() => setSection("create-kb")}
                >
                  <span>＋</span>
                  <strong>Create knowledge base</strong>
                  <small>Organize documents by topic</small>
                </button>

                <button
                  className="quick-action"
                  onClick={() => setSection("documents")}
                >
                  <span>↑</span>
                  <strong>Upload documents</strong>
                  <small>Make files searchable</small>
                </button>

                <button
                  className="quick-action"
                  onClick={() => setSection("chat")}
                >
                  <span>✳</span>
                  <strong>Ask a question</strong>
                  <small>Chat with your documents</small>
                </button>
              </div>
            </section>
          </>
        )}

        {section === "create-kb" && (
          <section className="panel form-panel">
            <h2>New knowledge base</h2>
            <p className="muted">
              Create a collection of documents for your AI assistant.
            </p>

            <form onSubmit={createKnowledgeBase} className="stack-form">
              <label htmlFor="kb-name">Name</label>
              <input
                id="kb-name"
                value={kbName}
                onChange={(event) => setKbName(event.target.value)}
                placeholder="e.g. Research papers"
                required
              />

              <label htmlFor="kb-description">Description</label>
              <textarea
                id="kb-description"
                value={kbDescription}
                onChange={(event) =>
                  setKbDescription(event.target.value)
                }
                placeholder="What is this knowledge base about?"
                rows={4}
              />

              <button className="primary-button">
                Create knowledge base
              </button>
            </form>
          </section>
        )}

        {section === "documents" && (
          <div className="content-stack">
            {!selectedKB ? (
              <section className="empty-state">
                <h2>No knowledge base selected</h2>
                <p>Create a knowledge base before uploading documents.</p>
                <button
                  className="primary-button"
                  onClick={() => setSection("create-kb")}
                >
                  Create knowledge base
                </button>
              </section>
            ) : (
              <>
                <section className="panel">
                  <div className="panel-heading">
                    <div>
                      <h2>Upload a document</h2>
                      <p>
                        Add a file to{" "}
                        {knowledgeBases.find((kb) => kb.id === selectedKB)?.name}.
                      </p>
                    </div>
                  </div>

                  <form
                    className="upload-form"
                    onSubmit={uploadDocument}
                  >
                    <input
                      type="file"
                      accept=".pdf,.docx,.txt,.json"
                      onChange={(event) =>
                        setFile(event.target.files?.[0] || null)
                      }
                      required
                    />

                    <button
                      className="primary-button"
                      disabled={!file}
                    >
                      Upload file
                    </button>
                  </form>

                  <p className="muted upload-hint">
                    Supported formats depend on your backend document loader.
                  </p>
                </section>

                <section className="panel">
                  <div className="panel-heading">
                    <div>
                      <h2>Your documents</h2>
                      <p>
                        Processing happens in the background. Status refreshes
                        automatically for pending documents.
                      </p>
                    </div>

                    <button
                      className="secondary-button"
                      onClick={() => loadDocuments(selectedKB)}
                    >
                      Refresh
                    </button>
                  </div>

                  {documents.length === 0 ? (
                    <div className="empty-inline">
                      No documents uploaded yet.
                    </div>
                  ) : (
                    <div className="document-list">
                      {documents.map((doc, index) => {
                        const id = doc.id || doc.document_id || index;
                        const status = String(
                          doc.status || "unknown"
                        ).toLowerCase();

                        return (
                          <div className="document-row" key={id}>
                            <div className="file-icon">PDF</div>

                            <div className="document-info">
                              <strong>
                                {doc.filename || doc.name || "Document"}
                              </strong>
                              <span>
                                {doc.chunk_count != null
                                  ? `${doc.chunk_count} chunks`
                                  : "Document"}
                                {doc.error_message
                                  ? ` · ${doc.error_message}`
                                  : ""}
                              </span>
                            </div>

                            <span
                              className={`status-pill status-${status}`}
                            >
                              {status}
                            </span>
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

        {section === "chat" && (
          <section className="chat-panel">
            {!selectedKB ? (
              <div className="empty-state">
                <h2>Select a knowledge base</h2>
                <p>Create or select a knowledge base before chatting.</p>
                <button
                  className="primary-button"
                  onClick={() => setSection("create-kb")}
                >
                  Create knowledge base
                </button>
              </div>
            ) : (
              <>
                <div className="chat-toolbar">
                  <div>
                    <strong>
                      {activeSession?.title || "New conversation"}
                    </strong>
                    <span>
                      Answers are generated from your selected knowledge base.
                    </span>
                  </div>

                  <button
                    className="secondary-button"
                    onClick={createChatSession}
                  >
                    + New chat
                  </button>
                </div>

                <div className="chat-messages">
                  {messages.length === 0 && (
                    <div className="chat-empty">
                      <div className="chat-spark">✳</div>
                      <h2>Ask your documents anything</h2>
                      <p>
                        Start with a question about information in your files.
                      </p>
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
                        <strong>
                          {message.role === "user" ? "You" : "Inquira"}
                        </strong>

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
                                  ? "✓ Verified"
                                  : "⚠ Not verified"}
                              </span>

                              <span>
                                Retries: {message.retry_count || 0}
                              </span>
                            </div>
                          )}

                        {message.citations?.length > 0 && (
                          <div className="citations">
                            <strong>Sources</strong>

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
                        )}
                      </div>
                    </article>
                  ))}

                  {sending && (
                    <div className="progress-indicator">
                      <span className="spinner" />
                      <span>{progress || "Agent is working..."}</span>
                    </div>
                  )}

                  <div ref={bottomRef} />
                </div>

                <form className="chat-composer" onSubmit={sendMessage}>
                  <textarea
                    value={question}
                    onChange={(event) => setQuestion(event.target.value)}
                    onKeyDown={(event) => {
                      if (
                        event.key === "Enter" &&
                        !event.shiftKey &&
                        !event.nativeEvent.isComposing
                      ) {
                        event.preventDefault();
                        event.currentTarget.form?.requestSubmit();
                      }
                    }}
                    placeholder="Ask a question about your documents..."
                    rows={2}
                    disabled={sending}
                  />

                  <div className="composer-footer">
                    <span>Enter to send · Shift+Enter for a new line</span>
                    <button
                      className="primary-button send-button"
                      disabled={sending || !question.trim()}
                    >
                      {sending ? "Working..." : "Send ↑"}
                    </button>
                  </div>
                </form>
              </>
            )}
          </section>
        )}
      </main>
    </div>
  );
}

export default Dashboard;
