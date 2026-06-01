import json
import os
import re
import textwrap
from datetime import datetime, timezone
from pathlib import Path

from bitgn.harness_connect import HarnessServiceClientSync
from bitgn.harness_pb2 import EndTrialRequest, SubmitRunRequest, EvalPolicy, StartTrialRequest, GetTrialRequest, GetBenchmarkRequest, StartPlaygroundRequest, StatusRequest, StartRunRequest
from connectrpc.errors import ConnectError

from agent import run_agent
from config import BENCHMARK_ID, BITGN_API_KEY, BITGN_URL, MODEL_ID


CLI_RED = "\x1B[31m"
CLI_GREEN = "\x1B[32m"
CLI_CLR = "\x1B[0m"
CLI_BLUE = "\x1B[34m"
TRACE_DIR = Path(__file__).resolve().parent / "run_logs"
TRACE_INDEX = TRACE_DIR / "index.json"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stamp_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-") or "unknown"


def _read_index() -> list[dict]:
    if not TRACE_INDEX.exists():
        return []
    try:
        return json.loads(TRACE_INDEX.read_text())
    except json.JSONDecodeError:
        return []


def _write_trial_trace(
    *,
    benchmark_id: str,
    bitgn_run_id: str,
    model: str,
    task_id: str,
    trial_id: str,
    instruction: str,
    started_at: str,
    finished_at: str,
    steps: list[dict],
    score: float | None,
    score_detail: list[str],
    agent_error: str | None,
) -> None:
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{_stamp_now()}__{_slug(task_id)}__{_slug(trial_id)}.json"
    trace_path = TRACE_DIR / filename
    usage_totals: dict[str, int] = {}
    for step in steps:
        usage = step.get("usage") or {}
        for key, value in usage.items():
            if isinstance(value, int):
                usage_totals[key] = usage_totals.get(key, 0) + value
    payload = {
        "trace_version": 1,
        "benchmark_id": benchmark_id,
        "bitgn_run_id": bitgn_run_id,
        "model": model,
        "task_id": task_id,
        "trial_id": trial_id,
        "instruction": instruction,
        "started_at": started_at,
        "finished_at": finished_at,
        "step_count": len(steps),
        "steps": steps,
        "usage_totals": usage_totals,
        "score": score,
        "score_detail": score_detail,
        "agent_error": agent_error,
    }
    trace_path.write_text(json.dumps(payload, indent=2))

    summary = {
        "file": filename,
        "task_id": task_id,
        "trial_id": trial_id,
        "bitgn_run_id": bitgn_run_id,
        "benchmark_id": benchmark_id,
        "model": model,
        "step_count": len(steps),
        "usage_totals": usage_totals,
        "score": score,
        "agent_error": agent_error,
        "started_at": started_at,
        "finished_at": finished_at,
    }
    items = [summary]
    for item in _read_index():
        if item.get("file") != filename:
            items.append(item)
    TRACE_INDEX.write_text(json.dumps(items, indent=2))


def main() -> None:
    task_filter = os.sys.argv[1:]

    scores = []
    try:
        client = HarnessServiceClientSync(BITGN_URL)

        print("Connecting to BitGN", client.status(StatusRequest()))
        res = client.get_benchmark(GetBenchmarkRequest(benchmark_id=BENCHMARK_ID))
        print(
            f"{EvalPolicy.Name(res.policy)} benchmark: {res.benchmark_id} "
            f"with {len(res.tasks)} tasks.\n{CLI_GREEN}{res.description}{CLI_CLR}"
        )

        run = client.start_run(StartRunRequest(
            name=f"A-Agent ECOM {MODEL_ID}",
            benchmark_id=BENCHMARK_ID,
            api_key=BITGN_API_KEY))

        try:

            for trial_id in run.trial_ids:
                trial = client.start_trial(
                    StartTrialRequest(trial_id=trial_id),
                )

                if task_filter and trial.task_id not in task_filter:
                    continue

                print(f"{'=' * 30} Starting task: {trial.task_id} {'=' * 30}")

                print(f"{CLI_BLUE}{trial.instruction}{CLI_CLR}\n{'-' * 80}")

                trace_started = _iso_now()
                step_records: list[dict] = []
                agent_error: str | None = None
                try:
                    run_agent(
                        MODEL_ID,
                        trial.harness_url,
                        trial.instruction,
                        on_step=step_records.append,
                    )
                except Exception as exc:
                    agent_error = str(exc)
                    print(exc)

                result = client.end_trial(EndTrialRequest(trial_id=trial.trial_id))
                trace_finished = _iso_now()
                _write_trial_trace(
                    benchmark_id=BENCHMARK_ID,
                    bitgn_run_id=run.run_id,
                    model=MODEL_ID,
                    task_id=trial.task_id,
                    trial_id=trial.trial_id,
                    instruction=trial.instruction,
                    started_at=trace_started,
                    finished_at=trace_finished,
                    steps=step_records,
                    score=float(result.score) if result.score >= 0 else None,
                    score_detail=list(result.score_detail),
                    agent_error=agent_error,
                )
                if result.score >= 0:
                    scores.append((trial.task_id, result.score))
                    style = CLI_GREEN if result.score == 1 else CLI_RED
                    explain = textwrap.indent("\n".join(result.score_detail), "  ")
                    print(f"\n{style}Score: {result.score:0.2f}\n{explain}\n{CLI_CLR}")

        finally:
            client.submit_run(SubmitRunRequest(run_id=run.run_id, force=True))

    except ConnectError as exc:
        print(f"{exc.code}: {exc.message}")
    except KeyboardInterrupt:
        print(f"{CLI_RED}Interrupted{CLI_CLR}")

    if scores:
        for task_id, score in scores:
            style = CLI_GREEN if score == 1 else CLI_RED
            print(f"{task_id}: {style}{score:0.2f}{CLI_CLR}")

        total = sum(score for _, score in scores) / len(scores) * 100.0
        print(f"FINAL: {total:0.2f}%")


if __name__ == "__main__":
    main()
