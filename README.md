# Gemini Chatbot API

FastAPI service for OLP AI with a cumulative input + output limit of 2,000 conversation tokens. Conversations and messages are persisted in SQLite.

The assistant has a fixed system instruction identifying it as OLP AI, an assistant for answering questions and writing, explaining, reviewing, and debugging code for OLP AI problems. For code requests it gives a short approach explanation before the code and avoids long tutorials unless requested. This instruction is sent separately through Gemini's `system_instruction`, is not saved in conversation history, and is excluded from the local 2,000-token conversation budget.

## Run

```bash
cd /home/thanglm2006/gemini-chat-limited
source /home/thanglm2006/venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

OpenAPI documentation: <http://127.0.0.1:8000/api-docs>

Temporary test frontend: <http://127.0.0.1:8000/>

## Endpoints

- `GET /health`
- `GET /api-docs`
- `GET /api-docs/openapi.json`
- `GET /api/v1/config`
- `PUT /api/v1/settings/api-key` (requires `X-API-Key-Password`)
- `POST /api/v1/chat` (creates a conversation when `conversation_id` is omitted)
- `POST /api/v1/conversations`
- `GET /api/v1/conversations`
- `GET /api/v1/conversations/{id}`
- `DELETE /api/v1/conversations/{id}`
- `DELETE /api/v1/conversations/{id}/messages` (clear and reset token usage)
- `GET /api/v1/conversations/{id}/messages`
- `POST /api/v1/conversations/{id}/messages`

Example:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Xin chao"}'
```

Set `GEMINI_MODEL` in `.env` if the model name enabled for your Google AI Studio project is different. Never commit `.env` because it contains the API key.

## Docker Compose

```bash
docker compose up --build -d
```

The API is then available at <http://127.0.0.1:8000>. SQLite data is stored in the named `chatbot_data` volume.

`POST /api/v1/chat` without `conversation_id` creates a new UUID conversation and stores the request there. To continue an existing conversation, send its returned `conversation.id` in the next request. Messages from different conversation IDs are isolated by the database foreign key and query filter.

When a conversation reaches its 2,000-token budget, the remaining output is capped to the available amount. If the next input itself cannot fit, the API returns `429` and does not write that message to the database. A different conversation has its own independent budget.

The API key is stored in exactly one SQLite row (`api_keys.id = 1`). It is seeded from `.env` on first startup and can only be updated, never deleted. The update password is read from `API_KEY_UPDATE_PASSWORD` in `.env`; the response returns only a masked key.

Update the key:

```bash
curl -X PUT http://127.0.0.1:8000/api/v1/settings/api-key \
  -H "X-API-Key-Password: $API_KEY_UPDATE_PASSWORD" \
  -H "Content-Type: application/json" \
  -d '{"api_key":"new-gemini-api-key"}'
```

