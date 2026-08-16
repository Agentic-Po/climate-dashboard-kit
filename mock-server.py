#!/usr/bin/env python3
"""Localhost mock of the minds-chat-proxy Worker for E2E QA of dashboard-v2.html.
Serves the page at / and same-origin mock API routes. Simulates: history with a
canvas reply (including an ESCAPED closing marker to test tolerance), a Mind
rename mid-session (title change appears via /tabs polling), send echo, live data.
"""
import json, time, re, threading, base64, hashlib
from http.server import HTTPServer, BaseHTTPRequestHandler

START = time.time()
PAGE = open("dashboard.html", "rb").read()

# ---- BYOD fixtures (Phase 1a) ----
# Paste this VALID fixture key into the wizard for full E2E on localhost:
#   eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJodW1hbklkIjoiaHVtYW4tbW9jay0xIiwiZXhwIjo0MTAyNDQ0ODAwfQ.sig
# Expired-key fixture (client-side validation should reject it offline):
#   eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJodW1hbklkIjoiaHVtYW4tbW9jay0xIiwiZXhwIjoxMDAwMDAwMDAwfQ.sig
BYOD_MINDS = [
    {"mindId": "mind-alpha-0001", "name": "Climate Mind Alpha"},
    {"mindId": "mind-beta-0002", "name": "Beta Companion"},
    # gamma: replies but NEVER says "Canvas ready" — exercises the amber
    # soft-fail handshake path without needing X-Mock-Fail.
    {"mindId": "mind-gamma-0003", "name": "Gamma (no canvas)"},
]
BYOD_BALANCES = {"mind-alpha-0001": 1234.5, "mind-beta-0002": 0, "mind-gamma-0003": 42}
BYOD_MIND_MSGS = {}   # mindId -> [mind messages only]  (relay never returns visitor msgs)
BYOD_PRIMED = set()   # mindIds whose conversation exists
TRACK = {"join": 0, "docs": 0}
JOIN_URL = "https://hellominds.ai/join?platform=hellominds&tag=pochu1215"
DOCS_URL = "https://build.hellominds.ai/docs/builder-access"
ADMIN_KEY = "mock-admin"

BYOD_CANVAS_REPLY = ('[[CANVAS]]<div style="display:grid;place-items:center;height:100%;'
                     'background:#0b0d10;color:#e6e8eb;font-size:26px">BYOD CANVAS OK</div>[[/CANVAS]] Canvas ready.')

def byod_key_status(hdr):
    """Mirror the worker: header only; enum errors; payload-only JWT decode."""
    k = hdr or ""
    # Mirror worker getVisitorKey: header only, 20-4096 chars, no trimming.
    if not (20 <= len(k) <= 4096): return "missing_key"
    # Mirror worker jwtPayload: exactly 3 dot-separated parts.
    parts = k.split(".")
    if len(parts) != 3: return "bad_key"
    try:
        p = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(p))
    except Exception:
        return "bad_key"
    if not (payload.get("humanId") or payload.get("human_id") or payload.get("sub")): return "bad_key"
    if payload.get("exp") and payload["exp"] < time.time(): return "expired_key"
    return None

BYOD_PLAIN_REPLY = "<p>Sure — here is a plain text answer (no canvas capability equipped).</p>"

def byod_mind_reply(mind_id, delay=3.0):
    def go():
        time.sleep(delay)
        BYOD_MIND_MSGS.setdefault(mind_id, []).append({
            "messageText": BYOD_PLAIN_REPLY if mind_id.startswith("mind-gamma") else BYOD_CANVAS_REPLY,
            "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "senderName": "Mind", "partyType": 0})
    threading.Thread(target=go, daemon=True).start()

# ---- BYOD fixtures (Phase 1b: slugs + public replay) ----
# Second fixture key (humanId human-mock-2) — ALREADY CLAIMED tenant, for the
# whoami restore flow. Paste it and the dashboard should restore /d/kannan-climate:
#   eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJodW1hbklkIjoiaHVtYW4tbW9jay0yIiwiZXhwIjo0MTAyNDQ0ODAwfQ.sig
# The primary fixture key (human-mock-1) has NO claim -> exercises wizard State 3.5.
REPO_URL = "https://github.com/Agentic-Po/climate-dashboard-kit"
PAGE_URL = "/"
SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{2,31}$")
# Third segment {4,} — one regex everywhere (worker.js + dashboard.html twins).
JWT_SHAPE_RE = re.compile(r"[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}")
SNAP_BODY_MAX, SNAP_CANVAS_MAX, SNAP_MSG_MAX, SNAP_MSGS_MAX = 65536, 16384, 4096, 50
SNAP_MIN_INTERVAL = 5  # worker uses 30s; shortened for local QA loops
DENY_SUB = ["minds", "animoca", "hellominds", "mocaverse", "official",
            "admin", "support", "staff", "moderator", "security", "verify", "verified",
            "system", "wallet", "airdrop", "giveaway", "cognition", "yatsiu", "yat-siu", "pochu"]
DENY_EXACT = {"mind", "moca", "po", "poc", "api", "docs", "www",
              "root", "help", "team", "mod", "login", "signin", "key", "keys",
              "d", "page", "relay", "track", "tabs", "send", "history", "data", "badges",
              "snapshot", "meta", "claim", "workshop", "climate", "dashboard"}

def valid_slug(s):
    return isinstance(s, str) and bool(SLUG_RE.match(s)) and not s.endswith("-") and "--" not in s

def slug_denied(s):
    return s in DENY_EXACT or any(t in s for t in DENY_SUB)

def tenant_id_of(human_id):
    return hashlib.sha256(str(human_id).strip().encode()).hexdigest()

def byod_human_id(hdr):
    """Payload-only decode, pinned claim order humanId > human_id > sub."""
    try:
        p = (hdr or "").split(".")[1]
        payload = json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))
        for c in ("humanId", "human_id", "sub"):
            v = payload.get(c)
            if v is not None and str(v).strip():
                return str(v).strip()
    except Exception:
        pass
    return None

# Exact fixture keys the fake upstream "knows" (sha256 whitelist — never the
# raw key at comparison time paths beyond this constant). A forged JWT that
# merely reuses a known humanId with a garbage signature MUST be rejected,
# mirroring the real upstream's signature check (pinned QA row RT-1b).
FIXTURE_KEY_1 = ("eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0."
                 "eyJodW1hbklkIjoiaHVtYW4tbW9jay0xIiwiZXhwIjo0MTAyNDQ0ODAwfQ.sig")
FIXTURE_KEY_2 = ("eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0."
                 "eyJodW1hbklkIjoiaHVtYW4tbW9jay0yIiwiZXhwIjo0MTAyNDQ0ODAwfQ.sig")
_FIXTURE_KEY_HASHES = {hashlib.sha256(k.encode()).hexdigest()
                       for k in (FIXTURE_KEY_1, FIXTURE_KEY_2)}

def mock_verify_upstream(key, human_id):
    """Mock of verifyKeyUpstream (D4): only the EXACT fixture keys pass.
    Forged-JWT owner mutation -> 401 (RT-1b): known humanId + bad signature fails."""
    if hashlib.sha256((key or "").encode()).hexdigest() not in _FIXTURE_KEY_HASHES:
        return False
    return isinstance(human_id, str) and human_id.startswith("human-mock")

def sanitize_fragment(frag):
    s = str(frag or "")
    if len(s) > SNAP_CANVAS_MAX: return None  # reject, never truncate (D5)
    s = re.sub(r"<script\b[\s\S]*?</script\s*>", "", s, flags=re.I)
    s = re.sub(r"<script\b[^>]*>", "", s, flags=re.I)
    s = re.sub(r"</?(iframe|object|embed|form|base|link|meta)\b[^>]*>", "", s, flags=re.I)
    s = re.sub(r"\son\w+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", s, flags=re.I)
    s = re.sub(r"javascript:", "blocked:", s, flags=re.I)
    s = re.sub(r"\ssrcdoc\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", s, flags=re.I)
    s = re.sub(r"<a\b[^>]*>", "", s, flags=re.I)
    s = re.sub(r"</a\s*>", "", s, flags=re.I)
    return s

def clean_transcript_text(text):
    s = str(text or "")
    s = re.sub(r"\[\[CANVAS\]\][\s\S]*?\[\[\\?/CANVAS\]\]", "", s)
    s = re.sub(r"\[\[TAB-TITLE\]\][\s\S]*?\[\[\\?/TAB-TITLE\]\]", "", s)
    s = re.sub(r"\[\[\\?/?(CANVAS|TAB-TITLE)\]\]", "", s)
    s = re.sub("[\\u0000-\\u0008\\u000B\\u000C\\u000E-\\u001F\\u007F]", "", s)
    return s.strip()

def esc_html(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;"))

def iso_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

# Two fake tenants. Tenant rows mirror the worker's t:{slug} schema exactly
# (no secrets, no balance slot). human-mock-2 owns the PUBLIC one.
_TH2 = tenant_id_of("human-mock-2")
_TH3 = tenant_id_of("human-mock-3")
BYOD_TENANTS = {
    "kannan-climate": {"v": 1, "slug": "kannan-climate", "tenantIdHash": _TH2,
        "idClaim": "humanId", "mindId": "mind-alpha-0001", "mindName": "Climate Mind Alpha",
        "title": "Kannan's Climate Watch", "handshakeGrade": "PASS",
        "publicToggle": True, "consentAt": "2026-08-15T09:00:00Z",
        "createdAt": "2026-08-15T09:00:00Z", "lastSeenAt": "2026-08-16T08:00:00Z",
        "lastSnapshotAt": "2026-08-16T08:05:00Z"},
    "zoe-weather": {"v": 1, "slug": "zoe-weather", "tenantIdHash": _TH3,
        "idClaim": "humanId", "mindId": "mind-beta-0002", "mindName": "Beta Companion",
        "title": "Zoe's Weather Corner", "handshakeGrade": "SOFT-PASS",
        "publicToggle": False, "consentAt": None,  # private -> /d/ must 404 (D15)
        "createdAt": "2026-08-14T12:00:00Z", "lastSeenAt": "2026-08-14T12:00:00Z",
        "lastSnapshotAt": None},
}
BYOD_OWNERS = {_TH2: {"slug": "kannan-climate", "claimedAt": "2026-08-15T09:00:00Z"},
               _TH3: {"slug": "zoe-weather", "claimedAt": "2026-08-14T12:00:00Z"}}
BYOD_SNAPSHOTS = {
    "kannan-climate": {"v": 1,
        "canvas": ('<div style="display:grid;place-items:center;height:100%;'
                   'background:#0b0d10;color:#e6e8eb;font-size:24px">KANNAN REPLAY CANVAS</div>'),
        "canvasTitle": "HK Temperature Now",
        "transcript": [
            {"party": "owner", "text": "Show me today's hottest district.", "at": "2026-08-16T08:04:00Z"},
            {"party": "mind", "text": "Built a canvas with the top-3 hottest stations. Canvas ready.", "at": "2026-08-16T08:05:00Z"}],
        "mindName": "Climate Mind Alpha",
        "capturedAt": "2026-08-16T08:05:00Z", "publishedAt": "2026-08-16T08:05:00Z",
        "contentHash": "fixture"},
}
BYOD_TOMBS = {}          # slug -> {tenantIdHash, releasedAt}
BYOD_SNAP_LAST = {}      # tenantIdHash -> last accepted push (monotonic clock)

SHELL_404 = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
             '<meta name="viewport" content="width=device-width,initial-scale=1">'
             '<title>No dashboard here</title></head><body style="background:#0b0d10;color:#e6e8eb;'
             'font-family:sans-serif;padding:20px"><h1>No dashboard here</h1>'
             '<p>Nothing is published at this address.</p>'
             '<a href="' + PAGE_URL + '#byod" style="color:#93b4ff">Build your own climate dashboard in 60 seconds &rarr;</a>'
             '<p style="font-size:12.5px">Fork this kit &rarr; <a style="color:#93b4ff" href="' + REPO_URL + '">' + REPO_URL + '</a></p>'
             '<footer style="font-size:12px;color:#9aa3ad">Independent community project by Po Chu. '
             'Not an official Animoca Brands or Minds product.</footer></body></html>').encode()

def shell_html(slug, t):
    """Mock twin of the worker's public shell: fetches snapshot.json, sandboxed iframe."""
    title = esc_html(t.get("title") or slug)
    mind = esc_html(t.get("mindName") or "their Mind")
    js = (
        'var slug=' + json.dumps(slug) + ';'
        'function load(){fetch("/d/"+slug+"/snapshot.json").then(function(r){return r.ok?r.json():null;})'
        '.then(function(p){if(!p||p.empty){document.getElementById("es").hidden=false;return;}'
        'if(p.canvas){var f=document.getElementById("cv");f.parentElement.hidden=false;f.srcdoc=p.canvas;'
        'var ct=document.getElementById("cvt");ct.textContent=p.canvasTitle||"";ct.hidden=!p.canvasTitle;}'
        'var tr=document.getElementById("tr");tr.hidden=!(p.transcript&&p.transcript.length);tr.textContent="";'
        '(p.transcript||[]).forEach(function(m){var d=document.createElement("div");'
        'd.textContent=(m.label||m.party)+": "+m.text;tr.appendChild(d);});'
        'document.getElementById("st").textContent="Replay \\u00b7 last live: "+(p.publishedAt||"never")+'
        '" \\u00b7 content generated by this builder\'s Mind \\u2014 not reviewed";}).catch(function(){});}'
        'load();setInterval(load,60000);')
    return (('<!doctype html><html lang="en"><head><meta charset="utf-8">'
             '<meta name="viewport" content="width=device-width,initial-scale=1">'
             '<title>' + title + ' &middot; Climate Dashboard replay</title></head>'
             '<body style="background:#0b0d10;color:#e6e8eb;font-family:sans-serif;padding:20px;max-width:900px;margin:0 auto">'
             '<h1>' + title + '</h1><p id="st" style="color:#9aa3ad;font-size:13px">Loading replay&hellip;</p>'
             '<div hidden style="border:1px solid #1f242c;border-radius:14px;overflow:hidden">'
             '<div id="cvt" hidden style="padding:10px 16px 0;font-size:14px;color:#9aa3ad"></div>'
             '<iframe id="cv" sandbox="" referrerpolicy="no-referrer" title="Canvas replay" '
             'style="width:100%;height:420px;border:0;background:#0b0d10"></iframe></div>'
             '<div id="tr" hidden style="border:1px solid #1f242c;border-radius:14px;padding:14px;margin-top:16px"></div>'
             '<div id="es" hidden style="padding:26px;text-align:center;color:#9aa3ad">' + title +
             " hasn't gone live yet. Check back soon &mdash; or build your own below.</div>"
             '<a href="' + PAGE_URL + '#byod" style="display:block;color:#9aa3ad;border:1px solid #1f242c;'
             'border-radius:14px;padding:14px;margin-top:16px;text-decoration:none">Only ' + title +
             "'s owner can chat here &mdash; build your own in 60 seconds &rarr;</a>"
             '<p style="font-size:12.5px;color:#9aa3ad">Fork this kit &rarr; <a style="color:#93b4ff" href="'
             + REPO_URL + '">' + REPO_URL + '</a></p>'
             '<footer style="font-size:12px;color:#9aa3ad;margin-top:22px">Independent community project by Po Chu. '
             'Not an official Animoca Brands or Minds product. &middot; Powered by ' + mind + '</footer>'
             '<script>' + js + '</script></body></html>')).encode()

TABS = [
    {"alias": "workshop", "title": "Live Weather", "kind": "template", "createdAt": ""},
    {"alias": "tab-aaaa1111", "title": "Canvas A", "createdAt": "2026-08-16T01:00:00Z", "lastMindAt": "2026-08-16T01:05:00Z", "kind": "canvas"},
]
VISITORS = {"workshop": [], "tab-aaaa1111": []}
# canvas reply with ESCAPED closing marker — tests the tolerance fix
CANVAS_REPLY = ('[[CANVAS]]<div style="display:grid;place-items:center;height:100%;'
                'background:#0b0d10;color:#e6e8eb;font-size:28px">MOCK CANVAS RENDER OK</div>[[\\/CANVAS]] Built it.')

def mind_msgs(alias):
    if alias == "workshop":
        return [{"messageText": "<p>Welcome to the mock workshop thread.</p>",
                 "createdAt": "2026-08-16T00:01:00Z", "senderName": "Po's Minds Companion", "partyType": 0}]
    msgs = [{"messageText": CANVAS_REPLY, "createdAt": "2026-08-16T01:05:00Z",
             "senderName": "Po's Minds Companion", "partyType": 0}]
    return msgs

class H(BaseHTTPRequestHandler):
    # ---- Phase 1b helpers ----
    def _html(self, b, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(b)

    def _verified_tenant_hash(self):
        """(tenantIdHash, err_enum). Mirrors verifyKeyUpstream fail-closed order."""
        hdr = self.headers.get("X-Visitor-Key")
        err = byod_key_status(hdr)
        if err: return None, err if err == "missing_key" else "key_rejected"
        hid = byod_human_id(hdr)
        if not hid or not mock_verify_upstream(hdr, hid): return None, "key_rejected"
        return tenant_id_of(hid), None

    def _require_owner(self, slug):
        """(tenant_row, (err, code)). RT-1: cross-tenant -> not_owner 403."""
        th, err = self._verified_tenant_hash()
        if err: return None, (err, 401)
        t = BYOD_TENANTS.get(slug)
        if not t or t["tenantIdHash"] != th: return None, ("not_owner", 403)
        return t, None

    def log_message(self, *a): pass
    def _json(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/" or p == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(PAGE)
        elif p == "/tabs":
            # simulate a Mind rename 20s after server start
            if time.time() - START > 20:
                TABS[1]["title"] = "Renamed By Mind"
            self._json({"tabs": TABS})
        elif p == "/badges":
            self._json({t["alias"]: t.get("lastMindAt", "") for t in TABS})
        elif p == "/history":
            q = self.path.split("?")[1] if "?" in self.path else ""
            alias = "workshop"
            mt = re.search(r"tab=([\w-]+)", q)
            if mt: alias = mt.group(1)
            if alias not in VISITORS: return self._json({"ok": False, "error": "unknown_tab"}, 400)
            merged = sorted(mind_msgs(alias) + VISITORS[alias], key=lambda m: m["createdAt"])
            self._json(merged)
        elif p == "/data":
            self._json({"fetchedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "timings": {"rainfallMs": 800, "weatherMs": 300},
                        "weather": {"temperature": {"data": [
                            {"place": "Mock Hot Park", "value": 33, "unit": "C"},
                            {"place": "Mock Cool Bay", "value": 28, "unit": "C"},
                            {"place": "Mock Mid Town", "value": 30, "unit": "C"}],
                            "recordTime": "2026-08-16T12:00:00+08:00"},
                            "humidity": {"data": [{"place": "HKO", "value": 78}]},
                            "updateTime": "2026-08-16T12:00:00+08:00",
                            "rainfall": {"data": [{"place": "Mock District", "max": 2, "unit": "mm"}]}},
                        "rainfall": None})
        elif p == "/track/join" or p == "/track/docs":
            which = "join" if p.endswith("join") else "docs"
            TRACK[which] += 1
            self.send_response(302)
            self.send_header("Location", JOIN_URL if which == "join" else DOCS_URL)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
        elif p == "/relay/whoami":
            inj = self.headers.get("X-Mock-Fail", "")
            if inj == "rate_limited": return self._json({"ok": False, "error": "rate_limited"}, 429)
            th, err = self._verified_tenant_hash()
            if err: return self._json({"ok": False, "error": err}, 401)
            row = BYOD_OWNERS.get(th)
            t = BYOD_TENANTS.get(row["slug"]) if row else None
            if not t or t["tenantIdHash"] != th:
                if row: BYOD_OWNERS.pop(th, None)  # self-heal dangling reverse index
                return self._json({"ok": True, "claimed": False})
            t["lastSeenAt"] = iso_now()
            self._json({"ok": True, "claimed": True, "slug": t["slug"], "url": "/d/" + t["slug"],
                        "mindId": t.get("mindId") or "", "mindName": t.get("mindName") or "",
                        "title": t.get("title") or t["slug"], "handshakeGrade": t.get("handshakeGrade") or "",
                        "publicToggle": bool(t.get("publicToggle")), "lastSnapshotAt": t.get("lastSnapshotAt")})
        elif p == "/d" or p.startswith("/d/"):
            m = re.match(r"^/d/([^/]+)(?:/(snapshot\.json))?$", p)
            if not m: return self._html(SHELL_404, 404)
            slug, sub = m.group(1), m.group(2) or ""
            t = BYOD_TENANTS.get(slug) if valid_slug(slug) and not slug_denied(slug) else None
            # D15: private and unknown are byte-identical 404s.
            is_public = bool(t and t.get("publicToggle") is True and t.get("consentAt"))
            if sub == "snapshot.json":
                if not is_public: return self._json({"ok": False, "error": "not_found"}, 404)
                snap = BYOD_SNAPSHOTS.get(slug)
                if not snap:
                    return self._json({"v": 1, "empty": True, "slug": slug,
                                       "title": t.get("title") or slug, "publishedAt": None})
                return self._json({"v": 1, "slug": slug, "title": t.get("title") or slug,
                                   "canvas": snap.get("canvas"), "canvasTitle": snap.get("canvasTitle") or "",
                                   "transcript": [{"party": e["party"],
                                                   "label": "Builder" if e["party"] == "owner" else "Mind",
                                                   "text": e["text"], "at": e.get("at")}
                                                  for e in snap.get("transcript", [])],
                                   "mindName": snap.get("mindName") or t.get("mindName") or "",
                                   "publishedAt": snap.get("publishedAt")})
            self._html(shell_html(slug, t) if is_public else SHELL_404, 200 if is_public else 404)
        elif p == "/track/stats":
            if self.headers.get("X-Tab-Key") != ADMIN_KEY:
                return self._json({"ok": False, "error": "forbidden"}, 403)
            self._json({"ok": True, "join": TRACK["join"], "docs": TRACK["docs"]})
        else:
            self._json({"ok": False, "error": "not_found"}, 404)

    def do_POST(self):
        p = self.path.split("?")[0]
        ln = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(ln) if ln else b""
        if p == "/send":
            try: d = json.loads(body)
            except Exception: d = {}
            alias = d.get("tab") or "workshop"
            mt = re.search(r"tab=([\w-]+)", self.path)
            if mt: alias = mt.group(1)
            text = (d.get("messageText") or "").strip()
            if not text: return self._json({"ok": False, "error": "bad_message"}, 400)
            VISITORS.setdefault(alias, []).append({
                "messageText": text, "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "senderName": "Visitor", "partyType": 1})
            self._json({"alias": alias, "messageId": "mock-1"})
        elif p == "/tabs":
            n = {"alias": "tab-bbbb2222", "title": "Canvas New", "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "lastMindAt": "", "kind": "canvas", "primed": True}
            if not any(t["alias"] == n["alias"] for t in TABS):
                TABS.append(n); VISITORS[n["alias"]] = []
            self._json({"ok": True, "tab": n})
        elif p.startswith("/relay/"):
            # failure injection: X-Mock-Fail: upstream_502|rate_limited|expired_key
            inj = self.headers.get("X-Mock-Fail", "")
            if inj == "upstream_502": return self._json({"ok": False, "error": "upstream_error"}, 502)
            if inj == "rate_limited": return self._json({"ok": False, "error": "rate_limited"}, 429)
            if inj == "expired_key": return self._json({"ok": False, "error": "expired_key"}, 401)
            err = byod_key_status(self.headers.get("X-Visitor-Key"))
            if err:
                return self._json({"ok": False, "error": err}, 401)
            try: d = json.loads(body) if body else {}
            except Exception: d = {}
            mind_id = d.get("mindId") or ""
            alias = "byod-" + re.sub(r"[^a-z0-9]", "", mind_id.lower())[:8]
            if p == "/relay/minds":
                return self._json({"ok": True, "minds": BYOD_MINDS})
            if p == "/relay/claim":
                th, verr = self._verified_tenant_hash()
                if verr: return self._json({"ok": False, "error": verr}, 401)
                slug = (d.get("slug") or "").strip().lower() if isinstance(d.get("slug"), str) else ""
                if not valid_slug(slug): return self._json({"ok": False, "error": "bad_slug"}, 400)
                if slug_denied(slug): return self._json({"ok": False, "error": "slug_reserved"}, 400)
                row = BYOD_OWNERS.get(th)
                if row:  # idempotent: one slug per tenant, ever (F-5)
                    ex = BYOD_TENANTS.get(row["slug"])
                    if ex and ex["tenantIdHash"] == th:
                        return self._json({"ok": True, "slug": row["slug"], "url": "/d/" + row["slug"],
                                           "publicToggle": bool(ex.get("publicToggle")), "existing": True})
                    BYOD_OWNERS.pop(th, None)
                tomb = BYOD_TOMBS.get(slug)
                if tomb and tomb["tenantIdHash"] != th:
                    return self._json({"ok": False, "error": "slug_taken"}, 409)
                if slug in BYOD_TENANTS:
                    return self._json({"ok": False, "error": "slug_taken"}, 409)
                consent = d.get("consent") is True
                public = d.get("publicToggle") is True and consent  # RT-4
                now = iso_now()
                BYOD_TENANTS[slug] = {
                    "v": 1, "slug": slug, "tenantIdHash": th, "idClaim": "humanId",
                    "mindId": mind_id if any(m["mindId"] == mind_id for m in BYOD_MINDS) else "",
                    "mindName": (d.get("mindName") or "").strip()[:80] if isinstance(d.get("mindName"), str) else "",
                    "title": ((d.get("title") or "").strip()[:64] if isinstance(d.get("title"), str) and (d.get("title") or "").strip() else slug),
                    "handshakeGrade": d.get("handshakeGrade") if d.get("handshakeGrade") in ("PASS", "SOFT-PASS", "SOFT-FAIL") else "",
                    "publicToggle": public, "consentAt": now if consent else None,
                    "createdAt": now, "lastSeenAt": now, "lastSnapshotAt": None}
                BYOD_OWNERS[th] = {"slug": slug, "claimedAt": now}
                return self._json({"ok": True, "slug": slug, "url": "/d/" + slug, "publicToggle": public})
            if not any(m["mindId"] == mind_id for m in BYOD_MINDS):
                return self._json({"ok": False, "error": "bad_mind"}, 400)
            if p == "/relay/balance":
                self._json({"ok": True, "balance": BYOD_BALANCES.get(mind_id)})
            elif p == "/relay/send":
                text = (d.get("messageText") or "").strip()
                if not text or len(text) > 2000 or "[[CANVAS]]" in text or "[[TAB-TITLE]]" in text:
                    return self._json({"ok": False, "error": "bad_message"}, 400)
                primed = mind_id not in BYOD_PRIMED
                BYOD_PRIMED.add(mind_id)
                byod_mind_reply(mind_id)
                self._json({"ok": True, "alias": alias, "primed": primed, "messageId": "mock-byod-%d" % time.time()})
            elif p == "/relay/history":
                self._json({"ok": True, "alias": alias, "messages": BYOD_MIND_MSGS.get(mind_id, [])})
            else:
                self._json({"ok": False, "error": "not_found"}, 404)
        elif p.startswith("/d/"):
            m = re.match(r"^/d/([^/]+)/(snapshot|visibility|clear)$", p)
            if not m: return self._json({"ok": False, "error": "method_not_allowed"}, 405)
            slug, sub = m.group(1), m.group(2)
            inj = self.headers.get("X-Mock-Fail", "")
            if inj == "rate_limited": return self._json({"ok": False, "error": "rate_limited"}, 429)
            if inj == "replay_paused": return self._json({"ok": False, "error": "replay_paused"}, 429)
            if not (valid_slug(slug) and not slug_denied(slug)):
                return self._json({"ok": False, "error": "not_found"}, 404)
            t, oerr = self._require_owner(slug)
            if oerr: return self._json({"ok": False, "error": oerr[0]}, oerr[1])
            try: d = json.loads(body) if body else {}
            except Exception: d = {}
            if sub == "visibility":
                if not isinstance(d.get("publicToggle"), bool):
                    return self._json({"ok": False, "error": "bad_body"}, 400)
                if d["publicToggle"]:
                    if not t.get("consentAt") and d.get("consent") is not True:
                        return self._json({"ok": False, "error": "consent_required"}, 409)
                    if d.get("consent") is True or not t.get("consentAt"): t["consentAt"] = iso_now()
                    t["publicToggle"] = True
                else:
                    t["publicToggle"] = False  # snapshot kept — pause, not redact (RT-4)
                return self._json({"ok": True, "publicToggle": t["publicToggle"]})
            if sub == "clear":
                BYOD_SNAPSHOTS.pop(slug, None)
                t["lastSnapshotAt"] = None
                return self._json({"ok": True})
            # sub == "snapshot" — the ONLY public-content write path.
            if not (t.get("publicToggle") is True and t.get("consentAt")):
                return self._json({"ok": False, "error": "replay_private"}, 409)
            if not body or len(body) > SNAP_BODY_MAX:
                return self._json({"ok": False, "error": "too_large"}, 413)
            if not isinstance(d, dict) or not d:
                return self._json({"ok": False, "error": "bad_body"}, 400)
            captured = d.get("capturedAt")
            if not isinstance(captured, str) or not captured:
                return self._json({"ok": False, "error": "bad_body"}, 400)
            canvas = None
            if isinstance(d.get("canvas"), str) and d["canvas"]:
                if len(d["canvas"]) > SNAP_CANVAS_MAX:
                    return self._json({"ok": False, "error": "canvas_too_large"}, 413)
                canvas = sanitize_fragment(d["canvas"])
                if canvas and JWT_SHAPE_RE.search(canvas):
                    canvas = None  # E2d: key-shaped text in a canvas build never public
            canvas_title = re.sub(r"<[^>]*>", "", d.get("canvasTitle") or "").strip()[:48] \
                if isinstance(d.get("canvasTitle"), str) else ""
            mind_name = (d.get("mindName") or "").strip()[:80] \
                if isinstance(d.get("mindName"), str) else (t.get("mindName") or "")
            transcript = []
            for e in (d.get("transcript") or [])[:SNAP_MSGS_MAX]:
                if not isinstance(e, dict): continue
                party = e.get("party")
                if party not in ("owner", "mind") or not isinstance(e.get("text"), str): continue
                if len(e["text"]) > SNAP_MSG_MAX:
                    return self._json({"ok": False, "error": "message_too_large"}, 413)
                if JWT_SHAPE_RE.search(e["text"]): continue  # E2d: key-shaped text never public
                text = clean_transcript_text(e["text"])
                if not text: continue
                transcript.append({"party": party, "text": text, "at": e.get("at") or captured})
            if not canvas and not transcript:
                return self._json({"ok": False, "error": "empty_snapshot"}, 400)
            stored = BYOD_SNAPSHOTS.get(slug)
            if stored and stored.get("capturedAt") and captured <= stored["capturedAt"]:
                return self._json({"ok": False, "error": "stale_capture"}, 409)  # D6
            chash = hashlib.sha256(json.dumps(
                {"canvas": canvas, "canvasTitle": canvas_title,
                 "transcript": transcript, "mindName": mind_name}, sort_keys=True).encode()).hexdigest()
            if stored and stored.get("contentHash") == chash:
                return self._json({"ok": True, "skipped": "unchanged", "publishedAt": stored["publishedAt"]})
            last = BYOD_SNAP_LAST.get(t["tenantIdHash"], 0)
            if time.monotonic() - last < SNAP_MIN_INTERVAL:
                return self._json({"ok": False, "error": "rate_limited"}, 429)
            BYOD_SNAP_LAST[t["tenantIdHash"]] = time.monotonic()
            published = iso_now()
            BYOD_SNAPSHOTS[slug] = {"v": 1, "canvas": canvas, "canvasTitle": canvas_title,
                                    "transcript": transcript, "mindName": mind_name,
                                    "capturedAt": captured, "publishedAt": published,
                                    "contentHash": chash}
            t["lastSnapshotAt"] = published
            if mind_name and not t.get("mindName"): t["mindName"] = mind_name
            self._json({"ok": True, "publishedAt": published})
        else:
            self._json({"ok": False, "error": "not_found"}, 404)

    def do_DELETE(self):
        p = self.path.split("?")[0]
        m = re.match(r"^/d/([^/]+)$", p)
        if m and self.headers.get("X-Tab-Key") == ADMIN_KEY:
            slug = m.group(1)
            t = BYOD_TENANTS.pop(slug, None) if valid_slug(slug) else None
            if t:
                BYOD_SNAPSHOTS.pop(slug, None)
                BYOD_OWNERS.pop(t["tenantIdHash"], None)
                BYOD_TOMBS[slug] = {"tenantIdHash": t["tenantIdHash"], "releasedAt": iso_now()}
            return self._json({"ok": True, "removed": bool(t)})
        self._json({"ok": False, "error": "method_not_allowed"}, 405)

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Localhost mock of the minds-chat-proxy Worker (BYOD QA).")
    ap.add_argument("--port", type=int, default=8787,
                    help="port to bind on 127.0.0.1 (default 8787)")
    args = ap.parse_args()  # unknown arguments fail loudly (exit 2)
    HTTPServer(("127.0.0.1", args.port), H).serve_forever()
