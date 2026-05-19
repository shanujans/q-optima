// Voice output via Web Speech API (zero cost, browser native)
// Reads the quantum result aloud when it arrives.
// One line of JS — but wrapped properly for React with controls.

"use client";
import { useEffect, useRef, useState } from "react";
import { Volume2, VolumeX } from "lucide-react";

interface VoiceOutputProps {
  text: string | null;   // pass human_readable_result from QuantumResult
  autoSpeak?: boolean;   // speak automatically when text arrives
}

export default function VoiceOutput({
  text,
  autoSpeak = true,
}: VoiceOutputProps) {
  const [speaking, setSpeaking] = useState(false);
  const [supported, setSupported] = useState(false);
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);

  useEffect(() => {
    setSupported(typeof window !== "undefined" && "speechSynthesis" in window);
  }, []);

  // Auto-speak when result arrives
  useEffect(() => {
    if (autoSpeak && text && supported) {
      speak(text);
    }
  }, [text]);

  const speak = (content: string) => {
    if (!supported) return;
    window.speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(content);
    utterance.rate   = 0.95;
    utterance.pitch  = 1.0;
    utterance.volume = 1.0;
    // Pick a natural English voice if available
    const voices = window.speechSynthesis.getVoices();
    const preferred = voices.find(
      (v) => v.lang === "en-GB" || v.lang === "en-US"
    );
    if (preferred) utterance.voice = preferred;

    utterance.onstart = () => setSpeaking(true);
    utterance.onend   = () => setSpeaking(false);
    utterance.onerror = () => setSpeaking(false);

    utteranceRef.current = utterance;
    window.speechSynthesis.speak(utterance);
  };

  const stop = () => {
    window.speechSynthesis.cancel();
    setSpeaking(false);
  };

  if (!supported || !text) return null;

  return (
    <button
      onClick={speaking ? stop : () => speak(text)}
      title={speaking ? "Stop voice output" : "Read result aloud"}
      style={{
        display:        "flex",
        alignItems:     "center",
        gap:            6,
        padding:        "6px 12px",
        borderRadius:   8,
        border:         `1px solid ${speaking ? "#22d3a044" : "#232a3a"}`,
        background:     speaking ? "#22d3a011" : "#0a0c10",
        color:          speaking ? "#22d3a0"   : "#6b7591",
        cursor:         "pointer",
        fontSize:       11,
        fontFamily:     "var(--font-mono)",
        transition:     "all 0.2s",
      }}
    >
      {speaking ? <VolumeX size={13} /> : <Volume2 size={13} />}
      {speaking ? "Stop" : "Read aloud"}
    </button>
  );
}
