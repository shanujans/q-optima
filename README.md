# ⚛️ Q-Optima — Autonomous Quantum Logistics Agent

> **Milan AI Week 2026 · AI Agent Olympics**  
> Tracks: Intelligent Reasoning · Enterprise Agent · Speechmatics Sponsor Prize

[![Live Demo](https://img.shields.io/badge/Live%20Demo-q--optima.vercel.app-00C8FF?style=flat-square)](https://q-optima.vercel.app)
[![Backend](https://img.shields.io/badge/Backend-Render-A855F7?style=flat-square)](https://q-optima-backend.onrender.com/api/health)
[![License](https://img.shields.io/badge/License-MIT-22D3A0?style=flat-square)](LICENSE)

---

## What is Q-Optima?

Q-Optima is a **multi-cloud autonomous AI agent** that solves NP-Hard logistics optimization problems using **Quantum Computing**. A logistics commander speaks a voice instruction, uploads a route map, and within 30 seconds receives a quantum-optimized delivery route — enriched with real-time weather, traffic, and carbon data — delivered to their phone via Telegram.

```
🎙 Speak constraint  →  📸 Upload map  →  ⚛️ Quantum solve  →  📍 Optimal route  →  📱 Dispatch alert
```

---

## Architecture — Multi-Cloud Agentic Mesh

```
┌─────────────────┐     ┌──────────────────────────────────────────┐     ┌──────────────────┐
│  Vercel         │────▶│  Render — FastAPI + LangGraph (7 nodes)  │────▶│  IBM Quantum     │
│  Next.js 14     │     │                                          │     │  QAOA / Aer      │
│  Leaflet map    │     │  ┌──────────┐  ┌──────────┐             │     └──────────────────┘
│  WebSocket UI   │     │  │Speechmatics│ │Gemini 2.5│             │
└─────────────────┘     │  │ STT      │  │ Vision   │             │
                        │  └──────────┘  └──────────┘             │
                        │  ┌──────────┐  ┌──────────┐             │
                        │  │Open-Meteo│  │ TomTom   │             │
                        │  │ Weather  │  │ Traffic  │             │
                        │  └──────────┘  └──────────┘             │
                        │  ┌──────────┐  ┌──────────┐             │
                        │  │ Climatiq │  │ Telegram │             │
                        │  │ Carbon   │  │ Dispatch │             │
                        │  └──────────┘  └──────────┘             │
                        └──────────────────────────────────────────┘
                                      │
                        ┌─────────────▼────────────┐
                        │  AMD Dev Cloud           │
                        │  Whisper ROCm (GPU STT)  │
                        │  via Cloudflare Tunnel   │
                        └──────────────────────────┘
```

---

## LangGraph Pipeline — 7 Autonomous Nodes

```
Speechmatics STT → Gemini Vision → Enrich (OSRM+Weather+Traffic+Carbon)
→ Build QAOA Circuit → Execute IBM Quantum → Self-Reflect → Parse+Finalize
          ↑                                        │
          └─────── retry with p+1 if quality fails ┘
```

**Node 6 — Self-reflection loop:** The agent autonomously checks if the quantum result is a valid permutation and if confidence exceeds the threshold. If not, it increases QAOA layers and retries — no human intervention.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 14 (App Router), Tailwind, Framer Motion, Leaflet.js |
| Orchestrator | FastAPI, LangGraph, Python 3.11 |
| Primary STT | **Speechmatics** batch + RT transcription API |
| Vision AI | Google Gemini 2.5 Flash Lite (multimodal) |
| Quantum | IBM Quantum / Qiskit QAOA, Aer simulator |
| AMD GPU | OpenAI Whisper on ROCm PyTorch (perception node) |
| Road data | OSRM public API (real driving distances) |
| Weather | Open-Meteo API (zero cost, no key) |
| Traffic | TomTom Flow Segment Data API |
| Carbon/ESG | Climatiq freight emission API |
| Dispatch | Telegram Bot API |
| Analytics | Supabase PostgreSQL (job history) |
| Hosting | Vercel (frontend) + Render (backend) + AMD Dev Cloud |
| Tunneling | Cloudflare Tunnel (free HTTPS) |

**Total cost: $0.00 out of pocket.**

---

## QUBO Enrichment Model

The quantum distance matrix is not just geographic — it encodes real-world constraints:

```
Enriched distance[i][j] =
    OSRM road distance (km)
  + weather penalty     (Open-Meteo WMO severity × max_penalty)
  + traffic penalty     (TomTom congestion ratio × max_penalty)
  + carbon penalty      (Climatiq CO₂e × cost_weight)
```

QAOA minimizes this enriched matrix — simultaneously optimizing for distance, weather safety, congestion, and carbon footprint in a single quantum pass.

---

## Project Structure

```
q-optima/
├── frontend/                    # Next.js 14 — Vercel
│   ├── app/
│   │   ├── globals.css
│   │   ├── layout.tsx
│   │   ├── page.tsx
│   │   └── components/
│   │       ├── QuantumCommandCenter.tsx
│   │       ├── AgentTimeline.tsx
│   │       └── VoiceOutput.tsx
│   └── package.json
├── backend_vultr/               # FastAPI + LangGraph — Render
│   ├── main.py
│   ├── agent/
│   │   ├── graph.py             # 7-node StateGraph with reflection loop
│   │   ├── nodes/
│   │   │   ├── speechmatics_node.py
│   │   │   ├── gemini_node.py
│   │   │   ├── qiskit_node.py
│   │   │   ├── ibm_quantum_node.py
│   │   │   └── reflection_node.py
│   │   └── tools/
│   │       ├── osrm_tool.py
│   │       ├── weather_tool.py
│   │       ├── traffic_tool.py
│   │       ├── carbon_tool.py
│   │       ├── telegram_tool.py
│   │       └── supabase_tool.py
│   ├── models/schemas.py
│   └── utils/
│       ├── qubo_parser.py
│       └── classical_comparison.py
├── backend_amd/                 # Whisper ROCm — AMD Dev Cloud
│   ├── whisper_service.py
│   └── Dockerfile
└── docker-compose.yml
```

---

## Setup

### Prerequisites
- Python 3.11
- Node.js 18+
- API keys (see `.env.example`)

### Local Development

```bash
# Clone
git clone https://github.com/YOUR_USERNAME/q-optima.git
cd q-optima

# Backend
cd backend_vultr
cp .env.example .env        # fill in your API keys
pip install -r requirements_vultr.txt
uvicorn main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
npm install
echo "NEXT_PUBLIC_BACKEND_URL=http://localhost:8000" > .env.local
npm run dev
```

Open `http://localhost:3000` → click **Run Quantum Agent**.

### Required API Keys

| Key | Source | Cost |
|---|---|---|
| `GEMINI_API_KEY` | [aistudio.google.com](https://aistudio.google.com/app/apikey) | Free |
| `SPEECHMATICS_API_KEY` | [portal.speechmatics.com](https://portal.speechmatics.com) | $200 credit |
| `IBM_QUANTUM_TOKEN` | [quantum.ibm.com](https://quantum.ibm.com) | Free |
| `TOMTOM_API_KEY` | [developer.tomtom.com](https://developer.tomtom.com) | Free 2500/day |
| `CLIMATIQ_API_KEY` | [climatiq.io](https://www.climatiq.io/signup) | Free 1000/mo |
| `TELEGRAM_BOT_TOKEN` | [@BotFather](https://t.me/BotFather) | Free |
| `SUPABASE_URL` + `SUPABASE_ANON_KEY` | [supabase.com](https://supabase.com) | Free |

No-key APIs: Open-Meteo, OSRM, Leaflet/OSM, Web Speech API.

---

## Deployment

### Backend (Render)
```
render.com → New Web Service → Connect GitHub
Root Directory: backend_vultr
Build: pip install -r requirements_vultr.txt
Start: uvicorn main:app --host 0.0.0.0 --port $PORT
Add all env vars from .env.example
```

### Frontend (Vercel)
```
vercel.com → Import repo
Root Directory: frontend
NEXT_PUBLIC_BACKEND_URL = https://your-render-url.onrender.com
```

---

## Judging Criteria Coverage

| Criterion | How Q-Optima addresses it |
|---|---|
| **Originality** | First agent combining multimodal LLM + quantum computing for real enterprise logistics |
| **Application of Technology** | 14 real APIs, Speechmatics as primary STT, IBM QAOA, LangGraph self-reflection |
| **Business Value** | Carbon scoring, classical vs quantum comparison %, Telegram dispatch, Supabase analytics |
| **Presentation** | Live Vercel URL, animated agent timeline, voice output, Telegram demo moment |

---

## License

MIT — built for Milan AI Week 2026 AI Agent Olympics.
