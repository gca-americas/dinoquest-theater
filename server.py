"""dino-theater server — SSE bridge between Pub/Sub and the browser.

Serves index.html at / and streams Pub/Sub events as SSE at /events.
Run locally: python server.py
Demo mode:   curl http://localhost:8888/demo   (plays a canned event sequence)
"""

import json
import os
import queue
import threading
import time

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, Response, request, send_from_directory, stream_with_context
from flask_cors import CORS

app = Flask(__name__, static_folder=".")
CORS(app)

PROJECT      = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
SUBSCRIPTION = os.environ.get(
    "PUBSUB_SUBSCRIPTION",
    f"projects/{PROJECT}/subscriptions/harness-events-theater" if PROJECT else "",
)

_clients: list[queue.Queue] = []
_clients_lock = threading.Lock()


def _broadcast(event: dict) -> None:
    with _clients_lock:
        dead = []
        for q in _clients:
            try:
                q.put_nowait(event)
            except queue.Full:
                dead.append(q)
        for q in dead:
            _clients.remove(q)


# ── Recording ─────────────────────────────────────────────────────────────────
#
# When _recording is True, every event that passes through _record_event()
# gets stamped with "delay" = seconds since the previous event arrived.
# Stop recording to promote the buffer into _event_cache.

_recording       = False
_record_buf: list[dict] = []
_record_lock     = threading.Lock()
_last_record_t   = None   # time.monotonic() of last recorded event


def _record_event(event: dict) -> None:
    """Stamp event with inter-arrival delay and append to buffer."""
    global _last_record_t
    now = time.monotonic()
    with _record_lock:
        delay = round(now - _last_record_t, 3) if _last_record_t is not None else 0.0
        _last_record_t = now
        _record_buf.append({**event, "delay": delay})


def _pull_pubsub() -> None:
    if not SUBSCRIPTION:
        return
    from google.cloud import pubsub_v1
    subscriber = pubsub_v1.SubscriberClient()

    def callback(message):
        try:
            event = json.loads(message.data.decode())
            if _recording:
                _record_event(event)
            _broadcast(event)
        except Exception:
            pass
        message.ack()

    future = subscriber.subscribe(SUBSCRIPTION, callback=callback)
    try:
        future.result()
    except Exception:
        pass


threading.Thread(target=_pull_pubsub, daemon=True).start()


# ── SSE endpoint ──────────────────────────────────────────────────────────────

@app.route("/events")
def events():
    q: queue.Queue = queue.Queue(maxsize=50)
    with _clients_lock:
        _clients.append(q)

    def generate():
        try:
            while True:
                try:
                    msg = q.get(timeout=25)
                    yield f"data: {json.dumps(msg)}\n\n"
                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            with _clients_lock:
                try:
                    _clients.remove(q)
                except ValueError:
                    pass

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Demo script ───────────────────────────────────────────────────────────────
#
# Full incident story:
#   Phase 1 — DinoAgent detects OOM crash, fixes root cause, opens GitHub PR
#   Phase 2 — CIAgent runs the full CI pipeline (classify → test → build → report)
#   Phase 3 — CDAgent runs the full CD pipeline (risk → canary → monitor → promote)
#
# Each event has a "delay" field (seconds to wait after the previous event).

DEMO_EVENTS = [

    # ── Phase 1: DinoAgent detects production OOM ─────────────────────────────
    {"delay": 0, "agent": "DinoAgent", "event_type": "chat_message_received",
     "payload": {"platform": "slack", "user": "oncall",
                 "message": "🚨 dinoquest OOM crash — leaderboard endpoint"},
     "correlation_id": "incident-001"},

    {"delay": 2.0, "agent": "DinoAgent", "event_type": "thinking",
     "payload": {"summary": "Pulling Cloud Monitoring logs for the last 30 min…"},
     "correlation_id": "incident-001"},

    {"delay": 2.5, "agent": "DinoAgent", "event_type": "thinking",
     "payload": {"summary": "Root cause: leaderboard query loads all 50k rows — no pagination"},
     "correlation_id": "incident-001"},

    {"delay": 2.0, "agent": "DinoAgent", "event_type": "thinking",
     "payload": {"summary": "Fix: paginate with limit=50 + cursor. Writing branch fix/leaderboard-oom"},
     "correlation_id": "incident-001"},

    {"delay": 2.0, "agent": "DinoAgent", "event_type": "thinking",
     "payload": {"summary": "Branch pushed. Opening PR #43: fix/leaderboard-oom → main"},
     "correlation_id": "incident-001"},

    {"delay": 2.0, "agent": "DinoAgent", "event_type": "a2a_call_sent",
     "payload": {"target_agent": "CIAgent", "method": "run_ci_pipeline",
                 "args_preview": "Run CI for PR #43: fix/leaderboard-oom"},
     "correlation_id": "incident-001"},

    # ── Phase 2: CIAgent — full CI pipeline ──────────────────────────────────

    {"delay": 1.0, "agent": "CIAgent", "event_type": "pipeline_step",
     "payload": {"step": "Resolve GCP project → io-demo-2026"},
     "correlation_id": "incident-001"},

    {"delay": 1.5, "agent": "CIAgent", "event_type": "pipeline_step",
     "payload": {"step": "Branch: fix/leaderboard-oom · 2 files changed"},
     "correlation_id": "incident-001"},

    {"delay": 1.5, "agent": "CIAgent", "event_type": "pipeline_step",
     "payload": {"step": "Generate PR summary → scope: BACKEND"},
     "correlation_id": "incident-001"},

    {"delay": 1.5, "agent": "CIAgent", "event_type": "pipeline_step",
     "payload": {"step": "Classify scope: BACKEND (Python only)"},
     "correlation_id": "incident-001"},

    {"delay": 1.5, "agent": "CIAgent", "event_type": "thinking",
     "payload": {"summary": "Security scan: checking diff for secrets & prompt injection…"},
     "correlation_id": "incident-001"},

    {"delay": 2.0, "agent": "CIAgent", "event_type": "pipeline_step",
     "payload": {"step": "✓ Security scan: clean, no secrets found"},
     "correlation_id": "incident-001"},

    {"delay": 1.5, "agent": "CIAgent", "event_type": "thinking",
     "payload": {"summary": "Running pytest backend — 42 tests…"},
     "correlation_id": "incident-001"},

    {"delay": 2.5, "agent": "CIAgent", "event_type": "pipeline_step",
     "payload": {"step": "✓ pytest: 42/42 passed"},
     "correlation_id": "incident-001"},

    {"delay": 1.5, "agent": "CIAgent", "event_type": "gate_passed",
     "payload": {"gate": "Human Verification 1", "decision": "Y",
                 "summary": "PR #43 + test run confirmed"},
     "correlation_id": "incident-001"},

    {"delay": 1.5, "agent": "CIAgent", "event_type": "thinking",
     "payload": {"summary": "Submitting Cloud Build job — building Docker image…"},
     "correlation_id": "incident-001"},

    {"delay": 3.0, "agent": "CIAgent", "event_type": "pipeline_step",
     "payload": {"step": "✓ Cloud Build SUCCESS · image pushed"},
     "correlation_id": "incident-001"},

    {"delay": 1.5, "agent": "CIAgent", "event_type": "pipeline_step",
     "payload": {"step": "✓ Artifact Registry: sha256-abc123 verified"},
     "correlation_id": "incident-001"},

    {"delay": 1.5, "agent": "CIAgent", "event_type": "gate_passed",
     "payload": {"gate": "Human Verification 3", "decision": "Y",
                 "summary": "Trigger build confirmed"},
     "correlation_id": "incident-001"},

    {"delay": 1.5, "agent": "CIAgent", "event_type": "pipeline_step",
     "payload": {"step": "✓ CI report posted to GitHub PR #43"},
     "correlation_id": "incident-001"},

    {"delay": 1.0, "agent": "CIAgent", "event_type": "a2a_call_sent",
     "payload": {"target_agent": "DinoAgent", "method": "ci_complete",
                 "args_preview": "CI passed for PR #43, image sha256-abc123 ready"},
     "correlation_id": "incident-001"},

    # ── DinoAgent hands off to CDAgent ───────────────────────────────────────

    {"delay": 1.0, "agent": "DinoAgent", "event_type": "thinking",
     "payload": {"summary": "CI passed ✓ — forwarding image to CDAgent for canary deploy"},
     "correlation_id": "incident-001"},

    {"delay": 1.5, "agent": "DinoAgent", "event_type": "a2a_call_sent",
     "payload": {"target_agent": "CDAgent", "method": "canary_deploy",
                 "args_preview": "Deploy sha256-abc123 for dinoquest service"},
     "correlation_id": "incident-001"},

    # ── Phase 3: CDAgent — full CD pipeline ──────────────────────────────────

    {"delay": 1.0, "agent": "CDAgent", "event_type": "pipeline_step",
     "payload": {"step": "Resolve GCP project, read PR #43 context"},
     "correlation_id": "incident-001"},

    {"delay": 1.5, "agent": "CDAgent", "event_type": "thinking",
     "payload": {"summary": "Risk score: 3/10 (backend-only paginate fix) → canary 10%, window 10 min"},
     "correlation_id": "incident-001"},

    {"delay": 2.0, "agent": "CDAgent", "event_type": "gate_passed",
     "payload": {"gate": "Human Verification 1", "decision": "Y",
                 "summary": "Canary 10%, 10-min window confirmed"},
     "correlation_id": "incident-001"},

    {"delay": 1.5, "agent": "CDAgent", "event_type": "pipeline_step",
     "payload": {"step": "Pre-scaling instances + creating GitHub deployment"},
     "correlation_id": "incident-001"},

    {"delay": 2.0, "agent": "CDAgent", "event_type": "pipeline_step",
     "payload": {"step": "Revision dinoquest-00043-abc deployed (0% traffic)"},
     "correlation_id": "incident-001"},

    {"delay": 1.5, "agent": "CDAgent", "event_type": "traffic_shifted",
     "payload": {"service": "dinoquest", "revision": "dinoquest-00043-abc",
                 "percent": 10, "stable_revision": "dinoquest-00042-xyz"},
     "correlation_id": "incident-001"},

    {"delay": 1.5, "agent": "CDAgent", "event_type": "pipeline_step",
     "payload": {"step": "✓ SPA asset sanity check: no conflicts"},
     "correlation_id": "incident-001"},

    {"delay": 2.0, "agent": "CDAgent", "event_type": "thinking",
     "payload": {"summary": "Monitor 1/3 · canary error rate 0.1% vs stable 0.3% ✓ OK"},
     "correlation_id": "incident-001"},

    {"delay": 2.5, "agent": "CDAgent", "event_type": "thinking",
     "payload": {"summary": "Monitor 2/3 · P95 latency 180ms vs stable 220ms ✓ OK"},
     "correlation_id": "incident-001"},

    {"delay": 2.5, "agent": "CDAgent", "event_type": "thinking",
     "payload": {"summary": "Monitor 3/3 · all metrics healthy. Ready to promote."},
     "correlation_id": "incident-001"},

    {"delay": 1.5, "agent": "CDAgent", "event_type": "gate_passed",
     "payload": {"gate": "Human Verification 3", "decision": "Y",
                 "summary": "Promote to 100% traffic"},
     "correlation_id": "incident-001"},

    {"delay": 1.5, "agent": "CDAgent", "event_type": "traffic_shifted",
     "payload": {"service": "dinoquest", "revision": "dinoquest-00043-abc", "percent": 100},
     "correlation_id": "incident-001"},

    {"delay": 1.0, "agent": "CDAgent", "event_type": "memory_written",
     "payload": {"collection": "cdagent_deployment_patterns", "key": "backend-paginate-fix",
                 "summary": "canary=10% promote_in=840s, OOM-fix pattern saved"},
     "correlation_id": "incident-001"},

    {"delay": 1.5, "agent": "CDAgent", "event_type": "pipeline_step",
     "payload": {"step": "✓ GitHub Release Tag v2.0.43 + deploy report posted"},
     "correlation_id": "incident-001"},

    {"delay": 1.0, "agent": "CDAgent", "event_type": "a2a_call_sent",
     "payload": {"target_agent": "DinoAgent", "method": "deploy_complete",
                 "args_preview": "100% traffic on v2.0.43, OOM incident resolved"},
     "correlation_id": "incident-001"},

    # ── DinoAgent confirms resolution ─────────────────────────────────────────

    {"delay": 1.0, "agent": "DinoAgent", "event_type": "thinking",
     "payload": {"summary": "✅ OOM incident resolved. dinoquest v2.0.43 live at 100%."},
     "correlation_id": "incident-001"},
]


import copy

# Cached event sequence — starts as the built-in DEMO_EVENTS, can be replaced
# via POST /cache.  Each entry keeps its "delay" key; we never mutate it.
_event_cache: list[dict] = copy.deepcopy(DEMO_EVENTS)

_demo_speed = 3.0   # multiplier; 1.0 = real-time, 3.0 = 3× slower


@app.route("/demo")
def demo():
    """Play the cached event sequence."""
    def play():
        for ev in _event_cache:
            delay = ev.get("delay", 1.5)   # get, not pop — never mutate
            time.sleep(delay * _demo_speed)
            _broadcast({k: v for k, v in ev.items() if k != "delay"})

    threading.Thread(target=play, daemon=True).start()
    return ("", 204)


@app.route("/cache", methods=["GET"])
def get_cache():
    """Return the current cached event sequence."""
    return {"events": _event_cache, "count": len(_event_cache)}


@app.route("/cache", methods=["POST"])
def set_cache():
    """Replace the cached event sequence.

    Body: {"events": [...]}  — list of event dicts, each optionally with a
    "delay" field (seconds).  If omitted, defaults to 1.5 s.

    Example — replace with two custom events:
        curl -X POST http://localhost:8888/cache \\
          -H 'Content-Type: application/json' \\
          -d '{"events": [
                {"delay":1,"agent":"DinoAgent","event_type":"thinking",
                 "payload":{"summary":"investigating issue..."}},
                {"delay":2,"agent":"CIAgent","event_type":"pipeline_step",
                 "payload":{"step":"running tests"}}
              ]}'

    To append events instead of replacing, use POST /cache/append.
    """
    global _event_cache
    body = request.get_json(silent=True) or {}
    events = body.get("events")
    if not isinstance(events, list):
        return {"error": "'events' must be a list"}, 400
    _event_cache = copy.deepcopy(events)
    return {"ok": True, "count": len(_event_cache)}


@app.route("/cache/append", methods=["POST"])
def append_cache():
    """Append events to the cached sequence without replacing it.

    Body: {"events": [...]}
    """
    body = request.get_json(silent=True) or {}
    events = body.get("events")
    if not isinstance(events, list):
        return {"error": "'events' must be a list"}, 400
    _event_cache.extend(copy.deepcopy(events))
    return {"ok": True, "count": len(_event_cache)}


@app.route("/cache/reset", methods=["POST"])
def reset_cache():
    """Restore the cache to the built-in DEMO_EVENTS."""
    global _event_cache
    _event_cache = copy.deepcopy(DEMO_EVENTS)
    return {"ok": True, "count": len(_event_cache)}


# ── Recording endpoints ───────────────────────────────────────────────────────

@app.route("/record/start", methods=["POST"])
def record_start():
    """Start recording live Pub/Sub events with inter-arrival delays.

    Clears any previous recording buffer first.

        curl -X POST http://localhost:8888/record/start
    """
    global _recording, _record_buf, _last_record_t
    with _record_lock:
        _recording     = True
        _record_buf    = []
        _last_record_t = None
    return {"ok": True, "recording": True}


@app.route("/record/stop", methods=["POST"])
def record_stop():
    """Stop recording and promote the buffer to the event cache.

    Optional body: {"save": false} to stop without overwriting the cache.

        curl -X POST http://localhost:8888/record/stop
    """
    global _recording, _event_cache
    body = request.get_json(silent=True) or {}
    save = body.get("save", True)
    with _record_lock:
        _recording = False
        captured   = list(_record_buf)
    if save and captured:
        _event_cache = captured
    return {"ok": True, "recording": False, "captured": len(captured), "saved": save and bool(captured)}


@app.route("/record/status")
def record_status():
    """Return current recording state and buffered event count.

        curl http://localhost:8888/record/status
    """
    with _record_lock:
        return {
            "recording": _recording,
            "buffered":  len(_record_buf),
            "preview":   _record_buf[-3:] if _record_buf else [],
        }


@app.route("/demo/speed", methods=["POST"])
def set_speed():
    """Adjust the demo playback speed multiplier.

    Body: {"speed": 1.0}   — 1.0 = real-time, 3.0 = 3× slower (default)
    """
    global _demo_speed
    body = request.get_json(silent=True) or {}
    speed = body.get("speed")
    if not isinstance(speed, (int, float)) or speed <= 0:
        return {"error": "'speed' must be a positive number"}, 400
    _demo_speed = float(speed)
    return {"ok": True, "speed": _demo_speed}


@app.route("/inject", methods=["POST"])
def inject():
    """Broadcast a single custom event to all connected browsers.

    Expects JSON with at minimum: agent, event_type, payload.
    Missing fields are filled with defaults so quick one-liners work.

    Example:
        curl -X POST http://localhost:8888/inject \\
          -H 'Content-Type: application/json' \\
          -d '{"agent":"CIAgent","event_type":"thinking","payload":{"summary":"running tests"}}'
    """
    body = request.get_json(silent=True) or {}
    if not body.get("agent") or not body.get("event_type"):
        return {"error": "agent and event_type are required"}, 400

    event = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "agent": body["agent"],
        "event_type": body["event_type"],
        "payload": body.get("payload", {}),
        "correlation_id": body.get("correlation_id", "injected"),
    }
    if _recording:
        _record_event(event)
    _broadcast(event)
    return {"ok": True, "event": event}


# ── Static ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(".", "index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8888))
    print(f"dino-theater running at http://localhost:{port}")
    if SUBSCRIPTION:
        print(f"Pub/Sub subscription: {SUBSCRIPTION}")
    else:
        print("No PUBSUB_SUBSCRIPTION set — use /demo to test")
    app.run(host="0.0.0.0", port=port, threaded=True)
