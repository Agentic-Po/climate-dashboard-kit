# Minds Canvas Dashboard

Live multi-tab, Mind-driven dashboard built for the **AI in Sustainability and Climate Change** workshop (Animoca Brands × Civic Exchange, Aug 2026). A static page on Minds-native hosting where visitors chat with a Mind and the Mind **renders whole visual canvases** — dashboards, maps, quizzes — live onto the page.

**Production**: https://sites-moca.ethoswarm.ai/roadtoglory/hello-world-native/index.html

## Architecture

```
Browser (dashboard.html — static, no secrets)
  → Cloudflare Worker (worker.js) — holds MINDS_BUILDER_API_KEY as a secret
      POST /send  · GET /history   (per-tab, ?tab=)
      GET  /data                    (live HKO weather proxy, 60s cache)
      POST /tabs  · GET /tabs       (dynamic canvas tabs; admin-key gated create)
      GET  /badges                  (unread indicators)
      POST /page  · GET /page       (release staging; admin-key gated write)
      KV: tabs_registry · visitor_messages:* · site_html
  → api.build.hellominds.ai (X-Api-Key)
  → conversations with the Mind (one per tab; visitors share each thread)
```

- **Tab 1 "Live Weather"**: HKO 26-station temperature ranking, rainfall, AI insights, pipeline-performance panel. Auto-refresh 60s.
- **Canvas tabs**: each is a fresh conversation. The Worker sends a **primer** teaching the Mind the render protocol; visitor sends get a per-message reminder prefix.

## The Mind render protocol

- `[[CANVAS]] …html fragment… [[/CANVAS]]` in a Mind reply → rendered into a sandboxed iframe (`sandbox=""`, no scripts ever). Fragment rules (enforced by primer): `<div>`-rooted, inline `<style>` only, no scripts/iframes/external URLs, dark theme, ≤12k chars.
- `[[TAB-TITLE]]name[[/TAB-TITLE]]` → the Worker applies it to the tab registry; titles refresh live on the page (30s poll). This is the Mind's **only** rename mechanism (primer forbids claiming renames without it).
- Escaped closing markers (`[[\/CANVAS]]`) are tolerated.
- Non-conforming replies degrade gracefully to a text card.

## Release pipeline (no terminal needed for page releases)

1. Edit `dashboard.html`; E2E test locally: `python3 mock-server.py` → http://localhost:8787/ (page auto-targets the same-origin mock when served from localhost).
2. Stage: `curl -X POST $BASE/page -H "X-Tab-Key: $ADMIN_KEY" --data-binary @dashboard.html`
3. Ask the Mind (site owner) to fetch `$BASE/page` raw and publish **byte-for-byte** via its `SITE_Update` tool. (The builder API has no site endpoints — publishing is Mind-side only.)
4. Verify: `curl <live URL> | md5` vs local. Watch for stray `U+FFFD` (the Mind's pipeline once corrupted a multibyte char — hence the `⏱` JS escapes).

Worker changes still need `npx wrangler deploy` (human terminal).

## Deploy your own

Everything you need is in this repo; the only prerequisites are a free Cloudflare account and a Minds builder API key.

1. **Fork** this repo: https://github.com/Agentic-Po/climate-dashboard-kit
2. **Create the Worker**: `npx wrangler deploy` from the repo root (uses `wrangler.jsonc`; rename the Worker if you like). First deploy will prompt Cloudflare login.
3. **Set secrets**:
   ```
   npx wrangler secret put MINDS_BUILDER_API_KEY   # your builder key — never goes in the page or repo
   npx wrangler secret put TAB_ADMIN_KEY           # any strong random string; gates tab creation + page staging
   ```
4. **Create the KV namespace**: `npx wrangler kv namespace create CHAT_KV`, then replace the `id` in `wrangler.jsonc` with the one printed, and `npx wrangler deploy` again.
5. **Point the page at your Worker**: edit `BASE` in `dashboard.html` (search for `var BASE =`) to your `https://<worker-name>.<account>.workers.dev` URL.
6. **Stage the page**: `curl -X POST https://<your-worker>/page -H "X-Tab-Key: <TAB_ADMIN_KEY>" --data-binary @dashboard.html`
7. Done — serve `GET /page` directly, or have your Mind publish it byte-for-byte via `SITE_Update` (see Release pipeline below).

### Localhost QA (no Cloudflare, no keys)

`python3 mock-server.py` then open http://localhost:8787/. The page auto-targets the same-origin mock when served from localhost, so the full flow — tabs, canvas replies, the Build-Your-Own wizard (fixture JWTs are in the header comment of `mock-server.py`), badges, live-data fallback — is testable offline. The mock admin key is `mock-admin`.

## Secrets & config

- `MINDS_BUILDER_API_KEY` — Worker secret (`wrangler secret put`). Never in the page or repo.
- `TAB_ADMIN_KEY` — Worker secret gating tab creation and page staging. The page accepts it via `#key=<value>` in the URL (stored to localStorage, stripped from the URL bar).
- `wrangler.jsonc` — Worker name, KV binding.

## Files

| File | Role |
|---|---|
| `dashboard.html` | The entire front-end (single self-contained file, inline CSS/JS) |
| `worker.js` | Cloudflare Worker proxy — the only holder of API credentials |
| `mock-server.py` | Localhost mock of every Worker route for E2E QA |
| `wrangler.jsonc` | Worker deploy config |

## Provenance

Built 2026-08-15/16 by Po with Claude Code (LLM council + build/QA workflow orchestration) and the Mind "RoadToGlory" (public persona: *Po's Minds Companion*) publishing to Minds-native hosting. Iterated v1 → v2.4 across two build days.
