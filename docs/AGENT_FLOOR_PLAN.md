# AgentOS + Agent Floor Integration

## Product flow

- `http://localhost:3000` is the main self-hosted Agent UI.
- The Agent UI connects to the Company Brain AgentOS API at `http://localhost:8000`.
- The Agent UI sidebar has an **Open Agent Floor** button.
- The button opens `http://localhost:8000/floor` in a new tab.
- AgentOS remains the source of truth for execution, sessions, memory, and workflows.
- The Agent Floor is a presentation layer and must not become a second orchestrator.

## Completed

- Mounted the Company Brain FastAPI routes into AgentOS with `base_app`.
- Registered Company Brain agents and the Company Brain team with AgentOS.
- Added `/floor` visual presentation page.
- Added `/api/floor/state` roster endpoint.
- Added `/api/floor/events` Server-Sent Events endpoint.
- Added dynamic client-agent roster display.
- Added self-hosted Agno Agent UI under `frontend/agent-ui`.
- Added the Agent UI sidebar button.
- Added the Agent UI Docker service to Compose.
- Added explicit `python-multipart` and `httpx` dependencies.
- Corrected Twilio webhook response types.

## Next phases

1. Start Docker Desktop and run the full Compose stack.
2. Verify Agent UI chat against the real PostgreSQL-backed AgentOS API.
3. Add AgentOS run/trace event translation so floor cards show real working/tool/error states.
4. Add workflow progress, approval, and audit panels to the floor.
5. Add authentication and production CORS configuration.
6. Add automated backend and frontend tests.
7. Add real Twilio signature validation and end-to-end webhook tests.
8. Review Munder Difflin asset licensing before reusing any artwork.

## Local commands

```powershell
Copy-Item example.env .env
# Fill in GOOGLE_API_KEY, GROQ_API_KEY, and MISTRAL_API_KEY

docker compose up --build
```

Open:

- Agent UI: `http://localhost:3000`
- AgentOS API docs: `http://localhost:8000/docs`
- Agent Floor: `http://localhost:8000/floor`
