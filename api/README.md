# mlbsims-api

Go (Gin) service that powers `mlbsims.com/ask` — natural-language questions over
the Statcast database. Layout follows the **controller / service / repository**
pattern.

## Layout

```
cmd/server/main.go        Wires controllers ← services ← repositories
internal/
  controller/             HTTP layer (Gin handlers, request parsing, SSE)
  service/                Orchestration (rate limit, cache, LLM, safety, DB, log)
  repository/             Concrete data access — Anthropic, pgx, LRU
  domain/                 Core types (Answer, QueryLog, Row, sentinel errors)
  config/                 Env var loading
  llm_assets/             Embedded schema doc + few-shot examples
Dockerfile                Multi-stage; final image ~15MB (distroless static)
```

## Running locally

```bash
# Terminal 1: Cloud SQL proxy on Mac (port 5433 to avoid conflict)
cloud-sql-proxy --port 5433 project-...:us-east1:mlbsims-statcast

# Terminal 2: API server
cd api
export ANTHROPIC_API_KEY=sk-...
export DB_HOST=localhost DB_PORT=5433 DB_NAME=statcast \
       DB_USER=mlbsims_llm DB_PASSWORD=...
export IP_HASH_SECRET=$(openssl rand -hex 16)
go run ./cmd/server

# Terminal 3: smoke test
curl -X POST localhost:8080/ask -H 'content-type: application/json' \
  -d '{"q":"highest spin sliders this week"}'
```

## Tests

```bash
go test ./...                # unit tests (fast, hermetic)
```

## Deploying

Triggered automatically by GitHub Actions on every push to `main` that
touches `api/**`. See `.github/workflows/deploy-api.yml` (to be added).
