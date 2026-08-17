# Company Brain — Architecture Guide

## Overview
Company Brain is a multi-agent AI system built on top of Agno Scout and the Agno Framework v2.
It serves as an intelligent business assistant with specialized agents for sales, client management,
negotiation, finance, legal, idea development, and strategic thinking.

## Architecture

### Single Entry Point
The **Top Agent** (Chief of Staff) is the ONLY agent the owner interacts with.
All requests flow: Owner → Top Agent → Specialist Agent → Top Agent → Owner.
Agents never talk to each other directly — they write to SuperMemory.

### Agent Roster (Week 1 — Foundation)
| Agent | Model | Role |
|-------|-------|------|
| Top Agent | Gemini Pro | Orchestrator. Routes everything, collects status, escalates to owner |
| Sales Agent | Groq Llama 3.3 70B | Qualify leads, score, draft first replies, manage pipeline |

### Agent Roster (Full — Weeks 2-5)
| Agent | Model | Role |
|-------|-------|------|
| Top Agent | Gemini Pro | Orchestrator |
| Sales Agent | Groq Llama 3.3 70B | Lead qualification & scoring |
| Client Agent | Gemini Flash | Per-client relationship owner |
| Negotiation Agent | Gemini Pro | Pricing & deal structuring |
| Finance Agent | Groq Llama 3.3 70B | Invoices & payments |
| Legal Agent | Mistral Large | Contract review |
| Idea Agent | Gemini Flash | Capture raw ideas |
| Refinement Agent | Mistral Large | Turn ideas into briefs |
| Market Research Agent | Groq Llama 3.3 70B | Competitor & trend research |
| Onboarding Agent | Gemini Flash | New client setup |
| Briefing Agent | Groq Llama 3.3 70B | Daily/weekly summaries |
| Strategy Agent | Gemini Pro | Campaign thinking |

## SuperMemory (5 Layers)
1. **Working Memory** — Active tasks & conversations
2. **Client Vaults** — Per-client isolated history (strict separation)
3. **Semantic Memory** — Vector search (PgVector locally, Vertex AI on GCP)
4. **Playbook Memory** — Rate cards, SOPs, winning patterns
5. **Audit & Learning** — Full action log (every action is tracked)

## Key Patterns

### Provider Pattern (from Agno Scout)
Each data source is wrapped in a Provider class with:
- `get_tools()` → list of tool functions for agents
- `get_instructions()` → system instructions for agents
- `is_available()` → check if required config is present

### Memory Backend Abstraction
- `MemoryBackend` (abstract) → `LocalBackend` (SQLite) or `GCPBackend` (Firestore/BigQuery)
- Swap via `MEMORY_BACKEND=local|gcp` environment variable
- No code changes needed when migrating to GCP

## Project Structure
```
app/
├── main.py              # AgentOS entry point + webhook endpoints
├── config.py            # Environment configuration
├── models/              # LLM helpers (Groq, Gemini, Mistral)
├── agents/              # Individual agent definitions
├── teams/               # Team compositions
├── workflows/           # Deterministic multi-step workflows
├── memory/              # SuperMemory system
├── providers/           # Context providers (Telnyx, Gmail, Web, Memory)
data/playbooks/          # Rate cards, SOPs
```

## Development

### Local Setup
```bash
cp example.env .env
# Fill in your API keys
docker compose up -d --build
# Open http://localhost:8000 for AgentOS Web UI
```

### Key Environment Variables
- `GROQ_API_KEY` — Groq API (Llama 3.3 70B)
- `GOOGLE_API_KEY` — Gemini API (Flash/Pro)
- `MISTRAL_API_KEY` — Mistral API
- `TELYNX_API_KEY` — Telnyx WhatsApp API
- `DATABASE_URL` — PostgreSQL connection

## Non-Negotiables
1. Built on Agno Scout ContextProvider pattern
2. Top Agent is the ONLY user interface
3. Strict client data isolation via Client Vaults
4. All pricing/negotiation requires owner approval
5. Full audit trail of every agent action
6. Models: Groq + Gemini + Mistral ONLY
