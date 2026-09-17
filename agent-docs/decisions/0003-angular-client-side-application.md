# 0003 — Use Angular for the client-side application

## Status

Accepted; supersedes the React frontend choice in decision 0001.

## Decision

- TaskRelay's authenticated web application remains client-side rendered.
- Angular is the supported frontend framework, using a supported LTS major, standalone components, Angular Router, `HttpClient`, reactive forms, and signals where local state benefits from them.
- FastAPI remains the only production server and the authority for authentication, authorization, validation, and business rules.
- The Angular production build is copied into the existing Python image and served as static assets by FastAPI; Node.js is build-time only.
- The browser and API remain same-origin. Route guards and client-side permission checks are user-experience features, not security boundaries.
- Prefer Angular's built-in facilities and browser APIs. Do not add NgRx, SSR, hydration, a service worker, or a component framework without a demonstrated need.

## Rationale

Angular provides one maintained set of conventions for routing, HTTP, forms, dependency injection, building, and upgrades. TaskRelay does not need React-specific ecosystem flexibility, and keeping a JSON REST boundary leaves the frontend replaceable.

## Non-goals

No server-side rendering, separate Node.js production service, React compatibility layer, micro-frontends, offline-first behavior, or frontend-owned authorization.
