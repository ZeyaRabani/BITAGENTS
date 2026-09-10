# AGENTS.md

## Project Overview

This is a Next.js frontend and Python backend application for Agent Marketplace.

- Frontend Framework: Next.js
- Language: TypeScript
- Backend: Python
- Database: PostgreSQL
- ORM: Drizzle
- Frontend package manager: npm

## Repository Structure

- `frontend/` — Next.js frontend
- `agents/new/` — Python backend
- `.env.example` - documented environment variables

## Commands

### Frontend

Install dependencies:
`npm install`

Start development:
`npm run dev`

Build:
`npm run build`

### Backend

Activate the virtual environment:
`source venv/bin/activate`

Install dependencies:
`pip install -r requirements.txt`

Start development:
`python agents_api.py`

## Coding Conventions

- Use TypeScript; do not introduce JavaScript files.
- Prefer named exports.
- Use async/await instead of `.then()` chains.
- Keep components small and composable.
- Reuse existing utilities before creating new ones.
- Match the style of surrounding code.
- Do not introduce a new dependency unless necessary.
- Prefer small, focused changes over large refactors.
- Do not refactor unrelated code while working on a task.
- Do not duplicate existing functionality; look for existing utilities, components, and services first.

## Architecture

- UI components must not access the database directly.
- Frontend code must communicate with the backend through the existing API/RPC layer.
- Do not expose server-side secrets, credentials, or private configuration through `NEXT_PUBLIC_*` environment variables.
- API routes should call service functions rather than contain business logic.
- Keep business logic out of UI components.
- Follow the existing project architecture instead of introducing a new pattern without a strong reason.

## Testing

<!-- ToDo: Add some test -->

## Do Not

- Do not remove or do any modifications in the `temp` folder.
- Do not commit `.env` files or secrets.
- Do not modify production configuration without being asked.
- Do not remove tests because they are failing.
- Do not upgrade dependencies unless requested or required.
- Do not change the database schema without checking the existing migration conventions.
- Do not modify generated files manually.
- Do not make unrelated refactors.
- Do not expose secrets or server-only values through `NEXT_PUBLIC_*`.

## Ask Before

Ask for confirmation before:

- Adding a new production dependency.
- Changing the database schema.
- Changing public API contracts.
- Making breaking changes.
- Changing authentication or authorization behavior.
- Modifying CI/CD configuration.
- Making significant architectural changes.
- Removing existing functionality.

## Git

- Keep commits focused on one logical change.
- Do not rewrite existing commits unless explicitly requested.
- Do not use `git reset --hard`.
- Do not commit generated build artifacts.
- Do not commit secrets or environment files.

## Pull Requests

- Explain what changed and why.
- Mention tests or validation commands that were run.
- Call out migrations or breaking changes explicitly.
- Keep the PR focused on the requested change.

## Gotchas

- Focus on keeping agent responses fast.
- Do not use em dashes (—); use regular dashes (-) instead.
- Environment variables are documented in `.env.example`.
- Before adding a new dependency or abstraction, check whether an existing solution can be reused.
