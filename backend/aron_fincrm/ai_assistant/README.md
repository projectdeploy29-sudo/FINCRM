# AI Assistant

The assistant is a read-only, role-scoped chat endpoint for the CRM. It sends only an allowlisted set of summaries and recent or question-matching records from the authenticated user's organization and hierarchy scope to the configured AI provider. Customer phone numbers, email addresses, addresses, notes, and raw financial JSON are excluded.

Supported CRM data includes leads, customers, financial applications, tasks, follow-ups, repayment schedules, and repayment payments. Summaries cover all records in the user's scope; the request includes at most eight matching or recent records per type.

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
  "question": "How many of my applications are awaiting review?",
  "history": [
    {"role": "user", "content": "Show my application summary"},
    {"role": "assistant", "content": "You have 4 applications."}
  ]
}
```

The optional history is limited to eight short user or assistant messages. The app is read-only and never executes model-generated SQL or model-selected tool calls.
