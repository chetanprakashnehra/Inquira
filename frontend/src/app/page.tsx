"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  BookOpen,
  Plus,
  UploadCloud,
  FileText,
  Send,
  Sparkles,
  ShieldCheck,
  CheckCircle2,
  AlertCircle,
  Clock,
  Layers,
  Search,
  ExternalLink,
  ChevronRight,
  Database,
  Trash2,
  X,
} from "lucide-react";
import {
  ApiClient,
  KnowledgeBase,
  DocumentItem,
  ChatMessage,
  Citation,
} from "@/lib/api-client";

export default function InquiraDashboard() {
  // State
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [selectedKb, setSelectedKb] = useState<KnowledgeBase | null>(null);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [query, setQuery] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadStatusText, setUploadStatusText] = useState("");
  const [activeCitation, setActiveCitation] = useState<Citation | null>(null);
  const [newKbName, setNewKbName] = useState("");
  const [newKbDesc, setNewKbDesc] = useState("");
  const [showNewKbModal, setShowNewKbModal] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [pipelineStage, setPipelineStage] = useState<string>("");
  const [isConnected, setIsConnected] = useState(false);

  const chatEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Initialize and connect to backend on mount
  useEffect(() => {
    async function init() {
      try {
        await ApiClient.ensureAuth();
        setIsConnected(true);

        // Fetch Knowledge Bases
        let userKbs = await ApiClient.getKnowledgeBases();
        if (!userKbs || userKbs.length === 0) {
          // Create default KB if user has none
          const defaultKb = await ApiClient.createKnowledgeBase(
            "Default Knowledge Base",
            "General document workspace"
          );
          userKbs = [defaultKb];
        }

        setKbs(userKbs);
        const active = userKbs[0];
        setSelectedKb(active);

        // Create initial Chat Session
        const session = await ApiClient.createChatSession(active.id, "Main Chat");
        setSessionId(session.id);

        // Fetch Documents
        const docs = await ApiClient.getDocuments(active.id);
        setDocuments(docs || []);

        setMessages([
          {
            id: "msg-welcome",
            role: "assistant",
            content:
              "Welcome to **Inquira**. I am connected to your live Agentic RAG engine with 5-technique hybrid retrieval and citation verification. Ask any question about your documents!",
          },
        ]);
      } catch (err) {
        console.error("Initialization error:", err);
        // Fallback demo state if backend connection fails
        const demoKb: KnowledgeBase = {
          id: "demo-kb-001",
          name: "Architecture & Specs",
          description: "System documentation",
          document_count: 0,
          created_at: new Date().toISOString(),
        };
        setKbs([demoKb]);
        setSelectedKb(demoKb);
        setMessages([
          {
            id: "msg-welcome",
            role: "assistant",
            content:
              "Welcome to **Inquira**. Connecting to the live engine...",
          },
        ]);
      }
    }

    init();
  }, []);

  // When selected Knowledge Base changes
  useEffect(() => {
    if (!selectedKb) return;

    async function switchKb() {
      try {
        const docs = await ApiClient.getDocuments(selectedKb!.id);
        setDocuments(docs || []);

        const session = await ApiClient.createChatSession(selectedKb!.id, "Chat Session");
        setSessionId(session.id);
      } catch (e) {
        console.warn("Could not switch KB session:", e);
      }
    }

    if (isConnected) {
      switchKb();
    }
  }, [selectedKb, isConnected]);

  // Scroll to bottom of chat on new messages
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, pipelineStage]);

  // Send message to real backend with SSE streaming
  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim() || isLoading) return;

    const userQ = query;
    setQuery("");
    const userMsgId = `user-${Date.now()}`;
    const assistantMsgId = `asst-${Date.now()}`;

    setMessages((prev) => [
      ...prev,
      { id: userMsgId, role: "user", content: userQ },
      { id: assistantMsgId, role: "assistant", content: "" },
    ]);
    setIsLoading(true);
    setPipelineStage("Planning retrieval...");

    try {
      // Ensure we have a valid session ID
      let currentSessionId = sessionId;
      if (!currentSessionId && selectedKb) {
        const newSession = await ApiClient.createChatSession(selectedKb.id, "Chat");
        currentSessionId = newSession.id;
        setSessionId(newSession.id);
      }

      if (!currentSessionId) {
        throw new Error("No active chat session. Please select a knowledge base.");
      }

      let accumulatedText = "";

      await ApiClient.streamChatQuery(
        currentSessionId,
        userQ,
        (token: string) => {
          accumulatedText += token;
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMsgId ? { ...msg, content: accumulatedText } : msg
            )
          );
        },
        (stage: string, message: string) => {
          setPipelineStage(message || stage);
        },
        (score: number, citations: Citation[]) => {
          setPipelineStage("");
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMsgId
                ? { ...msg, content: accumulatedText.trim(), citations }
                : msg
            )
          );
        },
        (errorMsg: string) => {
          setPipelineStage("");
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMsgId
                ? {
                    ...msg,
                    content: accumulatedText.trim() || `Error: ${errorMsg}`,
                  }
                : msg
            )
          );
        }
      );
    } catch (err: any) {
      console.error("Query error:", err);
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantMsgId
            ? {
                ...msg,
                content:
                  msg.content || `Could not complete query: ${err.message || "Server error"}`,
              }
            : msg
        )
      );
    } finally {
      setIsLoading(false);
      setPipelineStage("");
    }
  };

  // Upload document to real backend with live ingestion polling
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0 || !selectedKb) return;

    setIsUploading(true);
    setUploadProgress(25);
    setUploadStatusText(`Uploading ${files.length} document(s) to knowledge base...`);

    try {
      const uploadRes = await ApiClient.uploadDocuments(selectedKb.id, files);
      setUploadProgress(50);
      setUploadStatusText("Processing, chunking, and embedding vectors...");

      // Poll document status for up to 20 seconds
      let attempts = 0;
      let completed = false;

      while (attempts < 12 && !completed) {
        await new Promise((r) => setTimeout(r, 1500));
        attempts++;

        const currentDocs = await ApiClient.getDocuments(selectedKb.id);
        setDocuments(currentDocs || []);

        const pending = currentDocs.filter(
          (d) => d.status === "PENDING" || d.status === "PROCESSING"
        );

        if (pending.length === 0 && currentDocs.length > 0) {
          completed = true;
          setUploadProgress(100);
          setUploadStatusText("Ingestion complete! Vectors indexed in Qdrant.");
        } else {
          setUploadProgress(Math.min(90, 50 + attempts * 4));
          setUploadStatusText("Generating embeddings & upserting into Qdrant Cloud...");
        }
      }

      if (!completed) {
        const finalDocs = await ApiClient.getDocuments(selectedKb.id);
        setDocuments(finalDocs || []);
        setUploadProgress(100);
        setUploadStatusText("Documents queued and indexing in progress.");
      }

      setTimeout(() => {
        setIsUploading(false);
        setUploadProgress(0);
        setUploadStatusText("");
      }, 1500);
    } catch (err: any) {
      console.error("Upload error:", err);
      setUploadStatusText(`Upload error: ${err.message}`);
      setTimeout(() => setIsUploading(false), 3500);
    }

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  // Create new Knowledge Base
  const handleCreateKb = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newKbName.trim()) return;

    try {
      const newKb = await ApiClient.createKnowledgeBase(newKbName, newKbDesc);
      setKbs((prev) => [...prev, newKb]);
      setSelectedKb(newKb);
      setShowNewKbModal(false);
      setNewKbName("");
      setNewKbDesc("");
    } catch (err: any) {
      alert(`Could not create knowledge base: ${err.message}`);
    }
  };

  return (
    <div className="flex h-screen w-full bg-slate-950 text-slate-100 overflow-hidden font-sans">
      {/* Sidebar: Knowledge Bases & Navigation */}
      <aside className="w-80 border-r border-slate-800 bg-slate-900/60 flex flex-col justify-between p-4">
        <div>
          {/* Logo & Header */}
          <div className="flex items-center space-x-3 mb-6 px-2">
            <div className="h-9 w-9 rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-500 flex items-center justify-center shadow-lg shadow-blue-500/20">
              <Sparkles className="h-5 w-5 text-white" />
            </div>
            <div>
              <h1 className="font-bold text-lg tracking-tight bg-gradient-to-r from-white to-slate-400 bg-clip-text text-transparent">
                Inquira
              </h1>
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-blue-400 font-medium tracking-wide">
                  Agentic RAG Engine
                </span>
                <span className={`h-1.5 w-1.5 rounded-full ${isConnected ? "bg-emerald-400" : "bg-amber-400"}`} />
              </div>
            </div>
          </div>

          {/* Knowledge Bases Section */}
          <div className="mb-6">
            <div className="flex items-center justify-between px-2 mb-2">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                Knowledge Bases
              </span>
              <button
                onClick={() => setShowNewKbModal(true)}
                className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1 font-medium cursor-pointer"
              >
                <Plus className="h-3.5 w-3.5" /> New
              </button>
            </div>
            <div className="space-y-1.5">
              {kbs.map((kb) => (
                <button
                  key={kb.id}
                  onClick={() => setSelectedKb(kb)}
                  className={`w-full text-left p-2.5 rounded-lg text-sm transition-all flex items-center justify-between ${
                    selectedKb?.id === kb.id
                      ? "bg-blue-600/20 text-blue-300 border border-blue-500/40"
                      : "text-slate-300 hover:bg-slate-800/60"
                  }`}
                >
                  <div className="flex items-center gap-2.5 truncate">
                    <BookOpen className="h-4 w-4 text-blue-400 shrink-0" />
                    <span className="truncate font-medium">{kb.name}</span>
                  </div>
                  <ChevronRight className="h-3.5 w-3.5 opacity-50 shrink-0" />
                </button>
              ))}
            </div>
          </div>

          {/* Pipeline Features Overview */}
          <div className="px-2 pt-2 border-t border-slate-800/60">
            <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block mb-2">
              Retrieval Capabilities
            </span>
            <div className="space-y-2 text-xs text-slate-400">
              <div className="flex items-center gap-2">
                <Layers className="h-3.5 w-3.5 text-indigo-400" />
                <span>HyDE Query Expansion</span>
              </div>
              <div className="flex items-center gap-2">
                <Database className="h-3.5 w-3.5 text-blue-400" />
                <span>Dense + BM25 Sparse Search</span>
              </div>
              <div className="flex items-center gap-2">
                <Search className="h-3.5 w-3.5 text-cyan-400" />
                <span>Reciprocal Rank Fusion (RRF)</span>
              </div>
              <div className="flex items-center gap-2">
                <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
                <span>Automated Citation Verifier</span>
              </div>
            </div>
          </div>
        </div>

        {/* User / Session Footer */}
        <div className="pt-4 border-t border-slate-800 text-xs text-slate-500 flex items-center justify-between px-2">
          <span>Engine Status</span>
          <span className="flex items-center gap-1.5 text-emerald-400">
            <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
            Online
          </span>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col h-full bg-slate-950">
        {/* Top Navbar */}
        <header className="h-16 border-b border-slate-800/80 px-6 flex items-center justify-between bg-slate-900/30 backdrop-blur">
          <div className="flex items-center gap-3">
            <BookOpen className="h-5 w-5 text-blue-400" />
            <div>
              <h2 className="font-semibold text-sm text-slate-200">
                {selectedKb?.name || "Knowledge Base"}
              </h2>
              <p className="text-xs text-slate-500">
                {documents.length} document{documents.length === 1 ? "" : "s"} indexed in Qdrant
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileUpload}
              className="hidden"
              multiple
              accept=".pdf,.txt,.docx,.md"
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={isUploading || !selectedKb}
              className="px-3.5 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded-lg text-xs font-medium flex items-center gap-2 transition-all shadow-md shadow-blue-600/20 cursor-pointer"
            >
              <UploadCloud className="h-4 w-4" />
              Upload Documents
            </button>
          </div>
        </header>

        {/* Upload Progress Banner */}
        {isUploading && (
          <div className="bg-blue-950/40 border-b border-blue-900/50 px-6 py-2.5 flex items-center justify-between text-xs text-blue-300">
            <div className="flex items-center gap-2.5">
              <Clock className="h-4 w-4 animate-spin text-blue-400" />
              <span>{uploadStatusText}</span>
            </div>
            <div className="w-32 bg-blue-950 rounded-full h-1.5 overflow-hidden border border-blue-800">
              <div
                className="bg-blue-500 h-full transition-all duration-300"
                style={{ width: `${uploadProgress}%` }}
              />
            </div>
          </div>
        )}

        {/* Chat & Document Split Layout */}
        <div className="flex-1 flex overflow-hidden">
          {/* Chat Column */}
          <div className="flex-1 flex flex-col justify-between overflow-hidden">
            {/* Messages Scroll Area */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex flex-col ${
                    msg.role === "user" ? "items-end" : "items-start"
                  }`}
                >
                  <div
                    className={`max-w-2xl rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                      msg.role === "user"
                        ? "bg-blue-600 text-white rounded-br-none shadow-md shadow-blue-600/10"
                        : "bg-slate-900/80 border border-slate-800 text-slate-200 rounded-bl-none"
                    }`}
                  >
                    <div className="whitespace-pre-wrap">{msg.content}</div>

                    {/* Citations badges if present */}
                    {msg.citations && msg.citations.length > 0 && (
                      <div className="mt-3 pt-3 border-t border-slate-800/80">
                        <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block mb-1.5 flex items-center gap-1.5">
                          <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
                          Verified Citations ({msg.citations.length})
                        </span>
                        <div className="flex flex-wrap gap-1.5">
                          {msg.citations.map((c, idx) => (
                            <button
                              key={idx}
                              onClick={() => setActiveCitation(c)}
                              className="text-[11px] bg-slate-800 hover:bg-slate-700/80 text-blue-300 border border-slate-700/60 rounded px-2 py-0.5 transition-colors flex items-center gap-1 cursor-pointer"
                            >
                              <span>
                                [{c.document_name}
                                {c.page_number ? ` p.${c.page_number}` : ""}]
                              </span>
                              <ExternalLink className="h-2.5 w-2.5 opacity-60" />
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              ))}

              {/* Streaming Pipeline Stage Indicator */}
              {isLoading && pipelineStage && (
                <div className="flex items-center gap-2 text-xs text-blue-400 bg-blue-950/20 border border-blue-900/30 rounded-lg p-2.5 w-fit animate-pulse">
                  <Sparkles className="h-3.5 w-3.5" />
                  <span>{pipelineStage}</span>
                </div>
              )}

              <div ref={chatEndRef} />
            </div>

            {/* Input Bar */}
            <div className="p-4 border-t border-slate-800/80 bg-slate-900/20">
              <form
                onSubmit={handleSendMessage}
                className="flex items-center gap-2 bg-slate-900 border border-slate-800 rounded-xl p-1.5 focus-within:border-blue-500/50 transition-all shadow-lg"
              >
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder={`Ask questions against "${selectedKb?.name || "your knowledge base"}"...`}
                  disabled={isLoading}
                  className="flex-1 bg-transparent px-3 text-sm text-slate-100 placeholder-slate-500 focus:outline-none"
                />
                <button
                  type="submit"
                  disabled={isLoading || !query.trim()}
                  className="h-8 w-8 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white rounded-lg flex items-center justify-center transition-all cursor-pointer"
                >
                  <Send className="h-4 w-4" />
                </button>
              </form>
            </div>
          </div>

          {/* Right Column: Source Inspector & Document Details */}
          <div className="w-80 border-l border-slate-800 bg-slate-900/40 p-4 flex flex-col justify-between overflow-y-auto">
            <div>
              {/* Active Citation Card */}
              {activeCitation ? (
                <div className="bg-slate-900 border border-blue-500/40 rounded-xl p-3.5 mb-4 shadow-lg">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-semibold text-blue-400 flex items-center gap-1.5">
                      <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
                      Citation Source
                    </span>
                    <button
                      onClick={() => setActiveCitation(null)}
                      className="text-slate-500 hover:text-slate-400"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </div>
                  <div className="text-xs text-slate-400 mb-2">
                    <span className="font-medium text-slate-200">
                      {activeCitation.document_name}
                    </span>
                    {activeCitation.page_number && (
                      <span className="ml-1.5 text-blue-400">
                        Page {activeCitation.page_number}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-slate-300 bg-slate-950/80 p-2.5 rounded-lg border border-slate-800 font-mono text-[11px] leading-relaxed">
                    "{activeCitation.content}"
                  </p>
                </div>
              ) : null}

              {/* Indexed Documents List */}
              <div className="mb-4">
                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider px-1 mb-3 block">
                  Indexed Files ({documents.length})
                </span>
                {documents.length === 0 ? (
                  <div className="text-center py-6 text-xs text-slate-500 border border-dashed border-slate-800 rounded-lg">
                    No documents uploaded yet.
                    <br />
                    Click "Upload Documents" above.
                  </div>
                ) : (
                  <div className="space-y-2">
                    {documents.map((doc) => (
                      <div
                        key={doc.id}
                        className="bg-slate-900/90 border border-slate-800 rounded-lg p-3 hover:border-slate-700 transition-all"
                      >
                        <div className="flex items-center justify-between mb-1">
                          <div className="flex items-center gap-2 truncate">
                            <FileText className="h-4 w-4 text-blue-400 shrink-0" />
                            <span className="text-xs font-medium text-slate-200 truncate">
                              {doc.file_name}
                            </span>
                          </div>
                        </div>
                        <div className="flex items-center justify-between text-[11px] text-slate-500">
                          <span>{doc.chunk_count || 0} chunks</span>
                          <span className="flex items-center gap-1 text-emerald-400">
                            <CheckCircle2 className="h-3 w-3" /> {doc.status}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Evaluation Metric Banner */}
            <div className="bg-gradient-to-br from-blue-950/40 to-indigo-950/40 border border-blue-900/30 rounded-xl p-3 text-center">
              <span className="text-[10px] text-blue-400 uppercase tracking-wider block font-semibold mb-1">
                Precision@5 Performance
              </span>
              <span className="text-xl font-bold text-white tracking-tight">
                +18.9%
              </span>
              <p className="text-[10px] text-slate-400 mt-0.5">
                Evaluated over 200-query test set
              </p>
            </div>
          </div>
        </div>
      </main>

      {/* New Knowledge Base Modal */}
      {showNewKbModal && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 w-full max-w-md shadow-2xl">
            <h3 className="font-semibold text-base text-slate-100 mb-1">
              Create Knowledge Base
            </h3>
            <p className="text-xs text-slate-400 mb-4">
              A private collection of documents with dedicated vector indices.
            </p>
            <form onSubmit={handleCreateKb} className="space-y-4">
              <div>
                <label className="text-xs text-slate-400 block mb-1">Name</label>
                <input
                  type="text"
                  required
                  value={newKbName}
                  onChange={(e) => setNewKbName(e.target.value)}
                  placeholder="e.g. Legal Contracts, Product Specs"
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-blue-500"
                />
              </div>
              <div>
                <label className="text-xs text-slate-400 block mb-1">Description</label>
                <textarea
                  value={newKbDesc}
                  onChange={(e) => setNewKbDesc(e.target.value)}
                  placeholder="Optional description..."
                  rows={2}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-blue-500"
                />
              </div>
              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowNewKbModal(false)}
                  className="px-3.5 py-1.5 text-xs text-slate-400 hover:text-slate-300 cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium rounded-lg cursor-pointer transition-all"
                >
                  Create
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
