"""Prove a DEPLOYED backend works:  python scripts/smoke_test.py https://your-api.onrender.com [--origin https://your-app.vercel.app]
Exits non-zero on the first failure. Prints exactly what was verified, so you can quote it honestly."""
import json
import sys
import time
import urllib.error
import urllib.request


def call(base, method, path, body=None, token=None, origin=None, timeout=90):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    if origin:
        h["Origin"] = origin
    req = urllib.request.Request(base + path, method=method, headers=h, data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), (json.loads(r.read() or b"null"))
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, dict(e.headers), json.loads(raw)
        except ValueError:
            return e.code, dict(e.headers), raw.decode(errors="replace")[:200]


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail else ""))
    if not ok:
        sys.exit(1)


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    base = args[0].rstrip("/")
    origin = args[args.index("--origin") + 1] if "--origin" in args else None
    t = time.time()
    s, _, b = call(base, "GET", "/api/health/live", timeout=120)   # first call may wake a sleeping free-tier instance
    check("liveness", s == 200, f"{time.time() - t:.1f}s incl. possible cold start")
    s, _, b = call(base, "GET", "/api/health")
    check("deep health (database reachable)", s == 200 and b["storage"]["ok"], f"storage={b['storage']['backend']}")
    print(f"INFO AI mode = {b['ai']['mode']} ({'SIMULATED demo' if b['ai']['simulated'] else 'live Meta models configured'}), accounts={b['auth']['accounts']}, guest={b['auth']['guest']}")
    s, _, _ = call(base, "GET", "/api/sessions")
    check("private routes reject anonymous callers", s == 401)
    s, _, _ = call(base, "GET", "/api/sessions", token="anon.AAAAAAAAAAAAAAAAAAAAAA.forged")
    check("forged token rejected", s == 401)
    if origin:
        req = urllib.request.Request(base + "/api/sessions", method="OPTIONS", headers={"Origin": origin, "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "authorization"})
        with urllib.request.urlopen(req, timeout=30) as r:
            check("CORS allows your frontend origin", r.headers.get("Access-Control-Allow-Origin") == origin)
        req = urllib.request.Request(base + "/api/sessions", method="OPTIONS", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                check("CORS blocks other origins", r.headers.get("Access-Control-Allow-Origin") is None)
        except urllib.error.HTTPError:
            check("CORS blocks other origins", True)
    s, _, g = call(base, "POST", "/api/auth/guest")
    if s != 200:
        print("INFO guest access disabled; sign in with a real account to test sessions (skipping session checks)")
        return print("\nSMOKE TEST PASSED (partial)")
    tok = g["token"]
    s, _, sess = call(base, "POST", "/api/sessions", {}, tok)
    check("create session", s == 201)
    sid = sess["id"]
    s, _, r = call(base, "POST", f"/api/sessions/{sid}/agent/turn", {"text": "My internet is not working and the router light is orange."}, tok)
    check("AI turn returns a structured answer", s == 200 and r["response"]["assistant_message"], f"mode={r.get('mode')} simulated={r.get('simulated')} state={r.get('workflow_state')}")
    s, _, r = call(base, "POST", f"/api/sessions/{sid}/agent/turn", {"text": "I can smell gas near it"}, tok)
    check("safety stop works", s == 200 and r["response"]["safety_status"] == "stop" and r["workflow_state"] == "escalation_required")
    s, _, m = call(base, "GET", f"/api/sessions/{sid}/memory", token=tok)
    check("history persisted", s == 200 and len(m["messages"]) == 4, f"{len(m['messages'])} messages")
    s, _, other = call(base, "POST", "/api/auth/guest")
    s, _, _ = call(base, "GET", f"/api/sessions/{sid}", token=other["token"])
    check("another user cannot open this session", s == 404)
    s, _, h = call(base, "GET", f"/api/sessions/{sid}/handoff", token=tok)
    check("technician report preview", s == 200 and h["disclaimers"])
    s, _, _ = call(base, "POST", f"/api/sessions/{sid}/handoff/export", {"consent_to_share": False}, tok)
    check("export refused without consent", s == 403)
    call(base, "DELETE", "/api/me/data", token=tok)
    call(base, "DELETE", "/api/me/data", token=other["token"])
    print("\nSMOKE TEST PASSED. (Voice, camera and live-model quality still need a manual check in a browser; see docs/DEMO.md.)")


if __name__ == "__main__":
    main()
