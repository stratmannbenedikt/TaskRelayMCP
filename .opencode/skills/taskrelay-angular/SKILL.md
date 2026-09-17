---
name: taskrelay-angular
description: Use when creating, changing, testing, or reviewing TaskRelay's Angular frontend under frontend/, including routes, forms, API calls, inspection mode, static builds, and frontend dependencies.
---

# TaskRelay Angular

Follow `agent-docs/decisions/0003-angular-client-side-application.md` and preserve the REST contracts in `src/taskrelaymcp/api.py` and `schemas.py`.

## Architecture

- Keep the application client-side rendered. FastAPI is the only production server.
- Use supported Angular 21 LTS facilities: standalone components, Router, `HttpClient`, reactive forms, and signals.
- Keep business rules, validation, authentication, and authorization authoritative in FastAPI. Guards and hidden controls are UX only.
- Put shared transport/authentication/inspection state in `frontend/src/app/core/`; pages belong in `frontend/src/app/pages/`; add shared components only after real reuse.
- Prefer Angular and browser APIs. Do not add NgRx, SSR, hydration, a service worker, a CSS/component framework, Axios, or another state/form/router library without explicit approval.

## HTTP and security

- Send same-origin requests through `ApiService`; do not call `HttpClient` directly from pages.
- Preserve cookie credentials and central FastAPI `{detail}` error normalization.
- Send `X-TaskRelay-Inspection` on normal API requests. Inspection mode is read-only.
- Logout must bypass the inspection marker and clear local inspection state so the next login works.
- Never store passwords, sessions, or MCP secrets in browser storage. Show newly generated MCP keys once.

## UI behavior

- Use reactive forms with controls constrained to backend enums and validation limits.
- Keep archived projects non-writable in the UI.
- Preserve owner/member controls, assignment eligibility, immutable DONE tasks, attribution, and mandatory-password-change routing.
- Use semantic elements, explicit labels, visible focus, keyboard-capable dialogs, and responsive CSS.
- Keep theming in CSS custom properties; framework migrations and theme redesigns are separate changes.

## Build and checks

- Keep `package-lock.json`; use `npm ci`, not `npm install`, for reproducible verification.
- `ng build` must emit `index.html` and hashed assets directly into `src/taskrelaymcp/static/`, not a nested `browser/` directory. FastAPI's SPA fallback serves root files and client routes.
- Node.js is build-time only. Do not introduce a Node production command.
- For every non-trivial UI branch or transport change, leave one focused Vitest check.
- Before completion run:

  ```bash
  cd frontend
  npm ci
  npm test -- --watch=false
  npm run build
  ```

- When static integration changes, also run the Python tests that exercise FastAPI SPA serving.
