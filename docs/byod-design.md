# Build Your Own Climate Dashboard — Design Document
Council-chair synthesis · 2026-08-16 · STUDY ONLY — nothing here is built until Po signs off.

---

## 1. Executive Summary

**Chosen custody model: the Zero-Custody Relay hybrid (C), with the kit (B) as graduation tier. Full hosted custody (A) is rejected.**

The feasibility probe removed all romantic options. Browsers cannot call api.build.hellominds.ai directly (no `Access-Control-Allow-Origin`, and `X-Api-Key` is not in `access-control-allow-headers` — two independent blockers), so a proxy is unavoidable. And builder keys are unscoped, account-wide JWTs: one key can message ALL of a holder's Minds, read every balance, and perform circle writes; expiry is the only blast-radius control the platform offers. Custodying such keys in KV — even encrypted — puts every enrolled builder's entire account inside one Worker's blast radius, operated by one PM as a side project. Every council seat (security, abuse, QA, trust-copy, devil's advocate, economics) independently rejected (A). The chair concurs: **(A) is not built until the platform ships scoped keys.**

What ships instead:

1. **Owner-interactive, zero-custody**: the builder's key lives only in their browser (sessionStorage by default). Po's single Worker becomes a **stateless relay** — the key transits per-request in a header, is never written to KV, never logged, and is stripped from errors. Logout = delete from storage; nothing server-side to revoke. Worker compromise degrades from "all tenants' keys stolen at rest" to "keys in transit during the compromise window" — bad, bounded, and honestly disclosable.
2. **Public access = read-only snapshots (the honest answer to ask #10)**: when the owner's authenticated session polls history, the Worker writes a sanitized, size-capped transcript + last canvas to per-tenant KV. Anonymous visitors get the snapshot: zero key involvement, zero cognition spend, inherently abuse-safe, and the viral loop stays intact — the chat box renders as "Build Your Own Now!" for non-owners. Public *interactive* is deliberately NOT offered on hosted infra: anyone who wants strangers spending their cognition graduates to the self-deploy kit (their key, their Worker, their caps). This resolves #10 as a spectrum, not a compromise: **hosted = public read-only + owner-interactive; self-deploy = anything they like.**
3. **Minds-native page hosting is the Phase-2/3 end-state for the page, not the secret.** SITE_Update lets each builder's Mind publish their own dashboard copy — "your Mind IS your infra" — and even bake read-only snapshots into re-published HTML. But it cannot replace the relay: static pages hold no secrets and CORS blocks direct API calls. Pursue it seriously; don't gate v1 on it.

**Honest caveat on ask #3**: "zero risk of exposure on the website" is achievable (key never appears in any served page or response); "zero risk" full-stop is not — the key transits Po's Worker over TLS. The trust copy says so plainly and pushes the real mitigation the platform offers: a **dedicated, short-expiry key**.

**v1 success metric**: key-paste → first `[[CANVAS]]` render from the builder's own Mind, under 60 seconds, and the completion rate of that funnel. Not dashboard counts.

---

## 2. Decision Log — the ten asks

| # | Ask | Verdict | Rationale |
|---|-----|---------|-----------|
| 1 | Current dashboard stays, becomes the access point | **Accept** | Zero risk; the live dashboard is the demo AND the ad. Legacy routes frozen, new code purely additive under `/d/`. |
| 2 | Onboarding links (join w/ referral tag + Unlock Builder Access) | **Accept, modified** | Three labeled doors (no account / account-no-key / has-key). Referral tag must be disclosed with a plain no-referral alternative link (trust-copy §7); confirm tag optics with the team. |
| 3 | Securely store visitor's key, zero exposure | **Modify** | "Store" → "never store." Key stays in the owner's browser; stateless relay; no KV, no logs. "Zero risk on the website" met; residual in-transit risk disclosed honestly. Short-expiry key mandated in UX. |
| 4 | Builder picks which of their Minds | **Accept** | `listMinds` via humanId decoded client-side from the key JWT. Doubles as key verification — one round trip. Balance shown per card before selection. |
| 5 | Any Mind acceptable if "GIS Companion" equipped | **Modify (downgrade)** | Unverifiable — no equipment API exists (getMind exposes no skills; bazaar has only aggregate counts). Replaced by a **functional canvas handshake**: send the PRIMER, string-check the deterministic `[[CANVAS]]…Canvas ready…` reply. PASS/SOFT-FAIL/HARD-FAIL badges. GIS Companion becomes advisory copy + conversational equip instruction. Never claim "verified." |
| 6 | "Build Your Own Now!" on every builder dashboard | **Accept, extended** | Non-removable on hosted tier (fair trade for free hosting); default-on-removable in the kit. Phase 3: CTA carries the *owner's* referral tag, fallback Po's — turns the badge into a K-factor mechanism. |
| 7 | Surface Cognition balance | **Accept** | `/v1/minds/{id}/credits`, owner-only, polled ~60s. Teaches the economics. Low-balance auto-degrade to read-only. Never shown to public visitors (it's the builder's financial info). |
| 8 | Replace the attached Mind | **Accept (trivially)** | Client-side state change: re-open the Mind picker, re-run the handshake. Confirm dialog states that new tabs start fresh conversations. |
| 9 | Logout | **Accept (trivially)** | Delete key from browser storage. No server-side session exists to revoke — that's the point of zero-custody. |
| 10 | Public accessibility | **Modify** | Hosted default & only mode: **public read-only** (snapshot replay) + owner-interactive. Public-interactive-with-caps deferred to the self-deploy kit (v2 experiment at best, opt-in, credit-denominated daily budget, per-visitor caps, Turnstile). Never default a stranger's wallet to open. |

---

## 3. Architecture

### 3.1 Topology

```
                         PUBLIC VISITOR                    OWNER (has key in browser)
                              |                                    |
                              | GET snapshot (no key,              | all calls carry X-Builder-Key
                              |  no cognition, edge-cached)        | (sessionStorage; never persisted server-side)
                              v                                    v
   +----------------------------------------------------------------------------+
   |                    PO'S WORKER (one deployment, stateless relay)            |
   |                                                                             |
   |  /  (legacy routes)      -> UNTOUCHED single-tenant workshop code path      |
   |  /d/:slug/*  (tenant)    -> relay: forward X-Builder-Key to api.build,      |
   |                             never log / never store / strip from errors     |
   |  /d/:slug/snapshot GET   -> serve KV snapshot to anonymous visitors         |
   |  snapshot write          -> only on requests whose key auth'd upstream      |
   |  rate limits             -> Durable Object per tenant (NOT per-isolate)     |
   +----------------------------------------------------------------------------+
              |                                        |
              v                                        v
      KV (snapshots, tab registries,           api.build.hellominds.ai
       rate counters — NEVER keys)              (X-Api-Key = builder's key,
                                                 in transit only)

   GRADUATION TIERS (no Po custody at all):
   - Kit (B): builder deploys template Worker+page on own Cloudflare; key = wrangler secret.
   - Minds-native (C3): builder's Mind publishes their page via SITE_Update; page points
     at the shared relay (or their own kit Worker). Solves the PAGE, not the CHANNEL.
```

### 3.2 KV schema (prefix-partitioned; legacy keys untouched)

```
t:{slug}                → { humanIdHash, mindId, mindName, title, handshakeGrade,
                            gisAdvisory, createdAt }            (NO key material, ever)
slug_by_hh:{humanIdHash}→ slug        (one dashboard per key-holder in v1)
t:{slug}:snapshot       → sanitized merged transcript + last canvas fragment,
                          256KB cap, "last live: <ts>" label
t:{slug}:tabs           → per-tenant tab registry (today's shared tabs_registry
                          pattern must NOT survive multi-tenancy)
rl:{slug}:*             → Durable-Object-backed rate counters
tabs_registry, visitor_messages*, site_html  → legacy, frozen
```

Tenant id: `sha256(humanId)` prefix; slug `[a-z0-9-]{3,24}`. Conversation aliases tenant-prefixed (`{slug}-workshop`, `{slug}-tab-xxxx`).

### 3.3 Routes

```
/d/:slug/send /history /tabs /badges     owner-only (require X-Builder-Key; relay)
/d/:slug/data                            shared HKO proxy (public, 60s edge cache)
/d/:slug/snapshot                        public GET (read-only tier)
/d/:slug/meta                            public: title, mind name, mode, CTA payload
```

No `/onboard/*`, no sessions, no cookies: presenting the key IS authentication. Attach/replace/logout are client-side.

### 3.4 Workshop protection (ask #1)

Legacy code path keyed off absence of `/d/` prefix; `MINDS_BUILDER_API_KEY` env secret and hardcoded `MIND_ID` untouched. Regression suite pins legacy routes via golden responses (§8). Migration risk ≈ zero: all new code is additive.

### 3.5 Security hardening (multi-tenant preconditions)

- Keep `sandbox=""` iframe + srcdoc CSP (`default-src 'none'`) for ALL Mind HTML — treat Mind output as hostile even on the owner's own page.
- Add strict CSP + nonce'd script to the hosted page (key sits in page JS).
- Server-side truncation of Mind messages (32KB) before caching/serving.
- Reject `[[CANVAS]]`/`[[TAB-TITLE]]` in visitor input; keep the `[Workshop visitor]` prefix guard.
- Strip `<a href>` to plain text on public snapshot views (phishing channel).
- "Content generated by this builder's Mind — not reviewed" boundary label outside the iframe; report-abuse link; per-tenant kill switch (delete KV prefix).
- Per-isolate rate-limit arrays (worker.js:33-35) do NOT carry over — Durable Object per tenant is a Phase-1 blocker, not hardening.
- Cloudflare request logging off for `/d/` routes; note worker.js:262's Origin check is not a security boundary.

---

## 4. Onboarding UX (one page — overlay wizard on the existing dashboard)

**State 0 — Visitor**: persistent pill "Build Your Own Climate Dashboard →" (asks 1, 6) on Po's and every builder's dashboard. Wizard opens over the dimmed live dashboard — the product never disappears during onboarding.

**State 1 — Prerequisites**: three labeled doors: (a) join link with disclosed referral tag + plain no-referral alternative; (b) "Unlock Builder Access" docs link, with inline note: *name the key 'climate-dashboard', set a 30-day expiry*; (c) key field on the same screen for returners.

**State 2 — Key entry**: password-type input, never echoed, `autocomplete="off"`. Client-side JWT decode gives instant offline validation (malformed / no humanId / expired `exp` → field-level errors, no network call). Trust copy (§6) sits above the field. On submit: one `listMinds` relay call = verification + State-3 data. Key → sessionStorage (opt-in localStorage with warning).

**State 3 — Pick your Mind** (asks 4, 5, 7): card list with name, species, lazily-fetched balance (shown BEFORE selection — don't attach a broke Mind). Zero-Minds empty state with refresh; zero-balance selectable with warning. On attach: **canvas handshake** — PRIMER sent, deterministic `Canvas ready` string-check → green "render-capable" / amber "text-cards only — tip: ask your Mind to equip GIS Companion, then Re-test" / hard-fail blocks. Costs one message of the builder's own cognition; run only at attach/replace, never on page load.

**State 4 — Live**: own dashboard at `/d/<slug>`, Live Weather tab + one canvas tab, primer sent. Toast: "This is YOUR dashboard, powered by <Mind>. Public visitors can watch; only you can chat." Copy-URL button front and center — the share moment is the viral moment.

**Owner chrome**: balance chip with down-tick on spend (0 → composer disables, page never blanks over money); Switch Mind (re-opens State 3, re-handshake); Log out (purge storage; copy notes there's nothing server-side to delete — that's the feature); Re-test button.

**Error paths**: all inline, none modal-blocking; key-revoked-later → banner + degrade to read-only + reopen State 2; upstream down → retry affordance, never lose entered state.

---

## 5. Cognition & Abuse Policy

**Burn math** (why read-only is the default): canvas turns cost up to ~10 credits; current per-isolate limits are really 30/min × N isolates — a looped visitor could drain ~430k credits/day worst-case. Even organic virality (200 visitors × 3 turns × 4 credits ≈ 2,400/day) hurts. The viral loop and the cost bomb are the same feature; snapshots decouple them.

**Policy:**
- Public tier costs the builder **zero** (snapshot reads, no Mind invocation).
- Owner sends: per-tenant DO limits (e.g. 10/min, 150/day) + global platform circuit breaker (300/min). Quota burns only on upstream 2xx.
- Balance is a health signal: owner-only display, 5-min-cached, low-balance (<50) auto-degrade to read-only; budget-exhausted and zero-balance states convert into the "Build Your Own" CTA.
- Dashboard-attributed burn readout via per-send KV counters (usage endpoints are per-mind aggregates and can't attribute); count primer/reminder overhead honestly.
- If a public-interactive experiment ever runs (kit tier / v2): explicit opt-in toggle with auto-expiry ("public for 48h"), credit-denominated daily budget, per-visitor caps, Turnstile on /send, and the observed cost table (1–6 chat, ~10 canvas) shown at attach time.
- Abuse economics on Po's infra: snapshots are edge-cached GETs; `/data` gets the same Origin posture as today, documented as deliberately public.

---

## 6. Trust Copy (verbatim)

**Above the key field (zero-custody relay model):**

> **Before you paste your builder key, read this.**
>
> Your Minds builder key is an account-wide credential. It can message every Mind you own, read your Cognition balances, and manage your circles. Minds does not offer scoped keys yet.
>
> **What happens to it:** your key stays in this browser only. It is never stored on any server. Each message you send relays it once, over HTTPS, through this dashboard's proxy to the Minds API — the proxy never writes it down, never logs it, and never shows it to anyone, including us. Log out and it's gone.
>
> **What you're trusting:** this is an independent side project run by one person (Po Chu). It is **not operated, audited, or endorsed by Animoca Brands or the Minds team.** While your key is in transit through the proxy, a compromise of that proxy could expose it. Nothing is kept at rest.
>
> **Reduce your risk:** create a **new key just for this**, with a **short expiry** (30 days) — expiry is the only blast-radius control Minds gives you. Delete the key in your Builder console at any time; that instantly cuts off this dashboard. Prefer zero trust in us? [Self-host the kit →]
>
> ☐ I understand this key grants account-wide access and I'm using a dedicated, short-expiry key.

Banned phrases anywhere on the site: "bank-grade", "zero risk", "fully secure", "we can't see your key".

**Public page (read-only) status line:** "Live replay of <owner>'s dashboard · last live: <time> · content generated by this builder's Mind — not reviewed."

**Referral disclosure (next to the join link, not a footer):**

> Signing up through this link credits **pochu1215** as your referrer. It costs you nothing and doesn't change your account. [Sign up without a referral →]

**Persistent footer:** "Independent community project by Po Chu. Not an official Animoca Brands or Minds product."

**Logout confirmation:** "Signed out. Your key was never stored on our servers and has been removed from this browser. To be certain, you can also revoke it in your Builder console."

---

## 7. Phased Delivery Plan

**Phase 1 — Hosted try (smallest ownable win, ~the v1 slice).**
Refactor worker.js: additive `/d/` stateless-relay routes, DO rate limiter, snapshot write/read, legacy path frozen. Refactor dashboard.html: overlay wizard (States 0–4), key-in-sessionStorage, Mind picker, handshake, balance chip, switch/logout, viral pill, trust copy. Asks shipped: 1, 2, 3(modified), 4, 5(handshake), 6, 7, 8, 9, 10(read-only public). *builder.key.maker's role*: none in the request path; it runs the onboarding conversation for builders who arrive via chat and coaches key creation (short expiry) per its charter. Gate: key-paste → first canvas < 60s, workshop regression green.

**Phase 2 — Take it home.**
Ship the kit (B): templated worker.js (MIND_ID/ALLOWED_ORIGIN/alias/PRIMER parameterized, `#key=` hack removed), README, `ALLOWED_ORIGIN` required, limits on by default. Study Minds-native hosting seriously: builder's Mind SITE_Updates their own page copy (pointed at the shared relay or their own Worker). *builder.key.maker's role*: hands the template to a stranger's Mind and coaches the publish — this IS the charter's replication test, executed with the second builder key, timed.

**Phase 3 — Loops.**
Owner-referral-tag propagation on the #6 CTA; Mind-published baked-in snapshots (public pages with zero Worker reads); dashboard gallery; only-if-scoped-keys-ship: revisit public-interactive-with-caps. File platform asks with the Minds team: **scoped/per-Mind keys, CORS ACAO + X-Api-Key allow-header, per-mind equipment endpoint** — Po's position inside the company is leverage here.

---

## 8. QA Pipeline

Principles: workshop never breaks; no third-party keys in tests — exactly two real keys (Po's + one dedicated second-account key); mock-first, live-last (live sends burn cognition); the Mind is a nondeterministic dependency — canvas rendering tested against recorded replies.

- **mock-server.py `--mode=byod`** (stdlib-only): fixture JWTs (2-Minds / zero-cognition / expired), listMinds, credits, replace/logout, failure injection (`X-Mock-Fail: upstream_502|rate_limited|expired_key`), handshake pass/soft-fail fixtures, two-tenant simultaneity test (no cross-tenant bleed) on every commit.
- **Playwright e2e per surface**: workshop regression; onboarding (assert the referral URL literally — a silent tag typo is an invisible revenue bug); key-entry (network interception proves the key leaves the browser only to the relay, never in URL/HTML/console/storage-after-logout); mind-select/balance; logout; public-visitor (read-only page has no send path — endpoint 405s, not merely hidden UI).
- **Workshop regression**: cron (30 min) read-only probes — live-page checksum vs releases.log (catches the U+FFFD Mind-pipeline corruption class), /tabs /history /data /badges contracts, CORS posture spot-check, no `[SYSTEM SETUP` leakage. Write-path: ≤2 live sends per release, pre/post deploy only. Legacy routes pinned byte-for-byte via golden responses.
- **Stage→publish→verify loop** formalized: stage via /page + byte-diff (size warning at 250KB), publish prompt frozen in `qa/publish-prompt.txt`, verify md5 + FFFD grep, keep last 3 site_html versions in KV for rollback.
- **Second-key matrix** (quarterly + major releases): replication test end-to-end (timed — the friction number is a product metric); cross-tenant isolation on real infra; response-shape validation; GIS handshake before/after conversational equip; expiry drill; zero-balance economics on the sacrificial account. Never: load tests against the real API, circle writes, anything on Po's account.
- **CI**: every commit — mock + full Playwright + gitleaks-style scan (no JWT-shaped strings in page output). Every release — full loop. Note: zero-custody removes (A)'s standing obligations (encryption-at-rest verification, custody isolation) entirely — QA cost was itself an input to the architecture decision.

---

## 9. Red Team Findings (post-synthesis adversarial pass)

Attacks that the document did NOT already defend, with minimal fixes. (Attacks already covered — XSS on the key page vs. §3.5 CSP, transit-compromise honesty vs. §6, localStorage persistence, CSRF via header-not-cookie auth, snapshot amplification via edge cache, key-rotation vs. humanId-hash tenancy — are omitted.)

**RT-1 · Tenant-binding gap on authenticated writes (custody/isolation — HIGH).** §3.1 says snapshot writes happen "only on requests whose key auth'd upstream," but auth'd-upstream ≠ authorized-for-this-slug. Any attacker with their *own* valid builder key can call `/d/{victim-slug}/send` (or trigger snapshot writes): the key authenticates fine at api.build, and the victim's public snapshot gets poisoned — defacement/phishing served to the victim's audience under their name. **Fix:** on every `/d/:slug/*` owner route, decode the presented key's humanId, hash, and require equality with `t:{slug}.humanIdHash` before relaying; 403 otherwise. Add a cross-tenant write attempt to the two-tenant mock test and the Playwright suite (assert 403, snapshot unchanged).

**RT-2 · Page-delivery supply chain is the real key-theft path (custody — HIGH).** The key lives in page JS, so whoever can alter the served page owns every active key — and the page's publish pipeline runs through the Mind's SITE_Update path, which has already demonstrably corrupted output (the U+FFFD class §8 tests for). A hallucinated, corrupted, or prompt-injected publish that injects exfil JS defeats the entire zero-custody story; §3.5's CSP is authored *by* that same pipeline so it isn't an independent control. **Fix:** the onboarding/key-entry page and owner chrome must be deployed only via a deterministic channel (Worker-served static asset or wrangler deploy from git), never via Mind publish; QA gate: byte-for-byte hash check of the served key-entry page against the repo artifact on every release and in the 30-min cron.

**RT-3 · Cloudflare is an undisclosed third party (custody/trust copy — MEDIUM).** TLS terminates at Cloudflare's edge, so keys in transit are visible to Cloudflare infrastructure regardless of Po's "never log" posture; the trust copy names only Po's proxy. **Fix:** one sentence in §6 trust copy: "The proxy runs on Cloudflare; like any HTTPS service, Cloudflare's infrastructure processes requests in transit." Also resolves interaction with Open Question 2 (personal vs. company CF account) — the answer must be disclosed either way.

**RT-4 · Owner has no off switch for the public snapshot (public access — MEDIUM).** Everything the owner chats is auto-published to an anonymous public page; the only notice is a one-time toast (§4 State 4). An owner pasting something sensitive (a key, an address, internal Minds business) has no way to pause, redact, or delete the public view short of Po's kill switch. **Fix:** per-tenant `public: on/off` flag in `t:{slug}` + a "Make private / clear public replay" control in owner chrome that deletes `t:{slug}:snapshot`; consent moves from toast to an explicit line at attach time ("your conversation is publicly replayed — you can turn this off").

**RT-5 · Slug namespace allows impersonation (public access — LOW).** First-come slugs like `minds-official`, `animoca`, or `po` let any key-holder publish a public page that appears authoritative — exactly the surface the §6 footer disclaimers try to defuse. **Fix:** reserved-slug denylist (minds, animoca, official, admin, po, hellominds, +variants) checked at registration; keep the existing kill switch as backstop.

**RT-6 · Phase 1 bundles the riskiest surface with the first ship (scope — MEDIUM).** "Smallest ownable win" in §7 actually includes the entire public multi-tenant serving tier (snapshots, sanitization, DO limits, abuse posture) — the highest-risk, highest-QA-cost half — yet the stated v1 success metric (key-paste → first canvas < 60s) needs none of it. **Fix:** split Phase 1 → **1a: owner-only** (wizard, relay with RT-1 binding check, handshake, balance, logout; no public routes at all — funnel metric fully measurable) and **1b: public read-only** (snapshot pipeline + RT-4 toggle + sanitization + viral pill on builder pages), shipped only after 1a's regression suite is green. The workshop dashboard still advertises "Build Your Own" during 1a, so the acquisition loop is not blocked.

---

## 10. Open Questions for Po (max 5)

1. **Referral tag optics**: personal `tag=pochu1215` on a quasi-official-looking Minds property — confirm with the team, or use a team tag?
2. **Cloudflare account**: the Worker will relay third-party keys in transit — should it live on a dedicated Cloudflare account rather than one shared with other credentials?
3. **Snapshot staleness trade-off**: public pages go stale when the owner is offline ("last live: 3 days ago"). Acceptable price for zero custody, or should Phase 3's Mind-published baked snapshots be pulled forward?
4. **Platform asks**: will you file the scoped-keys / CORS / equipment-endpoint requests with the platform team? Phase-3 public-interactive is gated entirely on scoped keys.
5. **Second builder account**: approve creating a throwaway Minds account + key for the QA matrix and the charter's replication test?
