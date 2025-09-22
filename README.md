# Ask My Race

Ask My Race lets athletes upload a triathlon race guide, ask natural language questions, and receive answers grounded in the source PDF with page-level citations. The project is split into two deployable parts:

- **backend/** – FastAPI service that ingests PDFs, builds LangChain retrieval indexes, and answers questions via OpenAI.
- **frontend/** – Next.js (App Router) UI built for Vercel that handles PDF upload, demo guide selection, and chat-style Q&A. 

### Visit the live app at https://ask-my-race.vercel.app/.

## Features

- PDF parsing with chunk metadata (section titles + page numbers).
- LangChain RAG pipeline using OpenAI embeddings + chat models.
- In-memory document registry for quick iteration; easy to swap for a persistent store later.
- React Query powered UI with upload progress, demo guides, and citation chips.
- Demo library automatically surfaces PDFs from `race_examples/` for one-click testing.
- Safety guardrails: file size limits, triathlon keyword heuristics, prompt-abuse filtering, and rate limiting.

## Requirements

- Python 3.11+
- Node.js 18+
- OpenAI API key (set in backend `.env`)

## Backend (FastAPI + LangChain)

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt

# set environment variables
cp .env.example .env
# update OPENAI_API_KEY and optional model overrides

uvicorn backend.app.main:app --reload
```

API endpoints:

- `POST /upload` – upload a PDF (≤80 MB), receive a `document_id`.
- `POST /ask` – submit `{ document_id, question }`, returns answer + citations.
- `GET /examples` – list bundled demo guides from `race_examples/`.
- `POST /examples/{slug}` – load a demo guide without uploading manually.
- `GET /health` – simple health probe.

## Frontend (Next.js)

```bash
cd frontend
npm install
cp .env.local.example .env.local  # adjust NEXT_PUBLIC_API_BASE_URL if backend not on localhost
npm run dev
```

Visit http://localhost:3000 to upload a PDF or pick a demo guide and start asking questions.

### Lint & build

```bash
npm run lint
npm run build
```

Deploy the frontend to Vercel with `npm run build`. Remember to set `NEXT_PUBLIC_API_BASE_URL` in Vercel project settings to the deployed FastAPI URL.

## Demo Guides

Place PDF files in `race_examples/`. They are exposed via the backend’s `/examples` endpoints and rendered in the frontend sidebar for quick demos.

## Safety & Guardrails

- Question input trimmed to 500 characters with banned-pattern filters for prompt injection attempts.
- Backend rate limiting on uploads and questions per IP.
- File size enforced at 80 MB with simple triathlon keyword heuristics (rejects obviously unrelated PDFs).
- System prompt reminds the model to ignore malicious instructions inside PDF excerpts.
