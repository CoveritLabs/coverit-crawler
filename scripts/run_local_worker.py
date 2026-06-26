from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def read_env(path: Path) -> dict[str, str]:
    return {key: value for key, value in dotenv_values(path).items() if value is not None}


def require(env: dict[str, str], key: str) -> str:
    value = env.get(key)
    if not value:
        raise RuntimeError(f"{key} is not configured")
    return value


def describe_url(name: str, value: str) -> str:
    parsed = urlparse(value)
    return f"{name} scheme={parsed.scheme} host={parsed.hostname} port={parsed.port or ''}"


def main() -> int:
    env = {
        **read_env(ROOT / ".env"),
        **os.environ,
    }

    postgres_host_port = require(env, "POSTGRES_HOST_PORT")

    env["DATABASE_URL"] = require(env, "DATABASE_URL").replace(
        "@db:5432",
        f"@127.0.0.1:{postgres_host_port}",
    )
    env["REDIS_URL"] = require(env, "REDIS_URL").replace(
        "redis://redis:",
        "redis://127.0.0.1:",
    )
    env["COVERIT_API_INTERNAL_URL"] = require(env, "COVERIT_API_INTERNAL_URL")
    env["NEO4J_URI"] = env.get("NEO4J_URI") or env.get("NEO4J_URL") or "bolt://localhost:7687"
    env["NEO4J_USER"] = env.get("NEO4J_USER") or env.get("NEO4J_USERNAME") or "neo4j"

    print(describe_url("DATABASE_URL", env["DATABASE_URL"]), flush=True)
    print(describe_url("REDIS_URL", env["REDIS_URL"]), flush=True)
    print(describe_url("NEO4J_URI", require(env, "NEO4J_URI")), flush=True)
    print(describe_url("COVERIT_API_INTERNAL_URL", env["COVERIT_API_INTERNAL_URL"]), flush=True)

    python = ROOT / ".venv" / "Scripts" / "python.exe"
    if not python.exists():
        python = Path(sys.executable)

    print("Starting CRAWLER worker...", flush=True)
    crawler_process = subprocess.Popen(
        [str(python), "-m", "arq", "src.workers.main.WorkerSettings"],
        cwd=ROOT,
        env=env,
    )

    print("Starting MANUAL worker...", flush=True)
    manual_process = subprocess.Popen(
        [str(python), "-m", "arq", "src.workers.main_manual.ManualWorkerSettings"],
        cwd=ROOT,
        env=env,
    )

    print("Starting FLOWS worker...", flush=True)
    flows_process = subprocess.Popen(
        [str(python), "-m", "arq", "src.workers.main_flows.FlowsWorkerSettings"],
        cwd=ROOT,
        env=env,
    )

    try:
        crawler_process.wait()
        manual_process.wait()
        flows_process.wait()
    except KeyboardInterrupt:
        print("\nShutting down workers...", flush=True)
        crawler_process.terminate()
        manual_process.terminate()
        flows_process.terminate()
        crawler_process.wait()
        manual_process.wait()
        flows_process.wait()
        print("All workers shut down cleanly.", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
