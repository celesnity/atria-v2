# Garage Copilot — Demo Guide ("Vibe Repairing")

You are about to demo this idea: **a technician pairs with an AI copilot to diagnose and fix a
car — the way a developer pairs with a coding agent — and the conversation itself becomes the
work log and the workshop's memory.**

The demo attacks the workshop's five-star bottlenecks directly: diagnosis waiting on the senior
technician, knowledge scattered across people/Zalo/manuals, documentation done after the fact,
and knowledge evaporating when an RO closes.

---

## 1. One-time setup (~3 minutes)

Support services (from the repo root — they may already be running):

```bash
docker compose -f docker-compose.dev.yml -f docker-compose.override.yml up -d db redis qdrant
```

From this branch's checkout (`.worktrees/feature-garage-copilot` or wherever it lives):

```bash
# Python env (once)
uv sync --extra dev
uv pip install -r modules/enterprise_knowledge/requirements.txt

# .env does not carry into worktrees — copy it from the main workspace (LLM keys)
cp ../../.env .env

# AUTH_MODE=none uses user id 0; a fresh DB has no such row (500s otherwise). Once per DB:
docker exec atria-v2-db-1 psql -U atria -d atria -c \
  "INSERT INTO users (id, is_deleted, email, role, failed_login_attempts, is_active, email_verified, display_name) \
   VALUES (0, false, 'local@localhost', 'admin', 0, true, true, 'Local') ON CONFLICT (id) DO NOTHING"

# Seed the demo world: 6 manual documents + 5 historical work logs (idempotent)
uv run python modules/garage_copilot/scripts/seed_demo.py
```

Start the server:

```bash
set -a; . ./.env; set +a
export DATABASE_URL="postgresql://atria:atria@localhost:5433/atria" \
       ATRIA_REDIS_URL="redis://localhost:6379/0" AUTH_MODE="none" PYTHONPATH="$PWD"
.venv/bin/python -c "from atria.serve import main; main()" --host 127.0.0.1 --port 8081
```

Open **http://localhost:8081**. Stop later with `pkill -f "from atria.serve import main"`.

### What the seed created

Manual corpus (`sample_manuals/`, 6 docs): road-test procedure (WSM-RR-1005), driveline
vibration diagnosis (WSM-RR-2040), CV axle inspection/replacement with torques and part numbers
(WSM-RR-2041), wheel balancing and its limits (WSM-RR-2010), the Ghost II 55–70 km/h TSB
(TSB-RR-2026-03), and Urus battery-drain diagnosis (WSM-LAM-3020).

Workshop history (5 past work logs, searchable):

- `seed-0101` · Rolls-Royce · vibration ~60 km/h → **inner CV joint** (wheel balance tried and
  rejected first — the classic misdiagnosis, on record)
- `seed-0102` · Rolls-Royce · steering shake **only when braking** → disc thickness variation
- `seed-0103` · Lamborghini Urus · battery dead after days parked → aftermarket dashcam drain
- `seed-0104` · McLaren · clicking on full lock → outer CV joint, split boot
- `seed-0105` · Rolls-Royce · floor drone above 80 km/h → propshaft centre bearing

---

## 2. The cast

Play **Nguyễn Văn A**, a technician (KTV) at the S&S Automotive HCMC workshop. A customer's
Ghost II just arrived:

- Repair Order: **RO-2026-0201** (Service Advisor already opened it in SAP — no RO, no work)
- VIN: **SCATV03C9PU207777** · Brand: **Rolls-Royce**
- Customer's words, verbatim: *"Xe chạy khoảng 60km/h thì rung."*

Replies **stream token by token** and the copilot narrates before slow lookups ("Để em tra
WSM…"), so text appears within ~3 s; a full turn with manual retrieval finishes in roughly
10–40 s. The citations that come back are the payoff. Each reply shows its own numbers in a
small footer (`⚡ first token 2.8s · total 14s`) — time from your message to the first visible
answer token, and to the finished turn.

---

## 3. Use case 1 — the star scenario (10 minutes)

### 3.1 The RO gate

In the left sidebar, under the **New chat** button, click the amber **Garage repair session**
button (wrench icon). A dialog opens: "Anchored to a Repair Order — no RO, no repair session."

Try to start it **leaving RO number empty**.

> **Expected:** the "Start repair session" button stays disabled — "RO number, VIN and brand are
> required." Same rule the workshop enforces for tools and diagnostic laptops. (The server
> enforces it too: a raw API call without `ro_number` gets HTTP 422.)

Now fill it in: RO `RO-2026-0201`, VIN `SCATV03C9PU207777`, brand `Rolls-Royce`, technician
`Nguyen Van A`. Start the session — the conversation is named after the RO.

### 3.2 Talk like the customer talked

Type exactly what the customer said — no translation, no cleanup:

```text
Khách bảo "Xe chạy khoảng 60km/h thì rung". Xe Ghost II. Em nên bắt đầu từ đâu?
```

> **Expected:** the copilot answers in Vietnamese, cites the road-test procedure
> (badge like `[WSM-RR-1005#1]`), and asks for the discriminating observations — speed band,
> felt where, and the load/coast behaviour — instead of guessing. Point at the citation badges:
> *every procedural claim is traceable to the manual.*

### 3.3 Report the road test

```text
Em road test rồi: rung mạnh nhất 60-65 km/h khi đạp nhẹ ga, coast về N thì gần hết rung,
cảm nhận ở sàn xe không phải vô lăng. Vậy là gì?
```

> **Expected:** it identifies the load-sensitive signature → **inner CV joint (tripod)**, cites
> the diagnosis stage `[WSM-RR-2040#2]` and the known-issue bulletin `[TSB-RR-2026-03]`, and
> tells you wheel balancing would NOT fix this. The narration moment: *"the advisor wrote
> 'steering vibration', a technician would have balanced the wheels — the copilot just skipped
> that dead end using the workshop's own manual."*

### 3.4 Inspect and close the job

```text
Kiểm tra theo hướng dẫn: tripod housing bên trái có độ rơ hướng kính rõ, boot vẫn nguyên,
bên phải ổn. Em thay CV axle trái, road test lại hết rung. Loại trừ cân bằng bánh xe từ đầu.
Chốt ca giúp em.
```

> **Expected:** it confirms the diagnosis, gives replacement torques and the part number from
> `[WSM-RR-2041]`, and reminds about single-use bolts. Note how the technician "closing out
> loud" (what was ruled out, what fixed it) is exactly what makes the work log good.

### 3.5 The conversation becomes the work log

Grab the session id from the URL (or `curl -s localhost:8081/api/sessions | head`), then:

```bash
SID=<session-id>
curl -s -X POST localhost:8081/api/garage/worklogs/$SID/generate | python3 -m json.tool
curl -s localhost:8081/api/garage/worklogs/$SID | python3 -m json.tool
```

> **Expected (~10 s):** a structured record — the symptom **verbatim as the customer said it**,
> hypotheses **including the rejected one**, diagnostic steps with citations, root cause, fix,
> part numbers. Nobody typed a report; documentation became a byproduct of doing the work.

---

## 4. Use case 2 — the flywheel (the wow moment, 3 minutes)

Two weeks later, a *different* Ghost arrives with the same complaint. New session:
RO `RO-2026-0230`, VIN `SCATV03C9PU208888`, Rolls-Royce. First message:

```text
Xe Ghost khác cũng rung rung tầm 60 cây số giờ. Xưởng mình gặp ca nào giống vậy chưa?
```

> **Expected:** the copilot searches past work logs (`work_log_search`) and comes back with the
> history — your own session from ten minutes ago AND `seed-0101` from April: same symptom,
> same root cause, wheel-balance dead end already on record. The diagnosis that took the
> workshop hours the first time now takes one question. **This is the knowledge-loss bottleneck
> reversed** — when a senior technician leaves, this history stays.

Show the same power from the manager's side (no chat needed):

```bash
# Paraphrase search — different words, still found
curl -s "localhost:8081/api/garage/worklogs/search?q=vibration+around+60+kph+body+shudder&k=3" | python3 -m json.tool

# This vehicle's history only
curl -s "localhost:8081/api/garage/worklogs/search?q=rung&vin=SCATV03C9PU204411" | python3 -m json.tool

# Everything we've seen on Lamborghinis
curl -s "localhost:8081/api/garage/worklogs/search?q=battery+dies+after+parking&brand=Lamborghini" | python3 -m json.tool
```

Note the first query is **English** finding **Vietnamese** records — retrieval is
paraphrase- and language-tolerant.

---

## 5. Use case 3 — trust boundaries (2 minutes)

**Unverified suggestions are visibly labeled.** Ask something the manuals don't cover:

```text
Khách hỏi có nên độ lại hệ thống xả cho tiếng to hơn không?
```

> **Expected:** no fake citations. Anything not grounded in the corpus arrives in an amber
> callout starting `⚠ Gợi ý chưa kiểm chứng` — manual content and model opinion can never be
> confused. (A hallucinated torque spec on a Rolls-Royce is a very expensive mistake.)

**Different vehicle mid-session?** Ask about another car in the same session:

```text
Tiện thể xem giúp em con Urus ngoài bãi bị hết bình luôn nhé.
```

> **Expected:** the copilot declines — this session is anchored to one RO and one VIN; the Urus
> needs its own RO and session. Same "no RO, no work" discipline the workshop already runs, now
> enforced by the tool.

---

## 6. Cheat sheet

- Chat UI: `http://localhost:8081` · server log: check the terminal you launched from
- Generate log: `POST /api/garage/worklogs/{session_id}/generate` (add `?incomplete=true` for an
  abandoned session)
- Read log: `GET /api/garage/worklogs/{session_id}` · Search: `GET /api/garage/worklogs/search?q=&vin=&brand=&k=`
- Manual corpus CLI: `uv run python modules/garage_copilot/scripts/garage.py query "..." --synthesize`
- Work-log CLI: `uv run python modules/garage_copilot/scripts/worklog.py search "..."`
- Re-seed anytime: `uv run python modules/garage_copilot/scripts/seed_demo.py` (idempotent)
- Work-log JSON files: `modules/garage_copilot/data/worklogs/` (or `$ATRIA_DIR/garage/worklogs`)

Troubleshooting:

- **Reply mentions the knowledge service is down** → check Qdrant (`curl localhost:6333/collections`)
  and your LLM key in `.env`. The copilot reports outages instead of answering uncited — by design.
- **Session create 500s** → the `users` id-0 row is missing (see setup).
- **Search returns nothing** → re-run the seeder; confirm collections `garage_chunks` and
  `garage_worklogs` exist in Qdrant.
- Full turns take ~10–40 s (retrieval + multi-step reasoning), with first text at ~3 s. Every
  reply's footer shows its measured `first token` / `total` times, and the server log prints
  matching `TTFT ...ms` / `total_ms` lines per turn.
- Rarely, an answer may briefly appear, vanish, and re-stream — that's the agent's own quality
  check (completion nudge) replacing a draft with its final answer. Harmless.
