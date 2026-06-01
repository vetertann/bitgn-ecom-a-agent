import os

from dotenv import dotenv_values, find_dotenv, load_dotenv


ENV_FILE = find_dotenv(filename=".env", usecwd=True)
if ENV_FILE:
    # Load the workspace `.env`, but allow explicit shell overrides for ad-hoc runs.
    load_dotenv(ENV_FILE, override=False)
    ENV_VALUES = dotenv_values(ENV_FILE)
else:
    ENV_VALUES = {}


def _env(name: str) -> str:
    env_value = os.getenv(name)
    if env_value:
        return env_value
    value = ENV_VALUES.get(name)
    if value:
        return value
    return ""


BITGN_URL = _env("BENCHMARK_HOST") or "https://api.bitgn.com"
BENCHMARK_ID = _env("BENCHMARK_ID") or _env("BENCH_ID") or "bitgn/ecom1-dev"
BITGN_API_KEY = _env("BITGN_API_KEY")
MODEL_ID = _env("MODEL_ID") or "Qwen/Qwen3.5-397B-A17B-fast"
MODEL_PROVIDER = _env("MODEL_PROVIDER") or "openai"

OPENAI_BASE_URL = _env("OPENAI_BASE_URL") or "https://api.openai.com/v1"
OPENAI_API_KEY = _env("OPENAI_API_KEY")

NEBIUS_BASE_URL = (
    _env("NEBIUS_BASE_URL")
    or "https://api.tokenfactory.us-central1.nebius.com/v1/"
)
NEBIUS_API_KEY = _env("NEBIUS_API_KEY")

ANTHROPIC_BASE_URL = _env("ANTHROPIC_BASE_URL") or "https://api.anthropic.com"
ANTHROPIC_API_KEY = _env("ANTHROPIC_API_KEY")

OPENROUTER_BASE_URL = _env("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1"
OPENROUTER_API_KEY = _env("OPENROUTER_API_KEY")

DEEPSEEK_BASE_URL = _env("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"
DEEPSEEK_API_KEY = _env("DEEPSEEK_API_KEY")

CEREBRAS_BASE_URL = _env("CEREBRAS_BASE_URL") or "https://api.cerebras.ai"
CEREBRAS_API_KEY = _env("CEREBRAS_API_KEY")
