# 🧠 Company Brain

> **Your company's AI Chief of Staff.** You talk to one Boss — it runs a whole office of 9 specialist agents for you, live on a pixel-art office floor. 👩‍💼🏢

Built on [Agno Framework v2](https://github.com/agno-agi/agno) · Models: Google Gemini 🇬 + Groq Llama 3.3 ⚡ (+ optional Mistral)

---

## ✨ What can it do?

| | |
|---|---|
| 💼 **Lead qualification** — score leads HOT/WARM/COLD, draft first replies |
| 🤝 **Pricing & negotiation** — 3 options prepared, *you* approve before anything is sent |
| 💰 **Finance** — invoices, payments, cashflow summaries |
| ⚖️ **Legal** — contract review with risk flags (HIGH/CRITICAL escalated instantly) |
| 💡 **Idea pipeline** — raw idea → research → polished pitch |
| 🔭 **Market research** — competitors & trends via web search |
| 📋 **Daily briefings** — morning status of the whole company |
| 🏢 **Live office floor** — watch your agents actually walk, work & hand off work in real time |

## 🚀 Quick start

### Option A — Full experience (Docker) ⭐ recommended

```bash
cp example.env .env        # add GOOGLE_API_KEY (free: aistudio.google.com)
docker compose up -d --build
```

Then open:

- 🏢 **Office Floor**: http://localhost:8000/floor — chat with the Chief and watch the office react
- ⚙️ **AgentOS API/UI**: http://localhost:8000

### Option B — Terminal only (no Docker)

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows
# .venv/bin/pip install -r requirements.txt               # macOS/Linux

cp example.env .env
.venv/Scripts/python -m app.chat
```

Type to the Top Agent · `exit` quits · memory stored in `data/companybrain_memory.db`

---

## 🏗️ Architecture

```mermaid
flowchart TD
    subgraph YOU
        U[👤 You - Owner]
    end

    subgraph CLIENTS["Interfaces (browser)"]
        FLOOR["🏢 Office Floor UI<br/>localhost:8000/floor<br/>Pixi.js avatars + chat box"]
        AGENTOS["⚙️ AgentOS API/UI<br/>localhost:8000"]
        CLI["💻 Terminal chat<br/>app/chat.py"]
    end

    subgraph SERVER["Docker: company-brain-app :8000"]
        direction TB
        subgraph API_LAYER["FastAPI / AgentOS"]
            REST["POST /teams/company-brain/runs"]
            WS["WS /ws/agent-status<br/>+ GET /api/agent-status/snapshot"]
            HOOK["POST /webhook/whatsapp<br/>(Twilio)"]
        end

        subgraph BRAIN["The Brain — Agno Team (coordinate mode)"]
            TOP["👩‍💼 TOP AGENT<br/>Chief of Staff (Gemini)"]
            subgraph SPECIALISTS["9 Specialists"]
                S1["📈 Sales"]:::spec
                S2["🧾 Onboarding"]:::spec
                S3["🤝 Negotiation"]:::spec
                S4["💰 Finance"]:::spec
                S5["⚖️ Legal"]:::spec
                S7["✍️ Refinement"]:::spec
                S8["🔭 Research"]:::spec
                S9["🗺️ Strategy"]:::spec
                S10["📋 Briefing"]:::spec
            end
        end

        subgraph TELEMETRY["Live event bus"]
            INST["instrument_agent()<br/>wraps every agent.run()"]
            BUS["AgentActivityBus<br/>working / idle / handoff events"]
        end

        subgraph PROVIDERS["Providers (ContextProvider)"]
            P1["Gmail"]:::prov
            P2["Twilio WhatsApp"]:::prov
            P3["Web search"]:::prov
            P4["Memory tools"]:::prov
        end

        MEM[("🗄️ SuperMemory<br/>5 layers: working · client vaults ·<br/>semantic · playbooks · audit")]
        WF["Workflows:<br/>Lead Conversion · Pricing Request · Daily Briefing"]
    end

    subgraph INFRA["Docker: company-brain-db"]
        PG[("🐘 Postgres + pgvector<br/>sessions · knowledge")]
    end

    subgraph LLM["LLM Providers"]
        G["Google Gemini 🇬<br/>(all agents)"]
        GR["⚡ Groq Llama 3.3<br/>(auto-fallback for 6 agents)"]
    end

    U -->|"task"| FLOOR
    U --> AGENTOS
    U --> CLI
    FLOOR -->|"POST /runs"| REST
    AGENTOS --> REST
    CLI --> TOP
    HOOK --> TOP
    REST --> TOP

    TOP -->|"delegates"| SPECIALISTS
    SPECIALISTS -->|"result"| TOP
    TOP -->|"final answer"| REST
    REST -->|"JSON"| FLOOR

    SPECIALISTS -.-> P1 & P2 & P3 & P4
    BRAIN <--> MEM
    WF --> BRAIN
    TOP & SPECIALISTS --> G
    SPECIALISTS -.->|if key set| GR

    INST -.->|"every run"| BUS
    BUS -->|"live events"| WS
    WS -->|"avatar moves"| FLOOR
    WS -->|"snapshot on load"| FLOOR

    API_LAYER --- PG

    classDef spec fill:#2d1f1a,stroke:#d9a441,color:#f0e6d8
    classDef prov fill:#1d2a24,stroke:#7fb069,color:#f0e6d8
```

### How a request flows 🔁

1. 💬 You send a task (floor chat / AgentOS / terminal / WhatsApp)
2. 👩‍💼 The **Top Agent** analyzes it — you never talk to specialists directly *(rule #1)*
3. 📈 It delegates to the right specialist(s), who use their tools + memory
4. 📨 On every delegation an event fires → on the floor, the Boss walks to the **conference table**, the specialist is summoned, an envelope flies 💌
5. ✅ The specialist walks to a work station (web portal / terminal / task board…), works, carries the artifact back to its desk
6. 🧾 Every action is logged to the audit trail; you get one clean summary

---

## 👥 The Team — meet the agents

| Agent | Emoji | Role | Model |
|---|---|---|---|
| **Top Agent** | 👩‍💼 | Chief of Staff — routes everything, escalates, summarizes | Gemini |
| **Sales Agent** | 📈 | Qualify & score leads (fit/budget/timing/authority), draft replies | Gemini/Groq |
| **Onboarding Agent** | 🧾 | New client checklists, credential gathering, vault setup | Gemini |
| **Negotiation Agent** | 🤝 | Pricing options & deal structuring — **owner approval required** | Gemini/Groq |
| **Finance Agent** | 💰 | Invoices, payment tracking, cashflow, overdue flags | Gemini/Groq |
| **Legal Agent** | ⚖️ | Contract review & risk flags (risk assessment ≠ legal advice) | Gemini/Mistral |
| **Refinement Agent** | ✍️ | Polish ideas into pitches, briefs, content | Gemini/Mistral |
| **Market Research Agent** | 🔭 | Competitors, trends, benchmarks (web search) | Gemini/Groq |
| **Strategy Agent** | 🗺️ | Campaigns, growth roadmaps, content strategy | Gemini/Groq |
| **Briefing Agent** | 📋 | Daily/weekly company summaries | Gemini/Groq |

➕ **Client Agents** — a dedicated agent spawned per client on conversion, isolated to its own vault.

## 🧠 SuperMemory (5 layers)

| Layer | Purpose |
|---|---|
| 🔄 Working Memory | Active tasks & conversations |
| 🔐 Client Vaults | Per-client isolated history — strict separation |
| 🔎 Semantic Memory | Vector search (pgvector locally, Vertex AI on GCP) |
| 📘 Playbook Memory | Rate cards & SOPs (`data/playbooks/`) |
| 🧾 Audit & Learning | Every agent action logged |

## 🛡️ Guardrails (non-negotiable)

1. 👩‍💼 The Top Agent is the **only** interface to the owner
2. 🔐 Strict client-data isolation via vaults
3. 💰 All pricing/deal terms require **explicit owner approval**
4. 🧾 Full audit trail of every action
5. 🤖 Models: Gemini + Groq (+ optional Mistral) only

## 🌍 Environment variables

See [`example.env`](example.env):

| Key | Required? | Notes |
|---|---|---|
| `GOOGLE_API_KEY` | ✅ minimum | Free at [aistudio.google.com](https://aistudio.google.com) |
| `GROQ_API_KEY` | ➕ recommended | Bigger free tier; auto-used by 6 agents |
| `MISTRAL_API_KEY` | optional | Legal + Refinement |
| `TWILIO_*` + `OWNER_NUMBER` | optional | WhatsApp control |
| `GMAIL_*` | optional | Email tools |
| `DATABASE_URL` | Docker only | Defaults to local Postgres |

## 📁 Project structure

```
app/
├── main.py              # AgentOS entry point + webhooks + floor serving
├── chat.py              # 💻 terminal chat with the Chief
├── config.py            # env configuration
├── floor.py             # office-floor landing page
├── agents/              # 👥 the 10 agents
├── teams/               # team wiring + instrumentation
├── workflows/           # lead conversion · pricing · briefing
├── memory/              # 🧠 SuperMemory (5 layers)
├── providers/           # Gmail · Twilio · Web · Memory (ContextProvider)
├── models/              # Gemini / Groq / Mistral helpers
└── telemetry/           # 🎥 live event bus + floor desk map
office-floor-widget/     # 🏢 Pixi.js office floor (React + Vite)
data/playbooks/          # rate cards & SOPs
```

## 📜 Fixes over upstream

- `requirements.txt`: added missing `openai` + `google-genai`
- Deprecated `gemini-1.5-pro`/`2.0-flash` → current Gemini Flash
- WhatsApp webhook mounted on the same port as AgentOS (single server)
- Team registered correctly under AgentOS (`teams=` + explicit id + model)
- Providers upgraded to Agno's real `ContextProvider` lifecycle
- Groq/Mistral gracefully fall back to Gemini when keys are absent

---

<p align="center">🧠 <i>One brain. Ten agents. Infinite leverage.</i></p>
