// Server Component — intentionally minimal.
// Metadata  → layout.tsx
// CSS vars  → globals.css
// All UI    → QuantumCommandCenter (Client Component)

import QuantumCommandCenter from "@/components/QuantumCommandCenter";

export default function HomePage() {
  return <QuantumCommandCenter />;
}