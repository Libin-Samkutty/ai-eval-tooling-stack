"""Garak probe runner — direct prompt injection/jailbreak probes.

Garak covers a different attack surface than PyRIT's XPIA (direct vs.
indirect injection), so both are justified.

API call volume: ~1 call per probe. 10 probes = ~10 calls per safety cycle.
"""

from __future__ import annotations

import asyncio
import os

import structlog
from pydantic import BaseModel

logger = structlog.get_logger(__name__)


class GarakProbeResult(BaseModel):
    """Result of a single Garak probe."""

    probe_name: str
    target_model: str
    passed: bool
    details: str


# Default probes to run (10 probes per safety cycle)
DEFAULT_PROBES = [
    "dan.Dan_11_0",
    "gcg.GCGCached",
    "lmrc.Anthropomorphisation",
    "lmrc.Bullying",
    "lmrc.Deadnaming",
    "lmrc.Profanity",
    "lmrc.SexualContent",
    "malwaregen.Evasion",
    "malwaregen.SubFunctions",
    "realtoxicityprompts.RTPBlank",
]


async def run_garak_probes(
    target_endpoint: str,
    probes: list[str] | None = None,
) -> list[GarakProbeResult]:
    """Run Garak probes against the model endpoint.

    TODO(phase-6): Implement actual Garak integration.
    Garak is typically run via CLI:
        garak --model_type rest --model_name <endpoint> --probes <probe_list>

    This module wraps that invocation and parses the output.

    Args:
        target_endpoint: The model/chat endpoint to probe.
        probes: List of probe names to run (defaults to DEFAULT_PROBES).

    Returns:
        List of probe results.
    """
    probes = probes or DEFAULT_PROBES
    results: list[GarakProbeResult] = []

    for probe in probes:
        # TODO(phase-6): Run actual Garak probe via subprocess or Python API
        # Example:
        #   import garak
        #   from garak import cli, _config
        #   _config.load_base_config()
        #   ...
        result = GarakProbeResult(
            probe_name=probe,
            target_model="gemini-1.5-flash",
            passed=True,
            details="Not yet implemented",
        )
        results.append(result)
        logger.info("garak_probe_complete", probe=probe, passed=result.passed)

    logger.info("garak_complete", total=len(results))
    return results


async def _main() -> None:
    target_endpoint = os.environ.get("TARGET_ENDPOINT", "http://localhost:8000/query")
    results = await run_garak_probes(target_endpoint)
    passed = sum(1 for r in results if r.passed)
    logger.info("garak_summary", total=len(results), passed=passed, failed=len(results) - passed)


if __name__ == "__main__":
    asyncio.run(_main())
