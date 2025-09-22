# Ask My Race – Frontend

Next.js App Router UI for uploading triathlon athlete guides and chatting with the LangChain-powered FastAPI backend.

## Prerequisites

- Node.js 18+
- Backend API running locally (default: `http://127.0.0.1:8000`)

## Environment variables

Create `.env.local` with the backend URL:

```
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

Vercel: add the same variable in Project Settings → Environment Variables.

## Development

```bash
npm install
npm run dev
```

Visit http://localhost:3000 and upload a PDF athlete guide to start chatting.

## Linting & build

```bash
npm run lint
npm run build
```

## Deployment notes

- Deploy the frontend on Vercel with the default `npm run build` command.
- Point `NEXT_PUBLIC_API_BASE_URL` to the publicly accessible FastAPI deployment.
- Optional: wire a `/examples` API endpoint in the backend to populate the “Quick prompts” sidebar with hosted sample guides.
