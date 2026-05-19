"use client";
// components/QuantumCommandCenter.tsx
// The main Q-Optima enterprise dashboard.
//
// Layout (3-column on wide screens, stacked on mobile):
//   LEFT  — Upload zone (image + audio) + Run button
//   CENTER — Agent reasoning timeline (live polling)
//   RIGHT  — Quantum result card
//
// Polling: after POST /api/solve, polls GET /api/status/{id} every 2000 ms.
// Stops when status === "complete" | "error".

import React, { useState, useCallback, useRef, useEffect } from "react";
import { useDropzone } from "react-dropzone";
import { motion, AnimatePresence } from "framer-motion";
import {
  ImageIcon, Mic2, Zap, X, RotateCcw,
  MapPin, Navigation, Activity, AlertTriangle,
  ExternalLink, Copy, CheckCheck, ChevronDown,
} from "lucide-react";
import AgentTimeline, { StepLog } from "./AgentTimeline";

// ─── Config ─────────────────────────────────────────────────────────────────

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

const POLL_INTERVAL_MS = 2000; // Updated to 2000 to reduce render load

// ─── Types ──────────────────────────────────────────────────────────────────

interface SolutionCandidate {
  bitstring: string;
  route: string[];
  distance: number;
  probability: number;
}

interface QuantumResult {
  problem_description: string;
  problem_type: string;
  city_names: string[];
  quantum_backend: string;
  num_qubits: number;
  circuit_depth: number;
  qaoa_layers: number;
  total_shots: number;
  best_bitstring: string;
  optimal_route: string[];
  route_distance: number;
  human_readable_result: string;
  top_solutions: SolutionCandidate[];
  circuit_code_display: string;
}

interface StatusResponse {
  job_id: string;
  status: "queued" | "running" | "complete" | "error";
  current_step: string;
  progress_percent: number;
  step_logs: StepLog[];
  result?: QuantumResult;
  error_message?: string;
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function formatBytes(b: number) {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / (1024 * 1024)).toFixed(1)} MB`;
}

// ─── Upload Drop Zone ────────────────────────────────────────────────────────

function UploadZone({
  accept,
  label,
  sublabel,
  icon: Icon,
  color,
  file,
  onDrop,
  onRemove,
}: {
  accept: Record<string, string[]>;
  label: string;
  sublabel: string;
  icon: React.ElementType;
  color: string;
  file: File | null;
  onDrop: (f: File) => void;
  onRemove: () => void;
}) {
  const handleDrop = useCallback(
    (accepted: File[]) => {
      if (accepted[0]) onDrop(accepted[0]);
    },
    [onDrop]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop: handleDrop,
    accept,
    maxFiles: 1,
    multiple: false,
  });

  return (
    <motion.div
      animate={{
        borderColor: isDragActive
          ? color
          : file
          ? color + "66"
          : "#232a3a",
        background: isDragActive
          ? color + "08"
          : file
          ? color + "06"
          : "#0a0c10",
        boxShadow: isDragActive ? `0 0 24px ${color}33` : "none",
      }}
      transition={{ duration: 0.2 }}
      style={{
        border: "1.5px dashed",
        borderRadius: 10,
        cursor: "pointer",
        position: "relative",
        overflow: "hidden",
      }}
    >
      {/* Radar ring animation when active */}
      <AnimatePresence>
        {isDragActive && (
          <motion.div
            initial={{ scale: 0, opacity: 0.4 }}
            animate={{ scale: 2, opacity: 0 }}
            exit={{ opacity: 0 }}
            transition={{ repeat: Infinity, duration: 1.2 }}
            style={{
              position: "absolute",
              top: "50%",
              left: "50%",
              transform: "translate(-50%,-50%)",
              width: 60,
              height: 60,
              borderRadius: "50%",
              background: color,
              pointerEvents: "none",
            }}
          />
        )}
      </AnimatePresence>

      <div {...getRootProps()} style={{ padding: "16px 14px" }}>
        <input {...getInputProps()} />
        {file ? (
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div
              style={{
                width: 36,
                height: 36,
                borderRadius: 8,
                background: color + "22",
                border: `1px solid ${color}44`,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
              }}
            >
              <Icon size={16} color={color} />
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div
                style={{
                  fontSize: 12,
                  fontWeight: 600,
                  color: "#e8eaf0",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {file.name}
              </div>
              <div
                style={{
                  fontSize: 10,
                  color: "#6b7591",
                  fontFamily: "var(--font-mono)",
                }}
              >
                {formatBytes(file.size)}
              </div>
            </div>
            <button
              onClick={(e) => {
                e.stopPropagation();
                onRemove();
              }}
              style={{
                background: "none",
                border: "none",
                cursor: "pointer",
                color: "#6b7591",
                padding: 4,
                borderRadius: 4,
                display: "flex",
                alignItems: "center",
              }}
            >
              <X size={14} />
            </button>
          </div>
        ) : (
          <div style={{ textAlign: "center", padding: "8px 0" }}>
            <div
              style={{
                margin: "0 auto 8px",
                width: 36,
                height: 36,
                borderRadius: 8,
                background: "#141820",
                border: "1px solid #1a1f2e",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <Icon size={16} color="#3d4560" />
            </div>
            <div style={{ fontSize: 12, fontWeight: 600, color: "#6b7591", marginBottom: 2 }}>
              {label}
            </div>
            <div style={{ fontSize: 10, color: "#3d4560" }}>{sublabel}</div>
          </div>
        )}
      </div>
    </motion.div>
  );
}

// ─── Metric chip ─────────────────────────────────────────────────────────────

function Metric({
  label,
  value,
  color = "#6b7591",
}: {
  label: string;
  value: string | number;
  color?: string;
}) {
  return (
    <div
      style={{
        padding: "8px 12px",
        background: "#050608",
        border: "1px solid #1a1f2e",
        borderRadius: 8,
        flex: "1 1 0",
        minWidth: 0,
      }}
    >
      <div style={{ fontSize: 9, color: "#3d4560", fontFamily: "var(--font-mono)", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ fontSize: 14, fontWeight: 700, color, fontFamily: "var(--font-mono)" }}>
        {value}
      </div>
    </div>
  );
}

// ─── Copy button ──────────────────────────────────────────────────────────────

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button
      onClick={copy}
      style={{
        background: "none",
        border: "1px solid #232a3a",
        borderRadius: 4,
        padding: "3px 8px",
        cursor: "pointer",
        display: "flex",
        alignItems: "center",
        gap: 4,
        color: "#6b7591",
        fontSize: 10,
        fontFamily: "var(--font-mono)",
      }}
    >
      {copied ? (
        <><CheckCheck size={10} color="#22d3a0" /> Copied</>
      ) : (
        <><Copy size={10} /> Copy</>
      )}
    </button>
  );
}

// ─── Result Card ─────────────────────────────────────────────────────────────

function ResultCard({ result }: { result: QuantumResult }) {
  const [showCode, setShowCode] = useState(false);
  const isIBM = result.quantum_backend === "ibm_quantum";

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, ease: "backOut" }}
      style={{
        background: "#0a0c10",
        border: "1px solid #22d3a044",
        borderRadius: 14,
        overflow: "hidden",
        boxShadow: "0 0 40px #22d3a011",
      }}
    >
      {/* Card header */}
      <div
        style={{
          padding: "14px 16px",
          borderBottom: "1px solid #1a1f2e",
          background: "linear-gradient(135deg, #22d3a010, transparent)",
          display: "flex",
          alignItems: "center",
          gap: 10,
        }}
      >
        <div
          style={{
            width: 8, height: 8,
            borderRadius: "50%",
            background: "#22d3a0",
            boxShadow: "0 0 8px #22d3a0",
            animation: "pulse 2s infinite",
          }}
        />
        <span style={{ fontSize: 13, fontWeight: 600, color: "#22d3a0" }}>
          Optimal Route Computed
        </span>
        <span
          style={{
            marginLeft: "auto",
            fontSize: 9,
            fontFamily: "var(--font-mono)",
            color: isIBM ? "#f59e0b" : "#6b7591",
            background: isIBM ? "#f59e0b11" : "#1a1f2e",
            border: `1px solid ${isIBM ? "#f59e0b44" : "#232a3a"}`,
            padding: "2px 6px",
            borderRadius: 4,
          }}
        >
          {isIBM ? "IBM QUANTUM" : "AER SIMULATOR"}
        </span>
      </div>

      <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 16 }}>
        {/* Problem description */}
        <div style={{ fontSize: 12, color: "#6b7591", lineHeight: 1.6 }}>
          {result.problem_description}
        </div>

        {/* Metrics row */}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <Metric label="Qubits" value={result.num_qubits} color="#00c8ff" />
          <Metric label="Depth" value={result.circuit_depth} color="#a855f7" />
          <Metric label="QAOA p" value={result.qaoa_layers} color="#f59e0b" />
          <Metric label="Shots" value={result.total_shots.toLocaleString()} color="#22d3a0" />
        </div>

        {/* Optimal route */}
        <div style={{ background: "#050608", border: "1px solid #1a1f2e", borderRadius: 10, padding: 14 }}>
          <div style={{ fontSize: 10, color: "#3d4560", fontFamily: "var(--font-mono)", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 12 }}>
            Optimal Route
          </div>
          <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 6 }}>
            {result.optimal_route.map((city, i) => (
              <React.Fragment key={`${city}-${i}`}>
                <motion.div
                  initial={{ opacity: 0, scale: 0.8 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: i * 0.1, duration: 0.3, ease: "backOut" }}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 4,
                    background: "#0f1218",
                    border: "1px solid #232a3a",
                    borderRadius: 6,
                    padding: "5px 10px",
                  }}
                >
                  <MapPin size={10} color="#22d3a0" />
                  <span style={{ fontSize: 11, fontWeight: 600, color: "#e8eaf0", fontFamily: "var(--font-mono)" }}>
                    {city}
                  </span>
                </motion.div>
                {i < result.optimal_route.length - 1 && (
                  <Navigation size={10} color="#3d4560" style={{ transform: "rotate(90deg)" }} />
                )}
              </React.Fragment>
            ))}
            {/* Return arrow */}
            <Navigation size={10} color="#22d3a044" style={{ transform: "rotate(90deg)" }} />
            <span style={{ fontSize: 10, color: "#3d4560", fontFamily: "var(--font-mono)" }}>
              {result.optimal_route[0]}
            </span>
          </div>
          <div style={{ marginTop: 12, display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 10, color: "#3d4560" }}>Total distance:</span>
            <span style={{ fontSize: 13, fontWeight: 700, fontFamily: "var(--font-mono)", color: "#22d3a0" }}>
              {result.route_distance.toFixed(1)} units
            </span>
          </div>
        </div>

        {/* Best bitstring */}
        <div>
          <div style={{ fontSize: 10, color: "#3d4560", fontFamily: "var(--font-mono)", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 6 }}>
            Best Measurement
          </div>
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 11,
              color: "#a855f7",
              background: "#050608",
              border: "1px solid #a855f722",
              borderRadius: 6,
              padding: "6px 10px",
              letterSpacing: "0.15em",
              wordBreak: "break-all",
            }}
          >
            |{result.best_bitstring}⟩
          </div>
        </div>

        {/* Human readable decision */}
        <div
          style={{
            background: "linear-gradient(135deg, #22d3a008, #00c8ff05)",
            border: "1px solid #22d3a022",
            borderRadius: 10,
            padding: 14,
          }}
        >
          <div style={{ fontSize: 10, color: "#3d4560", fontFamily: "var(--font-mono)", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 8 }}>
            Enterprise Decision
          </div>
          <div style={{ fontSize: 12, color: "#e8eaf0", lineHeight: 1.7, whiteSpace: "pre-line" }}>
            {result.human_readable_result}
          </div>
        </div>

        {/* Top solutions */}
        {result.top_solutions.length > 0 && (
          <div>
            <div style={{ fontSize: 10, color: "#3d4560", fontFamily: "var(--font-mono)", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 8 }}>
              Top Quantum Outcomes
            </div>
            {result.top_solutions.map((sol, i) => (
              <div
                key={i}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  padding: "7px 10px",
                  marginBottom: 4,
                  background: i === 0 ? "#22d3a008" : "#050608",
                  border: `1px solid ${i === 0 ? "#22d3a033" : "#1a1f2e"}`,
                  borderRadius: 6,
                }}
              >
                <span style={{ fontSize: 9, color: "#3d4560", fontFamily: "var(--font-mono)", width: 12 }}>
                  #{i + 1}
                </span>
                <span style={{ flex: 1, fontSize: 10, fontFamily: "var(--font-mono)", color: i === 0 ? "#22d3a0" : "#6b7591" }}>
                  {sol.route.join(" → ")}
                </span>
                <span style={{ fontSize: 10, fontFamily: "var(--font-mono)", color: "#6b7591" }}>
                  {sol.distance.toFixed(1)}
                </span>
                <span style={{ fontSize: 9, color: "#3d4560", fontFamily: "var(--font-mono)" }}>
                  {(sol.probability * 100).toFixed(1)}%
                </span>
              </div>
            ))}
          </div>
        )}

        {/* Qiskit code toggle */}
        {result.circuit_code_display && (
          <div>
            <div
              onClick={() => setShowCode((v) => !v)}
              role="button"
              style={{
                width: "100%",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                background: "none",
                border: "1px solid #1a1f2e",
                borderRadius: 6,
                padding: "8px 12px",
                cursor: "pointer",
                color: "#6b7591",
                fontSize: 11,
                fontFamily: "var(--font-mono)",
              }}
            >
              <span>View Qiskit Circuit Code</span>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <CopyButton text={result.circuit_code_display} />
                <motion.div animate={{ rotate: showCode ? 180 : 0 }} transition={{ duration: 0.2 }}>
                  <ChevronDown size={12} />
                </motion.div>
              </div>
            </div>
            <AnimatePresence>
              {showCode && (
                <motion.pre
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.3 }}
                  style={{
                    overflow: "auto",
                    background: "#050608",
                    border: "1px solid #1a1f2e",
                    borderTop: "none",
                    borderRadius: "0 0 6px 6px",
                    padding: 12,
                    fontFamily: "var(--font-mono)",
                    fontSize: 10,
                    color: "#a855f7",
                    lineHeight: 1.8,
                    whiteSpace: "pre",
                    maxHeight: 280,
                  }}
                >
                  {result.circuit_code_display}
                </motion.pre>
              )}
            </AnimatePresence>
          </div>
        )}
      </div>
    </motion.div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function QuantumCommandCenter() {
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [audioFile, setAudioFile] = useState<File | null>(null);

  const [jobId, setJobId]       = useState<string | null>(null);
  const [status, setStatus]     = useState<StatusResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError]       = useState<string | null>(null);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Stop polling ────────────────────────────────────────────────────────
  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  // ── Poll status ─────────────────────────────────────────────────────────
  const pollStatus = useCallback(async (id: string) => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/status/${id}`);
      if (!res.ok) throw new Error(`Status fetch failed: ${res.status}`);
      const data: StatusResponse = await res.json();
      setStatus(data);

      if (data.status === "complete" || data.status === "error") {
        stopPolling();
        setIsLoading(false);
        if (data.status === "error") setError(data.error_message ?? "Unknown error");
      }
    } catch (err: any) {
      console.error("Poll error:", err);
    }
  }, []);

  // ── Submit job ──────────────────────────────────────────────────────────
  const handleSubmit = async () => {
    setError(null);
    setStatus(null);
    setJobId(null);
    setIsLoading(true);
  
    try {
      let res: Response;
  
      if (imageFile || audioFile) {
        // Has files — send as multipart FormData
        const formData = new FormData();
        if (imageFile) formData.append("image", imageFile);
        if (audioFile) formData.append("audio", audioFile);
  
        res = await fetch(`${BACKEND_URL}/api/solve`, {
          method: "POST",
          body: formData,
          // DO NOT set Content-Type manually — browser sets it with boundary
        });
      } else {
        // No files — send empty JSON so body is never null
        res = await fetch(`${BACKEND_URL}/api/solve`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({}),
        });
      }
  
      // Always check status before parsing
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`Server error ${res.status}: ${text}`);
      }
  
      // Safe JSON parse
      let data: { job_id: string; message: string };
      try {
        data = await res.json();
      } catch (parseErr) {
        const raw = await res.clone().text().catch(() => "unreadable");
        throw new Error(`JSON parse failed. Raw response: ${raw}`);
      }
  
      if (!data.job_id) {
        throw new Error("No job_id in response");
      }
  
      setJobId(data.job_id);
  
      // Start polling
      pollRef.current = setInterval(
        () => pollStatus(data.job_id),
        POLL_INTERVAL_MS
      );
      pollStatus(data.job_id);
  
    } catch (err: any) {
      setIsLoading(false);
      setError(err.message ?? "Failed to submit job");
    }
  };

  // ── Reset ───────────────────────────────────────────────────────────────
  const handleReset = () => {
    stopPolling()
    setJobId(null)
    setStatus(null)
    setIsLoading(false)
    setError(null)
    // DO NOT clear imageFile/audioFile so user can retry
  };

  // Cleanup on unmount
  useEffect(() => () => stopPolling(), []);

  const isRunning = isLoading && status?.status !== "complete" && status?.status !== "error";
  const isDone = status?.status === "complete";
  const hasUploads = imageFile || audioFile;

  // ─── Render ──────────────────────────────────────────────────────────────

  return (
    <div
      style={{
        minHeight: "100dvh",
        background: "var(--bg-base)",
        backgroundImage: `
          linear-gradient(var(--grid-line) 1px, transparent 1px),
          linear-gradient(90deg, var(--grid-line) 1px, transparent 1px)
        `,
        backgroundSize: "40px 40px",
        fontFamily: "var(--font-sans)",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* ── Header bar ── */}
      <header
        style={{
          borderBottom: "1px solid #1a1f2e",
          padding: "0 32px",
          height: 56,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          background: "#050608cc",
          backdropFilter: "blur(12px)",
          position: "sticky",
          top: 0,
          zIndex: 50,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {/* Quantum logo mark */}
          <div style={{ position: "relative", width: 28, height: 28 }}>
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ repeat: Infinity, duration: 8, ease: "linear" }}
              style={{
                width: 28, height: 28,
                border: "1.5px solid #00c8ff44",
                borderRadius: "50%",
                position: "absolute",
              }}
            />
            <motion.div
              animate={{ rotate: -360 }}
              transition={{ repeat: Infinity, duration: 5, ease: "linear" }}
              style={{
                width: 18, height: 18,
                border: "1.5px solid #a855f766",
                borderRadius: "50%",
                position: "absolute",
                top: 5, left: 5,
              }}
            />
            <div style={{
              width: 6, height: 6,
              background: "#00c8ff",
              borderRadius: "50%",
              position: "absolute",
              top: 11, left: 11,
              boxShadow: "0 0 6px #00c8ff",
            }} />
          </div>
          <div>
            <div style={{ fontSize: 15, fontWeight: 700, letterSpacing: "-0.02em", color: "#e8eaf0" }}>
              Q<span style={{ color: "#00c8ff" }}>-</span>Optima
            </div>
            <div style={{ fontSize: 9, color: "#3d4560", fontFamily: "var(--font-mono)", letterSpacing: "0.1em", textTransform: "uppercase", lineHeight: 1 }}>
              Quantum Logistics Agent
            </div>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
          {/* Live indicator */}
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <motion.div
              animate={{ opacity: [1, 0.3, 1] }}
              transition={{ repeat: Infinity, duration: 2 }}
              style={{
                width: 6, height: 6, borderRadius: "50%",
                background: isRunning ? "#00c8ff" : isDone ? "#22d3a0" : "#3d4560",
                boxShadow: isRunning ? "0 0 8px #00c8ff" : isDone ? "0 0 8px #22d3a0" : "none",
              }}
            />
            <span style={{ fontSize: 10, color: "#3d4560", fontFamily: "var(--font-mono)" }}>
              {isRunning ? "RUNNING" : isDone ? "COMPLETE" : "STANDBY"}
            </span>
          </div>

          {/* Backend URL pill */}
          <div
            style={{
              fontSize: 9, fontFamily: "var(--font-mono)",
              color: "#3d4560",
              background: "#0a0c10",
              border: "1px solid #1a1f2e",
              padding: "3px 8px",
              borderRadius: 4,
              maxWidth: 220,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {BACKEND_URL}
          </div>
        </div>
      </header>

      {/* ── Main grid ── */}
      <div
        style={{
          flex: 1,
          display: "grid",
          gridTemplateColumns: "320px 1fr 380px",
          gridTemplateRows: "1fr",
          gap: 0,
          maxWidth: 1400,
          width: "100%",
          margin: "0 auto",
          padding: "28px 24px",
          alignItems: "start",
        }}
      >
        {/* ─────────────────────────── LEFT: Upload Panel ────────────────── */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 16,
            paddingRight: 24,
            borderRight: "1px solid #1a1f2e",
          }}
        >
          <div>
            <div style={{ fontSize: 10, color: "#3d4560", fontFamily: "var(--font-mono)", letterSpacing: "0.12em", textTransform: "uppercase", marginBottom: 4 }}>
              Input Sources
            </div>
            <div style={{ fontSize: 18, fontWeight: 700, color: "#e8eaf0", letterSpacing: "-0.02em" }}>
              Upload Assets
            </div>
          </div>

          {/* Image upload */}
          <UploadZone
            accept={{ "image/*": [".jpg", ".jpeg", ".png", ".webp", ".gif"] }}
            label="Drop Route Map"
            sublabel="JPEG · PNG · WebP"
            icon={ImageIcon}
            color="#00c8ff"
            file={imageFile}
            onDrop={setImageFile}
            onRemove={() => setImageFile(null)}
          />

          {/* Audio upload */}
          <UploadZone
            accept={{ "audio/*": [".mp3", ".wav", ".webm", ".ogg", ".m4a"] }}
            label="Drop Audio Memo"
            sublabel="MP3 · WAV · WebM"
            icon={Mic2}
            color="#a855f7"
            file={audioFile}
            onDrop={setAudioFile}
            onRemove={() => setAudioFile(null)}
          />

          {/* Demo mode note */}
          {!hasUploads && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              style={{
                padding: "10px 12px",
                background: "#f59e0b08",
                border: "1px solid #f59e0b22",
                borderRadius: 8,
                fontSize: 11,
                color: "#6b7591",
                lineHeight: 1.6,
              }}
            >
              <span style={{ color: "#f59e0b", fontWeight: 600 }}>Demo mode:</span>{" "}
              No uploads required. The agent will run on a synthetic 4-city logistics dataset.
            </motion.div>
          )}

          {/* Separator */}
          <div style={{ height: 1, background: "#1a1f2e" }} />

          {/* Model badges */}
          <div>
            <div style={{ fontSize: 10, color: "#3d4560", fontFamily: "var(--font-mono)", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 10 }}>
              Agent Stack
            </div>
            {[
              { label: "Whisper base", sub: "Audio → Text", color: "#00c8ff" },
              { label: "gemini-2.5-flash-lite", sub: "Vision → QUBO", color: "#a855f7" },
              { label: "Qiskit QAOA p=1", sub: "QUBO → Circuit", color: "#22d3a0" },
              { label: "IBM Quantum / Aer", sub: "Circuit → Counts", color: "#f59e0b" },
            ].map((item) => (
              <div
                key={item.label}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  padding: "7px 0",
                  borderBottom: "1px solid #1a1f2e",
                }}
              >
                <div style={{ width: 6, height: 6, borderRadius: "50%", background: item.color, boxShadow: `0 0 6px ${item.color}`, flexShrink: 0 }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 11, fontWeight: 600, color: "#e8eaf0", fontFamily: "var(--font-mono)" }}>
                    {item.label}
                  </div>
                  <div style={{ fontSize: 9, color: "#3d4560" }}>{item.sub}</div>
                </div>
              </div>
            ))}
          </div>

          {/* CTA / Reset button */}
          {!isRunning && !isDone ? (
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.97 }}
              onClick={handleSubmit}
              disabled={isLoading}
              style={{
                width: "100%",
                padding: "13px 0",
                borderRadius: 10,
                border: "none",
                cursor: isLoading ? "wait" : "pointer",
                background: "linear-gradient(135deg, #00c8ff, #a855f7)",
                color: "#050608",
                fontWeight: 700,
                fontSize: 13,
                fontFamily: "var(--font-sans)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 8,
                boxShadow: "0 0 24px #00c8ff44",
                letterSpacing: "0.01em",
              }}
            >
              <Zap size={15} />
              Run Quantum Agent
            </motion.button>
          ) : isDone ? (
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.97 }}
              onClick={handleReset}
              style={{
                width: "100%",
                padding: "13px 0",
                borderRadius: 10,
                border: "1px solid #232a3a",
                cursor: "pointer",
                background: "#0a0c10",
                color: "#6b7591",
                fontWeight: 600,
                fontSize: 13,
                fontFamily: "var(--font-sans)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 8,
              }}
            >
              <RotateCcw size={14} />
              New Job
            </motion.button>
          ) : (
            <div
              style={{
                width: "100%",
                padding: "13px 0",
                borderRadius: 10,
                background: "#0a0c10",
                border: "1px solid #00c8ff22",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 8,
                color: "#00c8ff",
                fontSize: 12,
                fontFamily: "var(--font-mono)",
              }}
            >
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ repeat: Infinity, duration: 1, ease: "linear" }}
              >
                <Activity size={14} />
              </motion.div>
              Quantum Pipeline Active …
            </div>
          )}

          {/* Error */}
          {error && (
            <motion.div
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              style={{
                padding: "10px 12px",
                background: "#f43f5e08",
                border: "1px solid #f43f5e33",
                borderRadius: 8,
                fontSize: 11,
                color: "#f43f5e",
                lineHeight: 1.6,
                display: "flex",
                gap: 8,
              }}
            >
              <AlertTriangle size={13} style={{ flexShrink: 0, marginTop: 2 }} />
              <span>{error}</span>
            </motion.div>
          )}

          {/* Job ID */}
          {jobId && (
            <div style={{ fontSize: 9, color: "#3d4560", fontFamily: "var(--font-mono)", wordBreak: "break-all" }}>
              JOB: {jobId}
            </div>
          )}
        </div>

        {/* ─────────────────────── CENTER: Timeline ──────────────────────── */}
        <div style={{ padding: "0 28px" }}>
          <div style={{ marginBottom: 20 }}>
            <div style={{ fontSize: 10, color: "#3d4560", fontFamily: "var(--font-mono)", letterSpacing: "0.12em", textTransform: "uppercase", marginBottom: 4 }}>
              Live Agent Status
            </div>
            <div style={{ fontSize: 18, fontWeight: 700, color: "#e8eaf0", letterSpacing: "-0.02em" }}>
              Reasoning Pipeline
            </div>
          </div>

          <AgentTimeline
            stepLogs={status?.step_logs ?? []}
            currentStep={status?.current_step ?? "queued"}
            progressPercent={status?.progress_percent ?? 0}
          />
        </div>

        {/* ─────────────────────── RIGHT: Result ─────────────────────────── */}
        <div
          style={{
            paddingLeft: 24,
            borderLeft: "1px solid #1a1f2e",
          }}
        >
          <div style={{ marginBottom: 20 }}>
            <div style={{ fontSize: 10, color: "#3d4560", fontFamily: "var(--font-mono)", letterSpacing: "0.12em", textTransform: "uppercase", marginBottom: 4 }}>
              Output
            </div>
            <div style={{ fontSize: 18, fontWeight: 700, color: "#e8eaf0", letterSpacing: "-0.02em" }}>
              Quantum Decision
            </div>
          </div>

          <AnimatePresence mode="wait">
            {status?.result ? (
              <ResultCard key="result" result={status.result} />
            ) : (
              <motion.div
                key="empty"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                style={{
                  height: 400,
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 16,
                  border: "1px dashed #1a1f2e",
                  borderRadius: 14,
                  color: "#3d4560",
                }}
              >
                {/* Idle quantum orb animation */}
                <div style={{ position: "relative", width: 72, height: 72 }}>
                  {[0, 1, 2].map((i) => (
                    <motion.div
                      key={i}
                      animate={{ rotate: i % 2 === 0 ? 360 : -360, opacity: isRunning ? 1 : 0.3 }}
                      transition={{ repeat: Infinity, duration: 4 + i * 2, ease: "linear" }}
                      style={{
                        position: "absolute",
                        inset: i * 10,
                        border: `1px solid ${["#00c8ff33", "#a855f722", "#22d3a011"][i]}`,
                        borderRadius: "50%",
                      }}
                    />
                  ))}
                  <div
                    style={{
                      position: "absolute",
                      inset: 28,
                      background: isRunning ? "#00c8ff" : "#1a1f2e",
                      borderRadius: "50%",
                      boxShadow: isRunning ? "0 0 16px #00c8ff" : "none",
                      transition: "all 0.4s",
                    }}
                  />
                </div>
                <div style={{ textAlign: "center" }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#3d4560", marginBottom: 4 }}>
                    {isRunning ? "Quantum pipeline running…" : "Awaiting submission"}
                  </div>
                  <div style={{ fontSize: 11, color: "#3d4560", fontFamily: "var(--font-mono)" }}>
                    {isRunning
                      ? "Results will appear here automatically"
                      : "Upload a map + audio, then click Run"}
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* ── Footer ── */}
      <footer
        style={{
          borderTop: "1px solid #1a1f2e",
          padding: "14px 32px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          fontSize: 10,
          color: "#3d4560",
          fontFamily: "var(--font-mono)",
        }}
      >
        <span>Q-OPTIMA · MILAN AI WEEK 2026 · INTELLIGENT REASONING TRACK</span>
        <span style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <a
            href={`${BACKEND_URL}/api/docs`}
            target="_blank"
            rel="noreferrer"
            style={{ color: "#3d4560", textDecoration: "none", display: "flex", alignItems: "center", gap: 4 }}
          >
            API DOCS <ExternalLink size={9} />
          </a>
          <span>GEMINI-2.5-FLASH-LITE · QAOA · IBM QUANTUM</span>
        </span>
      </footer>

      {/* Keyframe for pulse */}
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50%       { opacity: 0.4; }
        }
        @media (max-width: 1100px) {
          /* Collapse to single-column on smaller screens */
          [data-grid="main"] {
            grid-template-columns: 1fr !important;
          }
        }
      `}</style>
    </div>
  );
}