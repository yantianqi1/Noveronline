# apps/web — clean-slate rewrite

This branch rebuilds the SaaS web app from an empty shell against the existing
Go control plane (`apps/api`) and agent runtimes.

## Intent

- Previous `apps/web` UI was retired in place (too costly to incrementally fix).
- Backend contracts, Compose stack, and Temporal workers stay as-is.
- Rebuild surfaces one vertical slice at a time: auth → project shell → Writer → …

## Local

```bash
cd apps/web
npm install
MIROFISH_API_BASE_URL=http://127.0.0.1:3888 npm run dev
```

Compose still health-checks `GET /login` on port `3999`.

## Do not

- Restore the deleted Vite `frontend/` tree.
- Copy retired Writer chrome (`writer-studio-grid`, dark agent rail, etc.).
- Mock LLM / workflow success paths to “make the UI look done”.
