// Root layout — Server Component.
// Owns: Google Fonts, page metadata, globals.css import, html/body shell.
// RULES:
//   - NO "use client" here (metadata export requires a Server Component)
//   - NO styled-jsx here (that caused the Phase 3 build error)
//   - All CSS variables live in globals.css, imported below

import type { Metadata } from "next";
import { Space_Mono, Sora } from "next/font/google";
import { Analytics } from "@vercel/analytics/next";
import "./globals.css";

// ─── Fonts ──────────────────────────────────────────────────────────────────
// Space Mono → monospace readouts, bitstrings, code blocks, timestamps
// Sora       → all prose UI text; clean grotesque with excellent legibility
const spaceMono = Space_Mono({
  subsets: ["latin"],
  weight: ["400", "700"],
  variable: "--font-mono",
  display: "swap",
});

const sora = Sora({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
  variable: "--font-sans",
  display: "swap",
});

// ─── Metadata ────────────────────────────────────────────────────────────────
export const metadata: Metadata = {
  title: "Q-Optima | Autonomous Quantum Logistics Agent",
  description:
    "Upload a logistics map. Speak a constraint. Watch a quantum computer solve it. " +
    "Powered by Gemini 2.5 Flash Lite Vision + QAOA on IBM Quantum.",
  openGraph: {
    title: "Q-Optima — Quantum AI Agent",
    description:
      "NP-Hard logistics optimization via autonomous quantum computing. " +
      "Milan AI Week 2026.",
    type: "website",
  },
};

// ─── Root layout ─────────────────────────────────────────────────────────────
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${spaceMono.variable} ${sora.variable}`}
    >
      <body style={{ fontFamily: "var(--font-sans)" }}>
        {children}
        <Analytics />
      </body>
    </html>
  );
}