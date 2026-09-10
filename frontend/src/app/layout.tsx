import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Inquira — Agentic RAG Platform",
  description: "Enterprise Knowledge Base with 5-Technique Hybrid Retrieval and Citation Verification",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="bg-slate-950 text-slate-100 min-h-screen antialiased">
        {children}
      </body>
    </html>
  );
}
