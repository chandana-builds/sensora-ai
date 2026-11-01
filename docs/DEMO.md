# Demonstration guide

Before you present: open `https://<render>/api/health/live` (wakes the free server, ~1 min), confirm the badge shows what you intend (**LIVE · Meta models** vs **DEMO MODE · simulated**), and allow camera/mic in the browser. Use HTTPS (camera/mic need a secure context). Keep evidence-saving **off**.

## Primary path (live device, live models)
1. Open the app → **Continue as guest** (or sign in). Point out the LIVE badge.
2. **Start a new session**; choose Beginner.
3. Click **Speak**, describe the problem naturally ("my Wi-Fi light is orange and there's no internet"), **Stop & transcribe**, check the text, **Send**.
4. **Start camera**, show the router/stove, **Capture frame**, send. Sensora states what it can see and its confidence.
5. It gives **one** instruction. Do it.
6. Show the result: capture a frame, then **I've done this step**.
7. Point at the two flags: *you reported done* vs *verified on camera*. If the view is unclear it asks for a better one instead of assuming.
8. Next decision: next safe step, resolved, or escalation.
9. **End & review session** → transcript, steps, observations → **Preview report** → tick consent → **Download**.
10. Back to **All sessions**: it's in history; **Resume** works.
Safety beat (optional, 20 s): type "I can smell gas near the stove" → immediate stop + professional-help message, no instructions.

## Fallback A: no physical device (still live models)
Hold up a phone showing a router photo or any appliance picture, or use a printed picture; the flow is identical. Say clearly it's a photo.

## Fallback B: network/Meta/venue failure (guaranteed offline-ish path)
Run locally in **DEMO mode**: `AI_MODE=demo uvicorn app.main:app` + `npm run dev` (or `python backend/scripts/run_demo_scenario.py` in a terminal). The badge says **DEMO MODE · simulated, not real AI**; every reply is prefixed "[Simulated demo]"; camera analysis is canned and ignores the image; there is no voice transcription (type instead); verification never shows "verified". Tell the audience this. `DEMO_SCENARIO=router|induction` selects the script (the induction one matches the Prestige stove backup device).
Script (router): "My internet is down, the light is orange" → "beginner, here's the router" (capture) → "I checked the power" (done) → "I restarted it" (done) → "I pushed the cable in" (done) → escalation → summary → report.

## If something breaks live
Camera denied → click the lock icon, allow, Start camera again (typed input works meanwhile). Mic denied → type. "Can't reach server" → wait 60 s (cold start) and retry. 429 → wait a minute. AI error banner → retry; switch to Fallback B.
