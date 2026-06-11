<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

# Frontend console for the RAG Agent system

This workspace is the frontend control console for the larger RAG Agent system. It is a Next.js 16 + React 19 + TypeScript app that provides the UI and API proxy layer for the backend and Gateway services.

## What this app is responsible for

- Presenting login, registration, dashboard, admin console, and knowledge/task status UI.
- Proxying API requests to the backend service and gateway via `src/app/api/_lib/proxy.ts`.
- Managing auth cookies and redirect flows for front-end routes.
- Displaying chat history, ingestion jobs, knowledge upload, and QA logs.

## What this app is not responsible for

- It does not implement core RAG retrieval, vector store, or model orchestration logic.
- It does not own backend business or knowledge ingestion rules; those live in the backend service and Gateway.
- It is primarily a presentation/coordination layer.

## Important commands

- `pnpm install`
- `pnpm dev --port 3001`
- `pnpm build`
- `pnpm start --port 3001`
- `pnpm lint`

## Key environment config

Copy `.env.example` to `.env.local` and set:

- `BACKEND_BASE_URL` (default: `http://127.0.0.1:8877`)
- `GATEWAY_BASE_URL` (default: `http://127.0.0.1:8765/gateways/rag_kefu_gateway`)

The frontend expects the backend service and Gateway runner to be available during local development.

## Core directories

- `src/app/` - Next.js App Router pages, layouts, and route handlers.
- `src/app/api/` - API route proxies and auth endpoints.
- `src/app/_lib/` - shared server helpers such as proxy wrappers and auth session utilities.
- `src/app/ui/` - reusable UI components.
- `src/app/admin/` - admin dashboard views.
- `src/app/login/`, `src/app/register/` - auth pages.

## Proxy and auth patterns

- `src/app/api/_lib/proxy.ts` contains `backendFetch`, `backendJson`, `backendJsonWithAuth`, and `gatewayJson`.
- Auth cookies are set via `AUTH_COOKIE_NAME = ft_session` in `src/app/api/auth/login/route.ts`.
- Use the provided proxy helpers rather than creating duplicate backend fetch logic.

## Recommended behavior for AI agents

- Prefer small, targeted edits instead of broad refactors in this UI-only repository.
- If a change affects business behavior, check if it should be made in the backend service instead.
- Preserve Next.js app router conventions: `route.ts`, `page.tsx`, server/client boundaries, and `use client` directives.
- Do not assume the frontend owns model or retrieval logic; validate against backend service APIs.

## Reference docs

- `README.md` for developer startup and architecture notes.
- `next.config.ts` and `tsconfig.json` for build/runtime configuration.

