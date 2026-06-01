# A-Agent — architecture diagrams

Two views: a static layout (what the parts are) and a sequence (what happens during a task).

## 1. Architecture

Three prompt layers fan into the model. The model and the REPL talk every turn. The REPL is the only thing that talks to the VM.

```mermaid
flowchart TB
    SP["<b>System prompt</b><br/><i>benchmark- and<br/>model-agnostic</i>"]
    SK["<b>SKILL</b><br/><i>ecom.md<br/>domain</i>"]
    PS["<b>PRESUBMIT_SKILL</b><br/><i>presubmit.md<br/>refs polish</i>"]

    MODEL["<b>Model</b> · 6 providers<br/>prompt_json default · native optional<br/>schema-repair × 3"]

    REPL["<b>Persistent in-process Python REPL</b><br/><br/>preloaded globals:<br/><b>ws</b> · <b>scratchpad</b> (gates · draft · refs)<br/><b>submit</b> · <b>verify_scratchpad</b> · <b>anomaly_clusters</b><br/>bare aliases · user vars survive across turns"]

    VM[("<b>BitGN VM · gRPC</b><br/>/proc/* records · /docs/* policies · AGENTS.MD<br/>/bin/sql · /bin/jq · /bin/checkout · /bin/refund · ...")]

    SP --> MODEL
    SK --> MODEL
    PS --> MODEL
    MODEL <==>|"per-turn loop<br/>{thought, code} ↓  observation ↑<br/>≤ 50 turns · target 2–3"| REPL
    REPL <-->|"ws facade"| VM
```

## 2. Lifecycle

Time goes down. The two coloured blocks separate the normal turn loop from the staged-submit phase.

```mermaid
sequenceDiagram
    autonumber
    participant M as Model
    participant E as REPL
    participant V as VM

    Note over M,V: Turn 0 — Prelude injected: tree /, tree /docs,<br/>AGENTS.MD, /bin/date, /bin/id, checklist, task text

    rect rgb(240, 244, 255)
    Note over M,V: Per turn · ≤ 50 · target 2–3
    M->>E: {thought, code}
    E->>V: ws.read / write / search / exec
    V-->>E: results (+ truncation hint if any)
    E-->>M: STDOUT + scratchpad + (error + typed hint)
    end

    rect rgb(240, 255, 240)
    Note over M,V: Two-phase submit (when PRESUBMIT_SKILL is set)
    M->>E: submit(answer, outcome, refs)
    E->>E: verify_scratchpad → stage scratchpad['draft']
    E-->>M: draft preview + PRESUBMIT_SKILL checklist
    M->>E: submit(...) identical
    E->>V: ws.answer(...)
    V-->>M: trace + score
    end
```

## 3. Seams — fixed vs swappable per benchmark

```mermaid
flowchart LR
    subgraph FIXED["Fixed across benchmarks · the 1.2K-line core"]
        direction TB
        F1["System prompt"]
        F2["Turn loop · schema repair · error → hint"]
        F3["Gates · staged submit · verify"]
        F4["Persistent REPL · provider router"]
    end

    subgraph SWAP["Swapped per benchmark"]
        direction TB
        S1["SKILL.md · domain instincts"]
        S2["PRESUBMIT.md · accuracy polish"]
        S3["Workspace instrument list · /bin/*"]
        S4["Domain primitives · e.g. anomaly_clusters"]
    end

    FIXED ~~~ SWAP
```
