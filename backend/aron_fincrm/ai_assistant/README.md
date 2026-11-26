# AI Assistant

The assistant is a read-only, role-scoped chat endpoint for the CRM. It sends only an allowlisted set of summaries and recent or question-matching records from the authenticated user's organization and hierarchy scope to the configured AI provider. Customer phone numbers, email addresses, addresses, notes, and raw financial JSON are excluded.

Supported CRM data includes customers, leads, tasks, follow-ups, repayment schedules, and repayment payments. Organization administrators also receive their active subscription plan, billing dates, staff-account and lead limits, and current usage so the assistant can answer plan and remaining-capacity questions. Subscription details are not sent for staff or lead-portal roles. Summaries cover all records in the user's scope; the request includes at most eight matching or recent records per type.

Configure an OpenAI-compatible chat-completions endpoint in `backend/aron_fincrm/.env`:

```dotenv
AI_ASSISTANT_API_URL=https://your-provider.example/v1/chat/completions
AI_ASSISTANT_API_KEY=your-provider-key
AI_ASSISTANT_MODEL=your-model-name
AI_ASSISTANT_TIMEOUT=30
```

The aliases `AI_API_URL` / `AI_URL` / `API_URL` / `URL`, `AI_API_KEY` / `AI_API` / `API_KEY` / `API`, and `AI_MODEL` / `MODEL` are also accepted. The usual `OPENAI_BASE_URL`, `OPENAI_API_KEY`, and `OPENAI_MODEL` names work too. Existing process environment variables take precedence over values in `.env`.

Install the backend dependencies with `python -m pip install -r requirements.txt` from `backend/aron_fincrm`, then restart Django. The API key stays on the backend.

## API

`POST /api/v1/ai-assistant/chat/` (JWT or session authentication)

```json
{
  "question": "How many of my customers are under review?",
  "history": [
    {"role": "user", "content": "Show my lead summary"},
    {"role": "assistant", "content": "You have 4 active leads."}
  ]
}
```

The optional history is limited to eight short user or assistant messages. The app is read-only and never executes model-generated SQL or model-selected tool calls.

## Interface help knowledge

UI questions such as “Where is Generate Repayment Schedule?” are routed to the source-synchronized `ui_knowledge` catalog. Ordinary CRM data questions continue to use the existing tenant-scoped data context. The interface catalog records module IDs (this application is a state-driven SPA, not a browser-route-based app), sidebar and tab hierarchy, component evidence, actions, form fields, and role visibility rules. The server gets the user’s organization and role from the authenticated request and checks access before creating an answer; the client cannot provide a role or user ID to override that check.

After adding or changing frontend pages and controls, run from `backend/aron_fincrm`:

```powershell
python manage.py migrate ui_knowledge
python manage.py sync_ui_knowledge
```

Pass `--frontend-root <path>` if a project contains more than one React source tree. Use `--full` to record an explicit full sync. The command hashes source so unchanged entries are not rewritten. It deactivates removed entries only after it has completed a successful source scan and database transaction; a scan failure leaves the last good catalog intact. Each run is recorded in Django admin under UI sync runs. Feature descriptions remain source-derived and are flagged as requiring verification until reviewed; the configured LLM is used at answer time only with the authenticated user’s matched, permission-approved source evidence.
