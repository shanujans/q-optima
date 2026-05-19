"use client";
// Framer Motion animated timeline — each node "charges up" as the
// LangGraph agent progresses through its 5-step quantum pipeline.

import React, { useEffect, useRef } from "react";
import { motion, AnimatePresence, useAnimation } from "framer-motion";
import {
  Mic2, ScanSearch, Atom, Cpu, BarChart3,
  CheckCircle2, Loader2, AlertCircle, Clock,
} from "lucide-react";

// ─── Types ─────────────────────────────────────────────────────────────────

export type StepStatus = "pending" | "running" | "complete" | "error" | "skipped";

export interface StepLog {
  step: string;
  label: string;
  status: StepStatus;
  message: string;
  detail?: string;
  timestamp: string;
}

interface AgentTimelineProps {
  stepLogs: StepLog[];
  currentStep: string;
  progressPercent: number;
}

// ─── Static step definitions ────────────────────────────────────────────────

const PIPELINE_STEPS = [
  {
    key: "transcribe",
    label: "Audio Transcription",
    sublabel: "Whisper · ROCm AMD",
    icon: Mic2,
    color: "#00c8ff",
    glow: "0 0 20px #00c8ff66",
  },
  {
    key: "analyze",
    label: "Gemini Vision Analysis",
    sublabel: "gemini-2.5-flash-lite · Multimodal",
    icon: ScanSearch,
    color: "#a855f7",
    glow: "0 0 20px #a855f766",
  },
  {
    key: "build_qubo",
    label: "QUBO Formulation",
    sublabel: "QUBO Matrix · Ising Transform",
    icon: Atom,
    color: "#22d3a0",
    glow: "0 0 20px #22d3a066",
  },
  {
    key: "execute_quantum",
    label: "Quantum Execution",
    sublabel: "QAOA · IBM Quantum / Aer",
    icon: Cpu,
    color: "#f59e0b",
    glow: "0 0 20px #f59e0b66",
  },
  {
    key: "parse_result",
    label: "Enterprise Decision",
    sublabel: "Bitstring → Optimal Route",
    icon: BarChart3,
    color: "#22d3a0",
    glow: "0 0 20px #22d3a088",
  },
];

// Which backend step keys map to which pipeline step index
const STEP_KEY_MAP: Record<string, number> = {
  queued:         -1,
  running:        -1,
  transcribed:     0,
  analyzed:        1,
  circuit_built:   2,
  build_qubo:      2,
  executed:        3,
  complete:        4,
  error:          -1,
};

function getStepStatuses(
  stepLogs: StepLog[],
  currentStep: string
): StepStatus[] {
  const completedIndex = STEP_KEY_MAP[currentStep] ?? -1;

  return PIPELINE_STEPS.map((pStep, idx) => {
    // Find a log matching this pipeline step
    const matchingLog = stepLogs.find(
      (log) =>
        log.step === pStep.key ||
        (pStep.key === "build_qubo" && log.step === "build_circuit") ||
        (pStep.key === "analyze"    && log.step === "analyze")
    );

    if (matchingLog) {
      if (matchingLog.status === "error") return "error";
      if (matchingLog.status === "complete") return "complete";
      if (matchingLog.status === "running")  return "running";
    }

    if (idx < completedIndex) return "complete";
    if (idx === completedIndex + 1 && currentStep !== "complete" && currentStep !== "error")
      return "running";
    return "pending";
  });
}

// ─── Sub-components ─────────────────────────────────────────────────────────

function StatusIcon({ status }: { status: StepStatus }) {
  if (status === "complete")
    return <CheckCircle2 size={14} style={{ color: "#22d3a0" }} />;
  if (status === "running")
    return (
      <motion.div
        animate={{ rotate: 360 }}
        transition={{ repeat: Infinity, duration: 1, ease: "linear" }}
      >
        <Loader2 size={14} style={{ color: "#00c8ff" }} />
      </motion.div>
    );
  if (status === "error")
    return <AlertCircle size={14} style={{ color: "#f43f5e" }} />;
  return <Clock size={14} style={{ color: "#3d4560" }} />;
}

function NodeOrb({
  step,
  status,
  index,
}: {
  step: (typeof PIPELINE_STEPS)[0];
  status: StepStatus;
  index: number;
}) {
  const Icon = step.icon;
  const isComplete = status === "complete";
  const isRunning = status === "running";
  const isError = status === "error";

  const orbColor = isError
    ? "#f43f5e"
    : isComplete || isRunning
    ? step.color
    : "#1a1f2e";

  const orbGlow = isRunning
    ? step.glow
    : isComplete
    ? step.glow.replace("66", "33")
    : "none";

  return (
    <motion.div
      initial={{ scale: 0.7, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ delay: index * 0.08, duration: 0.4, ease: "backOut" }}
      style={{ position: "relative", flexShrink: 0 }}
    >
      {/* Pulse ring — only when running */}
      <AnimatePresence>
        {isRunning && (
          <motion.div
            key="pulse"
            initial={{ scale: 1, opacity: 0.7 }}
            animate={{ scale: 2.2, opacity: 0 }}
            exit={{ opacity: 0 }}
            transition={{ repeat: Infinity, duration: 1.4, ease: "easeOut" }}
            style={{
              position: "absolute",
              inset: 0,
              borderRadius: "50%",
              background: step.color,
              zIndex: 0,
            }}
          />
        )}
      </AnimatePresence>

      {/* Orb */}
      <motion.div
        animate={{
          background: isError
            ? "radial-gradient(circle, #f43f5e22, #0a0c10)"
            : isComplete
            ? `radial-gradient(circle, ${step.color}22, #0a0c10)`
            : isRunning
            ? `radial-gradient(circle, ${step.color}33, #0a0c10)`
            : "radial-gradient(circle, #1a1f2e, #0a0c10)",
          boxShadow: orbGlow,
          borderColor: orbColor,
        }}
        transition={{ duration: 0.5 }}
        style={{
          width: 48,
          height: 48,
          borderRadius: "50%",
          border: `1.5px solid`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          position: "relative",
          zIndex: 1,
        }}
      >
        <motion.div
          animate={{
            color: isComplete || isRunning ? step.color : "#3d4560",
            filter:
              isRunning
                ? `drop-shadow(0 0 6px ${step.color})`
                : "none",
          }}
          transition={{ duration: 0.4 }}
        >
          <Icon size={20} />
        </motion.div>
      </motion.div>

      {/* Step number badge */}
      <div
        style={{
          position: "absolute",
          top: -4,
          right: -4,
          width: 16,
          height: 16,
          borderRadius: "50%",
          background: isComplete ? step.color : "#1a1f2e",
          border: "1px solid #232a3a",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 8,
          fontFamily: "var(--font-mono)",
          color: isComplete ? "#050608" : "#3d4560",
          fontWeight: 700,
          zIndex: 2,
        }}
      >
        {index + 1}
      </div>
    </motion.div>
  );
}

function ConnectorLine({
  filled,
  color,
}: {
  filled: boolean;
  color: string;
}) {
  return (
    <div
      style={{
        flex: 1,
        height: 1.5,
        background: "#1a1f2e",
        position: "relative",
        overflow: "hidden",
        margin: "0 4px",
        marginTop: -24, // align with orb center
        alignSelf: "center",
      }}
    >
      <motion.div
        animate={{ scaleX: filled ? 1 : 0 }}
        initial={{ scaleX: 0 }}
        transition={{ duration: 0.6, ease: "easeInOut" }}
        style={{
          position: "absolute",
          inset: 0,
          background: color,
          transformOrigin: "left",
          boxShadow: `0 0 8px ${color}`,
        }}
      />
    </div>
  );
}

// ─── Log entry ────────────────────────────────────────────────────────────

function LogEntry({ log, stepDef }: { log: StepLog; stepDef: (typeof PIPELINE_STEPS)[0] | undefined }) {
  const color = stepDef?.color ?? "#6b7591";
  return (
    <motion.div
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.3 }}
      style={{
        display: "flex",
        gap: 10,
        padding: "10px 12px",
        borderRadius: 8,
        background: "#0a0c10",
        border: `1px solid ${
          log.status === "complete"
            ? color + "33"
            : log.status === "running"
            ? color + "44"
            : log.status === "error"
            ? "#f43f5e33"
            : "#1a1f2e"
        }`,
        marginBottom: 6,
      }}
    >
      <div style={{ paddingTop: 2, flexShrink: 0 }}>
        <StatusIcon status={log.status} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontSize: 12,
            color: "#e8eaf0",
            fontWeight: 500,
            marginBottom: 2,
          }}
        >
          {log.label}
        </div>
        <div
          style={{
            fontSize: 11,
            color: "#6b7591",
            lineHeight: 1.5,
          }}
        >
          {log.message}
        </div>
        {log.detail && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            transition={{ delay: 0.2 }}
            style={{
              marginTop: 6,
              padding: "6px 8px",
              borderRadius: 4,
              background: "#050608",
              border: "1px solid #1a1f2e",
              fontFamily: "var(--font-mono)",
              fontSize: 10,
              color: color,
              lineHeight: 1.7,
              whiteSpace: "pre-wrap",
              overflowX: "auto",
              maxHeight: 120,
              overflow: "auto",
            }}
          >
            {log.detail.length > 300
              ? log.detail.slice(0, 300) + "…"
              : log.detail}
          </motion.div>
        )}
        <div
          style={{
            fontSize: 10,
            color: "#3d4560",
            marginTop: 4,
            fontFamily: "var(--font-mono)",
          }}
        >
          {new Date(log.timestamp).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          })}
        </div>
      </div>
    </motion.div>
  );
}

// ─── Main Component ──────────────────────────────────────────────────────────

export default function AgentTimeline({
  stepLogs,
  currentStep,
  progressPercent,
}: AgentTimelineProps) {
  const statuses = getStepStatuses(stepLogs, currentStep);
  const logEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll logs
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [stepLogs]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      {/* ── Header ── */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <div style={{ fontSize: 11, color: "#3d4560", fontFamily: "var(--font-mono)", letterSpacing: "0.12em", textTransform: "uppercase", marginBottom: 4 }}>
            Quantum Pipeline
          </div>
          <div style={{ fontSize: 15, fontWeight: 600, color: "#e8eaf0" }}>
            Agent Reasoning Timeline
          </div>
        </div>
        <motion.div
          animate={{
            color: currentStep === "complete" ? "#22d3a0" : currentStep === "error" ? "#f43f5e" : "#00c8ff",
          }}
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: 22,
            fontWeight: 700,
          }}
        >
          {progressPercent}%
        </motion.div>
      </div>

      {/* ── Progress bar ── */}
      <div
        style={{
          height: 3,
          background: "#1a1f2e",
          borderRadius: 2,
          overflow: "hidden",
        }}
      >
        <motion.div
          animate={{ width: `${progressPercent}%` }}
          transition={{ duration: 0.8, ease: "easeInOut" }}
          style={{
            height: "100%",
            background:
              currentStep === "error"
                ? "#f43f5e"
                : "linear-gradient(90deg, #00c8ff, #a855f7)",
            boxShadow:
              currentStep === "error"
                ? "0 0 10px #f43f5e"
                : "0 0 10px #00c8ff",
            borderRadius: 2,
          }}
        />
      </div>

      {/* ── Orb row ── */}
      <div style={{ display: "flex", alignItems: "flex-start", gap: 0 }}>
        {PIPELINE_STEPS.map((step, i) => (
          <React.Fragment key={step.key}>
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: 8,
                flex: i < PIPELINE_STEPS.length - 1 ? "0 0 auto" : "0 0 auto",
              }}
            >
              <NodeOrb step={step} status={statuses[i]} index={i} />
              <div style={{ textAlign: "center", maxWidth: 72 }}>
                <div
                  style={{
                    fontSize: 9,
                    fontWeight: 600,
                    color:
                      statuses[i] === "complete" || statuses[i] === "running"
                        ? step.color
                        : "#3d4560",
                    lineHeight: 1.3,
                    transition: "color 0.4s",
                    fontFamily: "var(--font-sans)",
                  }}
                >
                  {step.label}
                </div>
                <div
                  style={{
                    fontSize: 8,
                    color: "#3d4560",
                    lineHeight: 1.3,
                    marginTop: 2,
                    fontFamily: "var(--font-mono)",
                  }}
                >
                  {step.sublabel}
                </div>
              </div>
            </div>
            {i < PIPELINE_STEPS.length - 1 && (
              <ConnectorLine
                filled={statuses[i] === "complete"}
                color={PIPELINE_STEPS[i].color}
              />
            )}
          </React.Fragment>
        ))}
      </div>

      {/* ── Log feed ── */}
      {stepLogs.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          style={{
            maxHeight: 320,
            overflowY: "auto",
            display: "flex",
            flexDirection: "column",
          }}
        >
          <div
            style={{
              fontSize: 10,
              color: "#3d4560",
              fontFamily: "var(--font-mono)",
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              marginBottom: 10,
            }}
          >
            Live Log Feed
          </div>
          <AnimatePresence initial={false}>
            {stepLogs.map((log, i) => {
              const stepDef = PIPELINE_STEPS.find(
                (s) =>
                  s.key === log.step ||
                  (s.key === "build_qubo" && log.step === "build_circuit")
              );
              return (
                <LogEntry key={`${log.step}-${i}`} log={log} stepDef={stepDef} />
              );
            })}
          </AnimatePresence>
          <div ref={logEndRef} />
        </motion.div>
      )}

      {/* ── Empty state ── */}
      {stepLogs.length === 0 && (
        <div
          style={{
            padding: "24px 0",
            textAlign: "center",
            color: "#3d4560",
            fontSize: 12,
            fontFamily: "var(--font-mono)",
          }}
        >
          Awaiting quantum agent invocation …
        </div>
      )}
    </div>
  );
}
