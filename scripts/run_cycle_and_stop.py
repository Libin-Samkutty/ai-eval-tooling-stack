#!/usr/bin/env python3
"""Run an eval cycle on a Codespace and stop it the moment the cycle ends.

Run this from your LOCAL machine, not inside the Codespace — it uses `gh`
(authenticated with the `codespace` scope) to SSH in, block until the cycle's
Jobs finish, and then stop the Codespace regardless of whether the cycle
succeeded or failed. This exists because a Codespace bills for wall-clock
time it's running, independent of whether anything inside it is doing work,
and it will happily stay up (and billing) after a cycle finishes if nobody
stops it.

Usage:
    python scripts/run_cycle_and_stop.py quality [--codespace NAME]
    python scripts/run_cycle_and_stop.py safety [--codespace NAME]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

import structlog

logger = structlog.get_logger(__name__)

CYCLE_TARGETS = {
    "quality": "eval-quality-wait",
    "safety": "eval-safety-wait",
}


def resolve_codespace_name(explicit: str | None) -> str:
    if explicit:
        return explicit

    result = subprocess.run(
        ["gh", "codespace", "list", "--json", "name"],
        capture_output=True,
        text=True,
        check=True,
    )
    codespaces = json.loads(result.stdout)
    if len(codespaces) != 1:
        raise SystemExit(
            f"Expected exactly one codespace, found {len(codespaces)}. "
            "Pass --codespace NAME explicitly."
        )
    return codespaces[0]["name"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cycle", choices=sorted(CYCLE_TARGETS))
    parser.add_argument(
        "--codespace", default=None, help="Codespace name (auto-detected if omitted)"
    )
    args = parser.parse_args()

    name = resolve_codespace_name(args.codespace)
    make_target = CYCLE_TARGETS[args.cycle]

    logger.info("cycle_start", cycle=args.cycle, codespace=name)
    remote_command = (
        f"cd /workspaces/ai-eval-tooling-stack && make {make_target}"
    )
    run_result = subprocess.run(
        ["gh", "codespace", "ssh", "-c", name, "--", remote_command],
    )
    if run_result.returncode == 0:
        logger.info("cycle_complete", cycle=args.cycle, codespace=name)
    else:
        logger.error(
            "cycle_failed", cycle=args.cycle, codespace=name, exit_code=run_result.returncode
        )

    logger.info("codespace_stopping", codespace=name)
    stop_result = subprocess.run(["gh", "codespace", "stop", "-c", name])
    if stop_result.returncode != 0:
        logger.error("codespace_stop_failed", codespace=name, exit_code=stop_result.returncode)
        sys.exit(stop_result.returncode)

    logger.info("codespace_stopped", codespace=name)
    sys.exit(run_result.returncode)


if __name__ == "__main__":
    main()
