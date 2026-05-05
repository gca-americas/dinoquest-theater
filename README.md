# dino-theater — Pub/Sub plumbing setup

dino-theater is the live visualization of the agent team at work. It subscribes to the
`harness-events` Pub/Sub topic that DinoAgent, CIAgent, and CDAgent all publish to.
Every meaningful action — A2A calls, skill invocations, memory writes, traffic shifts —
arrives as a structured JSON event and drives what you see on screen.

---

## Event schema

Every message on `harness-events` is a JSON-encoded string with this shape:

```json
{
  "timestamp": "2026-04-30T10:15:30.123456+00:00",
  "agent": "DinoAgent",
  "event_type": "skill_invoked",
  "payload": { "error_preview": "Memory limit of 128 MiB exceeded..." },
  "correlation_id": "session-12345"
}
```

| Field | Values |
|---|---|
| `agent` | `DinoAgent`, `CIAgent`, `CDAgent` |
| `event_type` | see table below |
| `correlation_id` | Pub/Sub message ID or A2A request ID — ties related events together |

### Event types

| `event_type` | Emitted by | Key payload fields |
|---|---|---|
| `chat_message_received` | DinoAgent | `message`, `user`, `space` |
| `detected_error` | DinoAgent | `error_preview` |
| `thinking` | any | `summary` |
| `pipeline_step` | any | `step` |
| `a2a_call_sent` | DinoAgent, CIAgent | `target_agent`, `method`, `args_preview` |
| `a2a_call_received` | CIAgent, CDAgent | `from_agent`, `method`, `args_preview` |
| `skill_registered` | CIAgent | `skill_name`, `description` |
| `memory_written` | CDAgent | `collection`, `key`, `summary` |
| `traffic_shifted` | CDAgent | `service`, `revision`, `percent` |

---

## Station routing

Each event is routed to one of six stations based on its text content. `pipeline_step` events go directly to `stationOf()`; `thinking` events first check the cloud override (any text matching `oom|root cause|log|heap|crash|leak|monitoring|pulling cloud` → **Cloud**), then fall through to `stationOf()`.

### RemediationAgent (agent = `DinoAgent`)

| Tool / trigger | Event type | Sample text | Station |
|---|---|---|---|
| Pub/Sub message received | `detected_error` | `🚨 <error_preview>` | **Cloud** |
| `clone_repo` | `pipeline_step` | `fix: cloning repository` | **Source** |
| `apply_code_fix` | `pipeline_step` | `fix: editing backend/main.py` | **Source** |
| `rollback_fix` | `pipeline_step` | `fix: reverting branch incident_26050202` | **Source** |
| `rollback_traffic` | `thinking` | `Rolling back Cloud Run svc → rev (100% traffic)` | **Cloud Run** |
| `update_service_env_vars` | `thinking` | `Updating Cloud Run svc env vars: KEY` | **Cloud Run** |
| `update_service_resources` | `thinking` | `Patching Cloud Run service svc: memory → 2Gi` | **Cloud Run** |
| `commit_to_incident_branch` | `thinking` | `Pushing branch: committing fix — <msg>` | **GitHub** |
| `open_pull_request` | `thinking` | `Opening pull request: <title>` | **GitHub** |
| `announce_a2a_to_ci` | `a2a_call_sent` | *(A2A badge + animated dot to CIAgent)* | — |

### CIAgent

| Tool / trigger | Event type | Sample text | Station |
|---|---|---|---|
| `get_pr` | `thinking` | `Generating summary for PR #42` | **GitHub** |
| `get_pr_files` | `thinking` | `Detecting changed files in PR #42` | **GitHub** |
| `scan_pr_diff` | `thinking` | `Classifying scope and security scan of PR #42 diff` | **GitHub** |
| `post_pr_comment` | `thinking` | `Posting CI report to GitHub PR #42` | **GitHub** |
| `submit_build` | `thinking` | `Submitting Cloud Build job for branch incident_xxx` | **Cloud Build** |
| `run_ci_backend_tests` | `pipeline_step` | `Cloud Build: running backend pytest for incident_xxx` | **Cloud Build** |
| `get_ci_build_status` | `thinking` | `Running test suite — polling build abc123` | **Testing** |
| `announce_a2a_to_cd` | `a2a_call_sent` | *(A2A badge + animated dot to CDAgent)* | — |

### CDAgent

| Tool / trigger | Event type | Sample text | Station |
|---|---|---|---|
| `deploy_revision` | `thinking` | `Deploying new revision for dinoquest-backend` | **Cloud Run** |
| `shift_traffic` | `thinking` | `Shifting 10% traffic to revision-xyz` | **Cloud Run** |
| `poll_metrics` | `thinking` | `Polling canary metrics for revision-xyz` | **Cloud Run** |
| `write_pattern` | `pipeline_step` | `cd report: deployment pattern saved` | **Source** |
| `create_release` | `thinking` | `Creating GitHub release v1.2.3` | **GitHub** |
| Final agent response | `pipeline_step` | `CD report: <summary>` | **Source** |

### `stationOf()` keyword map

| Station | Matching keywords |
|---|---|
| **Source** | `fix:`, `edit file`, `patch code`, `writing code`, `write code`, `writing a fix`, `writing branch`, `cd report`, `paginat`, `add.*limit` |
| **Cloud Build** | `cloud build`, `docker`, `artifact`, `registry`, `image push`, `build success` |
| **Testing** | `pytest`, `\d+ test`, `test suite`, `lint` |
| **Cloud Run** | `deploy`, `traffic`, `canary`, `cloud run`, `spa asset`, `promote`, `revision.*deploy`, `pre.scal` |
| **Cloud** | `monitor`, `error rate`, `latency`, `p95`, `metric`, `oom`, `log`, `heap`, `crash`, `risk`, `resolve gcp`, `pulling cloud`, `root cause`, `memory` |
| **GitHub** | `github`, `pr `, `pull request`, `branch`, `commit`, `push`, `release`, `classify`, `scope`, `security scan`, `secret`, `report`, `summary` |

---

## Run locally

```bash
cd dino-theater
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file:

```bash
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
# Optional — overrides the default subscription name
# PUBSUB_SUBSCRIPTION=projects/your-project/subscriptions/harness-events-theater
```

Start the server:

```bash
python server.py
# → http://localhost:8888
```

Open `http://localhost:8888` in a browser window resized to ~20% of screen height (full width).

**No Pub/Sub yet? Use demo mode:**

```bash
curl http://localhost:8888/demo
```

This plays the built-in 35-event keynote sequence — DinoAgent detects an OOM crash, CIAgent runs the full CI pipeline, CDAgent deploys with a canary and promotes to 100% — so you can see all the animations without any agents running.

---

## Demo playback

`/demo` plays the current event cache in order, honoring the `delay` field on each event (seconds to wait before sending it). The default speed multiplier is 3× (i.e. delays are tripled).

**Play the demo:**
```bash
curl http://localhost:8888/demo
```

**Change playback speed** (1.0 = real-time, 3.0 = 3× slower, 0.5 = 2× faster):
```bash
curl -X POST http://localhost:8888/demo/speed \
  -H 'Content-Type: application/json' \
  -d '{"speed": 2.0}'
```

**Inspect the current event cache:**
```bash
curl http://localhost:8888/cache
```

**Replace the cache with custom events:**
```bash
curl -X POST http://localhost:8888/cache \
  -H 'Content-Type: application/json' \
  -d '{"events": [
    {"delay":0,  "agent":"DinoAgent","event_type":"thinking","payload":{"summary":"investigating OOM..."}},
    {"delay":3,  "agent":"CIAgent",  "event_type":"pipeline_step","payload":{"step":"running pytest"}},
    {"delay":2,  "agent":"CDAgent",  "event_type":"traffic_shifted","payload":{"service":"dinoquest","percent":10}}
  ]}'
```

**Append events to the existing cache** (without wiping it):
```bash
curl -X POST http://localhost:8888/cache/append \
  -H 'Content-Type: application/json' \
  -d '{"events": [{"delay":1,"agent":"DinoAgent","event_type":"thinking","payload":{"summary":"all clear"}}]}'
```

**Restore the built-in demo sequence:**
```bash
curl -X POST http://localhost:8888/cache/reset
```

---

## Recording live events for replay

When agents are running against real Pub/Sub, you can record the live event stream — with accurate inter-arrival timing — and replay it later as a demo.

**1. Start recording** (clears any previous buffer):
```bash
curl -X POST http://localhost:8888/record/start
```

**2. Trigger your agents** — run the incident scenario, let the full pipeline execute. Every Pub/Sub event and every `/inject` call is captured with its exact delay (time since previous event, measured with a monotonic clock).

**3. Check what has been captured so far:**
```bash
curl http://localhost:8888/record/status
# → {"recording": true, "buffered": 18, "preview": [...last 3 events...]}
```

**4. Stop recording and save to the cache:**
```bash
curl -X POST http://localhost:8888/record/stop
# → {"captured": 34, "saved": true}
```

Stop without overwriting the cache (inspect first):
```bash
curl -X POST http://localhost:8888/record/stop \
  -H 'Content-Type: application/json' \
  -d '{"save": false}'
```

**5. Play it back with the same timing:**
```bash
curl http://localhost:8888/demo
```

The recording is held in memory — it survives until the server restarts or you call `/record/start` again. To persist it across restarts, save the output of `GET /cache` to a file and restore it via `POST /cache` on next startup.

**Inject a single event:**

```bash
# DinoAgent starts thinking
curl -X POST http://localhost:8888/inject \
  -H 'Content-Type: application/json' \
  -d '{"agent":"DinoAgent","event_type":"thinking","payload":{"summary":"analyzing build failure pattern..."}}'

# CIAgent receives an A2A call from DinoAgent (agent activates with ← label)
curl -X POST http://localhost:8888/inject \
  -H 'Content-Type: application/json' \
  -d '{"agent":"CIAgent","event_type":"a2a_call_received","payload":{"from_agent":"DinoAgent","message_preview":"run CI for PR #42 on feat/volcano-dodge"}}'

# Animated dot flies from CIAgent → DinoAgent
curl -X POST http://localhost:8888/inject \
  -H 'Content-Type: application/json' \
  -d '{"agent":"CIAgent","event_type":"a2a_call_sent","payload":{"target_agent":"DinoAgent","method":"analyze_failure","args_preview":"build failed: OOM in test step"}}'

# CIAgent learns a new skill — sparkle in log
curl -X POST http://localhost:8888/inject \
  -H 'Content-Type: application/json' \
  -d '{"agent":"CIAgent","event_type":"skill_registered","payload":{"skill_name":"oom-recovery","description":"Split test matrix on OOM","source":"DinoAgent"}}'

# CDAgent shifts canary traffic
curl -X POST http://localhost:8888/inject \
  -H 'Content-Type: application/json' \
  -d '{"agent":"CDAgent","event_type":"traffic_shifted","payload":{"service":"dinoquest","revision":"dinoquest-00042-abc","percent":10,"stable_revision":"dinoquest-00041-xyz"}}'

# CDAgent writes a deployment pattern to memory
curl -X POST http://localhost:8888/inject \
  -H 'Content-Type: application/json' \
  -d '{"agent":"CDAgent","event_type":"memory_written","payload":{"collection":"cdagent_deployment_patterns","key":"routing-change","summary":"canary=10% promote_in=300s"}}'

# Human triggers CIAgent via Slack
curl -X POST http://localhost:8888/inject \
  -H 'Content-Type: application/json' \
  -d '{"agent":"CIAgent","event_type":"chat_message_received","payload":{"platform":"slack","user":"christina","message":"build volcano-dodge at SHA abc123"}}'
```

Each event type drives a different animation — use these to rehearse the keynote story beat by beat without needing any live agents.

**With Pub/Sub running**, make sure ADC is configured and the subscription exists (Section 3 below), then trigger any agent — events appear in real time.

## Quick Deploy (Cloud Run)

1. **Build and push the container:**
   ```bash
   PROJECT_ID=$(gcloud config get-value project)
   gcloud builds submit --tag us-central1-docker.pkg.dev/$PROJECT_ID/dino-theater .
   ```

2. **Set up Service Account & Permissions:**
   ```bash
   # Create the service account
   gcloud iam service-accounts create dino-theater --project=$PROJECT_ID

   # Create the subscription (if you havent yet)
   gcloud pubsub subscriptions create harness-events-theater \
     --topic=harness-events --project=$PROJECT_ID

   # Grant subscriber role
   gcloud pubsub subscriptions add-iam-policy-binding harness-events-theater \
     --member="serviceAccount:dino-theater@${PROJECT_ID}.iam.gserviceaccount.com" \
     --role="roles/pubsub.subscriber" \
     --project=$PROJECT_ID
   ```

3. **Deploy:**
   ```bash
   gcloud run deploy dino-theater \
     --image gcr.io/$PROJECT_ID/dino-theater \
     --region=us-central1 \
     --service-account=dino-theater@$PROJECT_ID.iam.gserviceaccount.com \
     --set-env-vars="GOOGLE_CLOUD_PROJECT=$PROJECT_ID" \
     --allow-unauthenticated \
     --min-instances=1 \
     --project=$PROJECT_ID
   ```

---

## Deploy to Cloud Run (Detailed)

**1. Create a service account for dino-theater:**

```bash
PROJECT_ID=$(gcloud config get-value project)
gcloud iam service-accounts create dino-theater \
  --display-name="dino-theater" --project=$PROJECT_ID
```

**2. Build and push the image:**

```bash
gcloud builds submit --tag gcr.io/$PROJECT_ID/dino-theater .
```

**3. Deploy:**

```bash
gcloud run deploy dino-theater \
  --image gcr.io/$PROJECT_ID/dino-theater \
  --region=us-central1 \
  --service-account=dino-theater@$PROJECT_ID.iam.gserviceaccount.com \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=$PROJECT_ID" \
  --allow-unauthenticated \
  --min-instances=1 \
  --project=$PROJECT_ID
```

`--allow-unauthenticated` is fine here — dino-theater is read-only and serves only the visualization page.

`--min-instances=1` keeps the SSE connection alive between events (no cold-start drops).

**4. Open the service URL** in a browser window sized to ~20% of screen height.

**5. To run the demo sequence against the live deployment:**

```bash
curl https://dino-theater-xxx-uc.a.run.app/demo
```

---

## 1. Create the Pub/Sub topic

Run once per GCP project:

```bash
PROJECT_ID=$(gcloud config get-value project)
gcloud pubsub topics create harness-events --project=$PROJECT_ID
```

---

## 2. Grant each agent permission to publish

Run each command after the corresponding agent's service account exists (i.e. after that
agent has been deployed to Cloud Run at least once). Do not run these all at once upfront —
the service accounts for CIAgent and CDAgent don't exist until those agents are deployed.

```bash
PROJECT_ID=$(gcloud config get-value project)

# After DinoAgent is deployed:
gcloud pubsub topics add-iam-policy-binding harness-events \
  --member="serviceAccount:remediation-agent@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/pubsub.publisher" \
  --project=$PROJECT_ID

# After CIAgent is deployed:
gcloud pubsub topics add-iam-policy-binding harness-events \
  --member="serviceAccount:ci-agent@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/pubsub.publisher" \
  --project=$PROJECT_ID

# After CDAgent is deployed:
gcloud pubsub topics add-iam-policy-binding harness-events \
  --member="serviceAccount:cd-agent@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/pubsub.publisher" \
  --project=$PROJECT_ID
```

---

## 3. Create the pull subscription for dino-theater

dino-theater's WebSocket bridge pulls from this subscription and forwards events
to connected browsers:

```bash
gcloud pubsub subscriptions create harness-events-theater \
  --topic=harness-events \
  --ack-deadline=10 \
  --project=$PROJECT_ID
```

---

## 4. Grant dino-theater permission to pull

```bash
THEATER_SA="dino-theater@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud pubsub subscriptions add-iam-policy-binding harness-events-theater \
  --member="serviceAccount:${THEATER_SA}" \
  --role="roles/pubsub.subscriber" \
  --project=$PROJECT_ID
```

---

## 5. Tell each agent where to publish

Set `HARNESS_EVENTS_TOPIC` on each Cloud Run service. Emission is fire-and-forget —
agents continue working normally if the topic is unreachable.

Run each after the corresponding service exists in Cloud Run:

```bash
PROJECT_ID=$(gcloud config get-value project)
TOPIC="projects/${PROJECT_ID}/topics/harness-events"

# After DinoAgent is deployed:
gcloud run services update remediation-agent \
  --set-env-vars="HARNESS_EVENTS_TOPIC=${TOPIC}" \
  --region=us-central1 --project=$PROJECT_ID

# After CIAgent is deployed:
gcloud run services update ci-agent \
  --set-env-vars="HARNESS_EVENTS_TOPIC=${TOPIC}" \
  --region=us-central1 --project=$PROJECT_ID

# After CDAgent is deployed:
gcloud run services update cd-agent \
  --set-env-vars="HARNESS_EVENTS_TOPIC=${TOPIC}" \
  --region=us-central1 --project=$PROJECT_ID
```

For local dev, add to each agent's `.env`:

```
HARNESS_EVENTS_TOPIC=projects/your-project-id/topics/harness-events
```

---

## 6. Verify events are flowing

Pull messages manually after triggering an agent:

```bash
gcloud pubsub subscriptions pull harness-events-theater \
  --limit=10 \
  --auto-ack \
  --project=$PROJECT_ID
```

Watch a live stream (useful during rehearsal):

```bash
PROJECT_ID=$(gcloud config get-value project)
while true; do
  gcloud pubsub subscriptions pull harness-events-theater \
    --limit=5 --auto-ack --format=json --project=$PROJECT_ID \
  | python3 -c "
import json, sys
msgs = json.load(sys.stdin)
for m in msgs:
    raw = m.get('message', {}).get('data', '')
    import base64
    data = json.loads(base64.b64decode(raw))
    ts = data.get('timestamp','')[-8:]
    print(f\"{ts}  {data.get('agent','?'):12}  {data.get('event_type','?'):25}  {str(data.get('payload',''))[:80]}\")
" 2>/dev/null
  sleep 2
done
```

---

## Architecture

```
DinoAgent  ──┐
CIAgent    ──┼──▶  Pub/Sub topic: harness-events
CDAgent    ──┘              │
                            │ (pull subscription: harness-events-theater)
                            ▼
              server.py — Flask SSE bridge (Cloud Run)
                    │  Server-Sent Events (/events)
                    ▼
              index.html — 20vh × 100vw visualization strip
              • Three agent nodes with animated connecting lines
              • Glowing dot travels between agents on A2A calls
              • Agent rings pulse while thinking, glow while active
              • Live event log scrolls on the right
```

`server.py` runs a background thread that subscribes to `harness-events-theater` and
broadcasts each message to all connected SSE clients. The browser reconnects automatically
if the SSE stream drops.

`GET /demo` replays the event cache (built-in or recorded) with per-event delays.
`POST /record/start` + `POST /record/stop` captures a live run with real timing for later replay.

---

## Sample Pipeline Run — incident_2605051411 (2026-05-05)

Full end-to-end run triggered by an OOM on `dinoquest`. All gaps and active durations > 30 s are
capped to 30 s for demo pacing (marked ✂️ with the actual time in parentheses).
Raw totals: 22 m 1 s wall-clock; ~10 m 31 s active.

| # | Agent | Time | ← gap | Active | Station | Event | Detail |
|---|---|---|---|---|---|---|---|
| 1 | RemediationAgent | 14:11:21 | — | — | ☁️ Cloud | Event received | OOM 128→130 MiB on dinoquest |
| 2 | RemediationAgent | 14:11:26 | 5 s | 5 s | 🚀 Cloud Run | Memory bump | 128Mi → 256Mi via `update_service_resources` |
| 3 | RemediationAgent | 14:11:26–14:12:32 | 0 s | 30 s ✂️ (66 s) | 💾 Source | Root-cause track | clone→read→fix→test→commit→PR #65 |
| 4 | RemediationAgent | 14:12:39 | 7 s | — | 🐙 GitHub + A2A dot | Handoff | Slack notification + A2A to CIAgent |
| — | *transit* | 14:12:39–14:13:57 | 0 s | 30 s ✂️ (78 s) | *(A2A dot in flight)* | Remediation → CI | CIAgent warm instance startup |
| 5 | CIAgent | 14:13:57 | 0 s | — | *(A2A badge)* | Session started | A2A call received from RemediationAgent |
| 6 | CIAgent | 14:14:29–14:15:09 | 30 s ✂️ (32 s) | 30 s ✂️ (40 s) | 🐙 GitHub | `list_prs` | 1 SSL retry; found PR #65 |
| 7 | CIAgent | 14:16:05–14:18:27 | 30 s ✂️ (56 s) | 30 s ✂️ (2 m 22 s) | 🐙 GitHub | `scan_pr_diff` | SSL retries; diff_len=2644 chars |
| 8 | CIAgent | 14:19:22–14:19:44 | 30 s ✂️ (55 s) | 22 s | 🐙 GitHub | `post_pr_comment` | PR summary posted — HTTP 201 |
| 9 | CIAgent | 14:20:33–14:21:39 | 30 s ✂️ (49 s) | 30 s ✂️ (1 m 6 s) | 🏗️ Cloud Build | `run_ci_backend_tests` | pytest SUCCESS — all tests passed |
| 10 | CIAgent | 14:22:26–14:24:56 | 30 s ✂️ (47 s) | 30 s ✂️ (2 m 30 s) | 🏗️ Cloud Build → 🧪 Testing | `submit_build` + poll | Cloud Build Docker image — SUCCESS |
| 11 | CIAgent | 14:25:49–14:26:03 | 30 s ✂️ (53 s) | 14 s | 🏗️ Cloud Build | `verify_image` | app:latest confirmed in Artifact Registry |
| 12 | CIAgent | 14:26:51 | 30 s ✂️ (48 s) | — | 🐙 GitHub | `post_commit_status` | GitHub commit status → success |
| 13 | CIAgent | 14:28:02–14:28:24 | 30 s ✂️ (1 m 11 s) | 22 s | 🐙 GitHub | `post_pr_comment` | CI Pipeline Report posted — HTTP 201 |
| 14 | CIAgent | 14:32:32 | 30 s ✂️ (4 m 8 s) | — | *(A2A dot)* | CDAgent A2A | `announce_a2a_to_cd` — HTTP 200 ACK |
| 15 | CIAgent | 14:32:34 | 2 s | — | — | Runner closed | CIAgent session complete |
| — | *transit* | 14:32:34–14:32:35 | 0 s | 1 s | *(A2A dot in flight)* | CI → CD | A2A over internal Cloud Run network |
| 16 | CDAgent | 14:32:35 | 0 s | — | 🚀 Cloud Run | `get_stable_revision` | dinoquest-00006-jxr identified as stable |
| 17 | CDAgent | 14:32:37 | 2 s | 2 s | 💾 Source | `read_patterns` | no matching deployment pattern found |
| 18 | CDAgent | 14:32:40–14:33:04 | 3 s | 24 s | 🚀 Cloud Run | `deploy_revision` | dinoquest-00007-l87 deployed successfully |
| 19 | CDAgent | 14:33:06–14:33:10 | 2 s | 4 s | 🚀 Cloud Run | `shift_traffic` 50% | canary live — 50% to new revision |
| 20 | CDAgent | 14:33:11 | 1 s | — | 🚀 Cloud Run | `poll_metrics` | 0% error rate — verdict OK, promoting |
| 21 | CDAgent | 14:33:14–14:33:19 | 3 s | 5 s | 🚀 Cloud Run | `shift_traffic` 100% | promoted — new revision live |
| 22 | CDAgent | 14:33:22 | 3 s | — | 💾 Source | `write_pattern` | deployment pattern saved to Firestore |

**Total wall-clock:** 14:11:21 → 14:33:22 = **22 m 1 s**  
**Outcome:** PR #65 merged; `dinoquest-00007-l87` at 100% traffic.  
**Persisted:** `demo_pipeline_runs/incident_2605051411` in Firestore (`io26-keynote-demo-staging`).

### Recording a new pipeline run

After a live incident, record the run to Firestore for demo replay:

```bash
# 1. Activate the RemediationAgent venv (it has google-cloud-firestore)
cd /Users/christina/Desktop/work/io
source RemediationAgent/.venv/bin/activate

# 2. Edit record_pipeline_run.py — update RUN_ID, timestamps, and step details

# 3. Run it (uses Application Default Credentials from gcloud auth)
GOOGLE_CLOUD_PROJECT=io26-keynote-demo-staging python3 record_pipeline_run.py
# → Wrote summary to demo_pipeline_runs/<run_id>
# → Wrote N steps to demo_pipeline_runs/<run_id>/steps/
```

The script lives at `/Users/christina/Desktop/work/io/record_pipeline_run.py`.
All runs land in the `demo_pipeline_runs` Firestore collection under the `io26-keynote-demo-staging` project.

---

## Reset between dress rehearsals

Discard all backlogged messages so the next run starts clean:

```bash
gcloud pubsub subscriptions seek harness-events-theater \
  --time=$(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --project=$PROJECT_ID
```

Also reset CDAgent's Firestore memory if you want Behavior A (pattern recognition)
to replay from scratch:

```bash
# Deletes all docs in the cdagent_deployment_patterns collection
gcloud firestore documents delete \
  --collection=cdagent_deployment_patterns \
  --project=$PROJECT_ID \
  --quiet 2>/dev/null || \
firebase firestore:delete --project=$PROJECT_ID --recursive cdagent_deployment_patterns
```
