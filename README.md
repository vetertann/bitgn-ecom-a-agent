# A-Agent

A small, agnostic CodeAct agent for the BitGN Enterprise OS benchmarks.

> **1st place** on the [BitGN Agentic E-Commerce Challenge](https://bitgn.com/l/ecom1-accuracy) blind accuracy leaderboard — **81.3 / 100** with OpenAI GPT-5.5, **68.1 / 100** with Qwen3.5-397B-A17B (via Nebius).

## The challenge

BitGN's E-commerce challenge, featuring COLIBRIX ONE as lead partner, is a benchmark for **agentic commerce** — a simulated commercial environment where AI agents handle the full customer journey instead of stopping at product search.

Agents work across product discovery, cart and checkout, payment failures, fraud boundaries, merchant operations, delivery issues, returns, and customer support. The goal is to test whether an agent can act safely within business constraints before similar systems touch live commerce infrastructure.

## The agent

The agent core is ~1.2K lines: 869 in `agent.py`, a 260-line workspace facade, a 50-line config, a **28-line** `verify`, plus two hot-swappable markdown skills. CodeAct itself isn't new — what's interesting is the design discipline that produced this version of it.

Two agnosticisms, both deliberate, both bounded:

- **Model-agnostic.** The same agent runs across six providers (Anthropic, OpenAI, Nebius, OpenRouter, DeepSeek, Cerebras) through one loop. Tool calling supports both native function calling and a `prompt_json` mode (the model returns a `{thought, code}` JSON object as plain text, no provider-side schema validator). The system prompt was trained under `prompt_json` so it has to do its own work — native is a shipping convenience, not a crutch.
- **Domain-agnostic *within an Enterprise OS shell*.** The system prompt assumes the BitGN-style runtime — `AGENTS.MD` as canonical authority, `/proc/*` records, `/docs/*` policies, `/bin/*` runtime exec — but nothing more specific. Anything PAC1- or ECOM-shaped lives in a `SKILL` file, not the prompt.

The receipts: the same system prompt scored **75/104** on PAC1 with no domain skill, **104/104** with a 50-line `pac1.md`, then **11/12** on ECOM dev with no skill — zero edits to the system prompt between benchmarks. The leaderboard gap (GPT-5.5: 81.3 vs Qwen3.5: 68.1) is itself the Bitter Lesson signal — same agent, monotonic improvement with model strength, no prompt overfit to either side.

## Architecture

```mermaid
flowchart TB
    SP["<b>System prompt</b><br/><i>benchmark- and<br/>model-agnostic</i>"]
    SK["<b>SKILL</b><br/><i>ecom.md<br/>domain</i>"]
    PS["<b>PRESUBMIT_SKILL</b><br/><i>presubmit.md<br/>refs polish</i>"]

    MODEL["<b>Model</b> · 6 providers<br/>prompt_json or native<br/>schema-repair × 3"]

    REPL["<b>Persistent in-process Python REPL</b><br/><br/>preloaded globals:<br/><b>ws</b> · <b>scratchpad</b> (gates · draft · refs)<br/><b>submit</b> · <b>verify_scratchpad</b> · <b>anomaly_clusters</b><br/>bare aliases · user vars survive across turns"]

    VM[("<b>BitGN VM · gRPC</b><br/>/proc/* records · /docs/* policies · AGENTS.MD<br/>/bin/sql · /bin/jq · /bin/checkout · /bin/refund · ...")]

    SP --> MODEL
    SK --> MODEL
    PS --> MODEL
    MODEL <==>|"per-turn loop<br/>{thought, code} ↓  observation ↑<br/>≤ 50 turns · target 2–3"| REPL
    REPL <-->|"ws facade"| VM
```

More diagrams (per-turn sequence, fixed-vs-swappable view) in [`res/architecture.md`](res/architecture.md).

## How it works

One tool, one model, one Python REPL that persists across turns. The prompt has three layers:

- **System prompt** — agent behavior, gates, outcome ontology. Enterprise-OS-shaped, otherwise generic.
- **`SKILL`** — domain knowledge (e.g. `ecom.md`). Hot-loaded from `Skills/`.
- **`PRESUBMIT_SKILL`** — accuracy checklist, shown only when a draft is staged.

`main.py` walks `StartTrialRequest` over the benchmark's trial list and hands each `(harness_url, instruction)` to `run_agent(...)`. Before turn 1 a prelude is injected: `tree /`, `tree /docs`, root `AGENTS.MD`, `/bin/date`, `/bin/id`, a checklist, the task text. The model never has to discover the room.

Each turn:

1. Model returns `{thought, code}` — as a JSON object in plain text under `prompt_json`, or via a provider's native function-calling API.
2. The executor runs `code` in a persistent globals dict. Preloaded: `ws`, `scratchpad`, `submit`, `verify`, bare aliases `read / write / search / find / delete / stat / exec / tree / ls`, and the domain primitive `anomaly_clusters`. Importable: `json`, `math`, `re`, `datetime`. Everything else raises with a typed hint.
3. Observation returns as `STDOUT + SCRATCHPAD + optional ERROR`.
4. The task ends when `submit(answer, outcome, refs)` finalizes. Hard ceiling: 50 turns.

The prompt targets 2–3 calls per task: read pass, then decide+write+submit. In-process state makes that economical — a 10k-row TSV read once costs zero tokens to revisit on turn 3.

## Training methodology

The system prompt was developed under one rule: a change shipped only if **a stronger model already did better than a weaker one on the bare prompt** — *before* any domain skill was layered in. The Bitter Lesson used as a regression test. If a smaller model gained while a bigger model stayed flat or regressed, the change was overfit: it was compensating for the weaker model's gaps rather than improving structure. The check has to happen pre-skill, because once a domain file is layered on, the prompt-vs-skill contributions entangle and the signal disappears.

Trajectory on PAC1:

- System prompt only, Qwen iteration model: **75/104**.
- Same prompt, stronger model: **higher**. Confirms the prompt is doing structural work (gates, two-phase submit, `prompt_json` channel, error→hint coaching) rather than papering over Qwen's gaps.
- Add a 50-line `pac1.md` skill (separate file): **104/104**.

At that point the system prompt was "done." No further edits to it.

Transfer test: same system prompt, no domain skill, ECOM dev cut → **11/12** on the first run. The structural backbone carried benchmark-to-benchmark unchanged. From that point on, only the `SKILL` and `PRESUBMIT_SKILL` files were trained per benchmark — `ecom.md` for domain instincts, `presubmit.md` for `refs` discipline.

The leaderboard scores (Qwen 68.1 → GPT-5.5 81.3 on the same agent) are the same regression check measured on the blind set: monotonic with model strength, gap consistent with the prompt doing structural work the model amplifies.

## Acting, refusing, escalating

Task text is untrusted. Authority is canonical files only. The rule shows up structurally, not as a maxim.

Mutations require an evaluated gate in `scratchpad["gates"]` — `identity`, `trust`, `rule-conflict`, `pre-write scope`, `pre-delete scope`. Each gate is a procedure ("name the file that authorizes this move"), not a feeling. `submit(...)` calls `verify_scratchpad` and rejects `OUTCOME_OK` if any gate is `"NO"`.

Outcomes: `OK`, `NONE_CLARIFICATION` (legitimate but underspecified), `NONE_UNSUPPORTED` (no mechanism), `DENIED_SECURITY` (no canonical authority for the requested move), `ERR_INTERNAL`.

The **two-phase staged submit** is the answer-side analogue of gates. When `PRESUBMIT_SKILL` is set, the first `submit(...)` stages a draft and surfaces a focused checklist as the next observation. The model has a full Python turn during the review — it can verify a ref with `read(...)`, recompute an aggregate with `/bin/sql`, mutate `scratchpad["gates"]` if it missed one, then either confirm with an identical `submit(...)` or revise. The runtime, not the model, decides when `ws.answer(...)` actually fires.

## Layout

```
agent.py            869 LOC — loop, provider router, executor, system prompt
workspace.py        260 LOC — gRPC facade over the VM
cluster_tools.py    319 LOC — anomaly_clusters domain primitive
main.py             196 LOC — benchmark runner (start_run / trials / traces)
config.py            50 LOC — env loading + provider URLs
verify.py            28 LOC — scratchpad precondition
Skills/
  ecom.md                  — domain skill (hot-loaded via SKILL=)
  presubmit.md             — refs-discipline checklist (PRESUBMIT_SKILL=)
res/
  architecture.md          — diagrams
```

## How to run

```bash
cp .env.example .env
# fill in BITGN_API_KEY and at least one provider key
uv sync
uv run python main.py
```

Filter to specific tasks by passing task ids as positional args:

```bash
uv run python main.py task-id-1 task-id-2
```

### Configuration via environment variables

`config.py` reads `.env` at import. Anything in the shell environment wins over `.env` for ad-hoc overrides.

**Required**

| Variable | Purpose |
|---|---|
| `BITGN_API_KEY` | BitGN harness API key |
| `<PROVIDER>_API_KEY` | At least one of `OPENAI_API_KEY`, `NEBIUS_API_KEY`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `DEEPSEEK_API_KEY`, `CEREBRAS_API_KEY` |

**Benchmark and model**

| Variable | Default | Purpose |
|---|---|---|
| `BENCHMARK_HOST` | `https://api.bitgn.com` | BitGN harness URL |
| `BENCHMARK_ID` | `bitgn/ecom1-dev` | Benchmark to run (`BENCH_ID` also accepted) |
| `MODEL_ID` | `Qwen/Qwen3.5-397B-A17B-fast` | Model name as the provider expects it |
| `MODEL_PROVIDER` | `openai` | One of `openai`, `nebius`, `anthropic`, `openrouter`, `deepseek`, `cerebras` |
| `MODEL_TOOL_MODE` | `native` | `native` (provider function calling) or `prompt_json` (JSON-in-text channel) |

**Skills (hot-loaded markdown under `Skills/`)**

| Variable | Purpose |
|---|---|
| `SKILL` | File name appended to the system prompt as a domain skill (e.g. `ecom.md`) |
| `PRESUBMIT_SKILL` | File name shown as a checklist on first `submit(...)`; enables the two-phase staged submit |

**Runtime tuning (optional)**

| Variable | Default | Purpose |
|---|---|---|
| `MODEL_TIMEOUT_SECONDS` | `120` | API client timeout |
| `MODEL_MAX_OUTPUT_TOKENS` | `4096` | Per-turn token budget |
| `MODEL_MAX_ATTEMPTS` | `4` | API retries on 5xx / timeouts |
| `MODEL_SCHEMA_MAX_RETRIES` | `3` | Per-turn retries on malformed tool call |
| `MODEL_RETRY_BASE_SECONDS` | `2` | Backoff base for API retries |
| `MODEL_RETRY_503_SECONDS` | `10` | Fixed wait on HTTP 503 |
| `MODEL_RETRY_TOOL_CALL_SECONDS` | `1` | Wait between schema-repair retries |
| `DEEPSEEK_THINKING` | `enabled` | Toggle DeepSeek extended thinking |

**Provider base URLs (override if you proxy or self-host)**

`OPENAI_BASE_URL`, `NEBIUS_BASE_URL`, `ANTHROPIC_BASE_URL`, `OPENROUTER_BASE_URL`, `DEEPSEEK_BASE_URL`, `CEREBRAS_BASE_URL`.

### Recipes

Run the agent vanilla (no domain skill, no presubmit) on Qwen via Nebius:

```bash
MODEL_PROVIDER=nebius MODEL_ID=Qwen/Qwen3.5-397B-A17B-fast \
uv run python main.py
```

Run with the ECOM skill and the presubmit pass on GPT-5.5:

```bash
MODEL_PROVIDER=openai MODEL_ID=gpt-5.5 \
SKILL=ecom.md PRESUBMIT_SKILL=presubmit.md \
uv run python main.py
```

Run on Claude with native tool calling:

```bash
MODEL_PROVIDER=anthropic MODEL_ID=claude-opus-4-5 \
MODEL_TOOL_MODE=native \
SKILL=ecom.md PRESUBMIT_SKILL=presubmit.md \
uv run python main.py
```

Run the training-discipline mode (prompt_json forced, no presubmit, single skill) — what the system prompt was iterated against:

```bash
MODEL_TOOL_MODE=prompt_json SKILL=ecom.md \
MODEL_PROVIDER=nebius MODEL_ID=Qwen/Qwen3.5-397B-A17B-fast \
uv run python main.py
```

## What might be next

- Drop the 50-turn ceiling; add real context management for long stateful tasks.
- Cap presubmit revisions explicitly — currently unbounded except by the outer 50-turn loop.
- Make gates *call-site* preconditions — wrap `ws.write` / `ws.delete` so a missing gate raises in-runtime, not only at submit.
- Auto-promote lessons into `Skills/` after a failed-then-fixed task.
- A cheaper second model running the presubmit pass in parallel, surfacing objections.
- More domain primitives in the `anomaly_clusters` mold.

## License

MIT.
