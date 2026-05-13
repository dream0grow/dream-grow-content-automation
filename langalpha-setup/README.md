# LangAlpha sandbox install

LangAlpha (https://github.com/Chen-zexi/LangAlpha) is upstream; this directory
is a record of how it was installed inside this dev sandbox on 2026-05-13.

## TL;DR

```bash
./install.sh
```

clones LangAlpha to `~/LangAlpha`, applies `sandbox-patches.diff`, and runs
`docker compose up --build -d`. After it returns, the web UI lives at
http://localhost:80/.

## Why the patches exist

Four things upstream LangAlpha does not handle that this sandbox forced:

1. **CA bundle.** The sandbox's egress proxy intercepts TLS with a self-signed
   root. Containers reject every `pip install` until that root is added to
   their CA store. The patched Dockerfiles copy `ca-certificates.crt` from the
   build context and run `update-ca-certificates`.

2. **Debian apt mirror is blocked.** `deb.debian.org` returns 403 from inside
   the sandbox (over both http and https). The web Dockerfile used to
   `apt-get install nodejs npm`; the patch replaces that with a multi-stage
   `COPY --from=node:20-bookworm` so no apt fetch is needed.

3. **LangGraph constraints conflict.** `langchain/langgraph-api:3.11` ships
   `langgraph-checkpoint-postgres>=3.0.2` in its constraints file, while
   LangAlpha pins `langgraph-checkpoint-postgres==2.0.19`. The patch drops the
   `-c /api/constraints.txt` flag so the pinned version wins.

4. **Starlette 1.0 + Jinja2 3.x incompatibility.** Starlette 1.0 changed how
   `TemplateResponse` passes globals into Jinja2's cache, which now raises
   `TypeError: unhashable type: 'dict'` on every render. The patch pins
   `starlette<1.0` in `src/web/requirements.txt`.

Only #4 is unrelated to the sandbox — it would also bite a normal install
done today.

## Endpoints (verified)

| Service       | URL                          | Status                        |
| ------------- | ---------------------------- | ----------------------------- |
| web-api       | http://localhost:80/         | 200 (redirects to `/login`)   |
| langgraph-api | http://localhost:8123/ok     | 200; `/docs` for OpenAPI      |
| valuation-api | http://localhost:8001/health | 200                           |
| mongodb       | localhost:27017              | healthy (admin / password)    |
| postgres      | localhost:5433               | healthy (postgres / postgres) |
| redis         | internal                     | healthy                       |

`docker compose ps` reports `langgraph-api` and `valuation-api` as `unhealthy`
because their healthcheck commands probe routes that don't exist in those
images; the services themselves respond correctly on the URLs above.

## Before real use

`.env` is created from `.env.example` and still contains placeholder API keys.
Fill in at minimum:

- `POLYGON_API_KEY`, `TAVILY_API_KEY`, `FINANCIALMODELINGPREP_API_KEY`
- At least one of `OPENAI_API_KEY` / `GEMINI_API_KEY` / `ANTHROPIC_API_KEY`

then `docker compose restart langgraph-api web-api`.
