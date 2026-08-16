# Platform asks from building the Climate Dashboard Kit

**From:** Po ([@Agentic-Po](https://github.com/Agentic-Po))
**Context:** While building the "Build-Your-Own Climate Dashboard" starter kit — a small web app any builder can copy that talks to a Mind — we hit three platform walls. None are bugs; all are missing capabilities that every builder shipping a public-facing app will hit the same way. Writing them up here so the platform team can weigh them together.

---

## Ask 1: Per-Mind scoped builder keys

### What we hit

To let the dashboard talk to its Mind, we had to embed a builder API key. But today a builder key is all-or-nothing: the one key unlocks the builder's *entire account* — every Mind they own, their balances, and even circle writes. There is no way to mint a key that says "this key can only talk to this one Mind, read-only."

### Why it blocks us

We want a "public interactive" tier of apps — dashboards, demos, community tools — where the app itself calls a Mind on behalf of visitors. With account-wide keys, publishing such an app means publishing the keys to your whole account. No sensible builder will do that, and we can't recommend it. It also makes ordinary collaboration scary: sharing a key with a teammate or contractor hands over everything, not just the project at hand.

### What we ask for

Scoped keys: a builder can create a key limited to (a) a specific Mind, and (b) a permission level (e.g. converse-only — no balance reads, no circle writes). Revocable individually, so leaking one key burns one project, not the account.

### Copy-paste short version

> **Ask:** Per-Mind, permission-scoped API keys (e.g. "converse-only with Mind X"), individually revocable. Today one key = whole account (all Minds, balances, circle writes), which blocks any public-facing app tier and makes key sharing with collaborators unsafe.

---

## Ask 2: CORS support on api.build.hellominds.ai

### What we hit

Our dashboard is a plain web page. When the page tries to call the Minds API directly from the visitor's browser, the browser refuses. The reason is CORS — in one honest sentence: **browsers block a web page from calling an API on a different domain unless that API explicitly announces "web pages are allowed to call me," and the Minds API doesn't announce it.** So we had to build and run a small middleman server whose only job is to pass requests through to the API.

### Why it blocks us

Every builder who wants a browser-based app must now stand up and pay for a proxy server — extra code, extra hosting, extra thing to break — just to relay traffic the API would have accepted anyway. That's a real tax on exactly the lightweight, copy-a-template builders we're trying to attract. "Clone this page and it works" becomes "clone this page, then deploy a server."

### What we ask for

Serve the standard CORS headers on api.build.hellominds.ai so browsers are permitted to call it directly. This pairs naturally with Ask 1: scoped keys make it safe, CORS makes it possible.

### Copy-paste short version

> **Ask:** Enable CORS on api.build.hellominds.ai. Today browsers can't call the API from a web page, so every builder shipping a browser app must run their own proxy server. One config change removes a server from every browser-based builder project.

---

## Ask 3: An equipment read endpoint

### What we hit

The dashboard needs the "GIS Companion" skill equipped on the Mind to draw maps. There's no way to *ask* the platform whether a Mind has a skill equipped. Our only option was to probe conversationally — literally send the Mind a message like "can you do GIS lookups?" and try to interpret the reply.

### Why it blocks us

Conversational probing is slow, costs invocations, and is unreliable — a Mind can answer confidently and still be wrong about its own equipment. So apps can't check prerequisites up front, and users hit confusing mid-session failures ("the map is blank") instead of a clean upfront message ("this Mind needs GIS Companion — equip it first"). Any app built on a specific skill has this problem.

### What we ask for

A simple read endpoint: given a Mind, return the list of skills it currently has equipped. Read-only is enough. (With Ask 1, a scoped key could include this read.)

### Copy-paste short version

> **Ask:** A read-only endpoint listing which skills a Mind has equipped, so apps can verify prerequisites (e.g. "GIS Companion") up front instead of probing the Mind conversationally and guessing from its answers.

---

## Summary table

| # | Ask | Unblocks |
|---|-----|----------|
| 1 | Per-Mind, permission-scoped keys | Public-interactive apps; safe key sharing |
| 2 | CORS on api.build.hellominds.ai | Browser apps without a proxy server |
| 3 | Equipment read endpoint | Upfront prerequisite checks, clean UX |

The three compound: scoped keys make browser use safe, CORS makes it possible, and the equipment endpoint makes it reliable. Together they turn "deploy a server and hope" into "copy a template and ship."

---

## Ask 4 (added after live incident, 2026-08-17): Deterministic artifact/publish path

**What we hit:** Our Mind publishes web pages via `SITE_Update`, but the artifact parameter is a plain string — the entire file must flow through the Mind's own language model when it creates the artifact. On a ~118KB page with heavy JavaScript, the model silently "tidied" tokens during emission: `];` became `};` (breaking the page entirely), `showStep(1)` became `showStep(2)`, and one publish reused a stale artifact. Three publishes produced three different corruptions, each passing the Mind's own spot-checks.

**Why it blocks us:** Any builder shipping a real app through their Mind will eventually serve broken code to the public, without the Mind knowing. Verification can't fix this — the copy step itself is unreliable.

**What we ask for:** a URL-reference or file-reference mode for artifact creation — "fetch these bytes from this URL (or this uploaded file) and store them verbatim" — so content never passes through the model. A content-hash echo in the response would let Minds verify byte integrity themselves.

**Copy-paste short version:** "ARTIFACT/SITE_Update only take content as a string through the Mind's own generation, which silently corrupts large code files. Please add a fetch-from-URL or file-upload mode that stores bytes verbatim, ideally returning a content hash."
