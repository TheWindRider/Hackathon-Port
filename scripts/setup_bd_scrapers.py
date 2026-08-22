#!/usr/bin/env python3
"""Set up Bright Data Scraper Studio collectors for Kalshi and Polymarket.

This script is idempotent — if collector IDs are already set in .env, it skips
creation for that platform and just verifies the collector is reachable.

Usage:
    uv run python scripts/setup_bd_scrapers.py

Requirements:
    - Node.js v22+ with @brightdata/cli installed and authenticated
      (run: npx @brightdata/cli@latest login)
    - BRIGHTDATA_API_KEY set in .env

After running this script the following vars will be set in .env:
    BRIGHTDATA_KALSHI_COLLECTOR_ID
    BRIGHTDATA_POLYMARKET_COLLECTOR_ID
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parents[1]
_ENV_FILE = _REPO_ROOT / ".env"

_SCRAPERS = [
    {
        "env_key": "BRIGHTDATA_KALSHI_COLLECTOR_ID",
        "name": "kalshi-browse",
        "url": "https://kalshi.com/browse",
        "description": (
            "Extract the top 30 prediction market listings. For each market card extract: "
            "market title, yes price (probability as a decimal 0-1), no price, "
            "24h volume in dollars, category/tag, and the market URL."
        ),
    },
    {
        "env_key": "BRIGHTDATA_POLYMARKET_COLLECTOR_ID",
        "name": "polymarket-browse",
        "url": "https://polymarket.com/markets",
        "description": (
            "Extract the top 30 prediction market listings. For each market card extract: "
            "market title, yes price (probability as a decimal 0-1), no price, "
            "24h volume in dollars, category/tag, and the market URL."
        ),
    },
]


def _load_env() -> dict[str, str]:
    """Load key=value pairs from .env file."""
    env: dict[str, str] = {}
    if not _ENV_FILE.exists():
        return env
    for line in _ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


def _set_env_var(key: str, value: str) -> None:
    """Write or update a key in .env."""
    content = _ENV_FILE.read_text() if _ENV_FILE.exists() else ""
    pattern = re.compile(rf"^({re.escape(key)}=).*$", re.MULTILINE)
    if pattern.search(content):
        content = pattern.sub(rf"\g<1>{value}", content)
    else:
        if content and not content.endswith("\n"):
            content += "\n"
        content += f"{key}={value}\n"
    _ENV_FILE.write_text(content)
    print(f"  → Written to .env: {key}={value}")


def _find_bdata() -> str:
    """Locate the bdata CLI binary."""
    # Try direct path first (when Node 22 is active)
    for candidate in ["bdata", "npx @brightdata/cli@latest"]:
        try:
            result = subprocess.run(
                candidate.split() + ["--version"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode == 0:
                return candidate
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    # Try via nvm
    nvm_script = Path.home() / ".nvm" / "nvm.sh"
    if nvm_script.exists():
        probe = subprocess.run(
            ["bash", "-c", f"source {nvm_script} && bdata --version"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if probe.returncode == 0:
            return f"bash -c 'source {nvm_script} && bdata'"

    raise RuntimeError(
        "bdata CLI not found. Install it with: npm install -g @brightdata/cli\n"
        "Then authenticate: bdata login"
    )


def _run_bdata(bdata_cmd: str, args: list[str], timeout: int = 660) -> dict:
    """Run a bdata CLI command and return parsed JSON output."""
    if bdata_cmd.startswith("bash -c"):
        # Inject args into the bash -c string
        inner = bdata_cmd.split("'")[1]
        cmd = ["bash", "-c", f"source ~/.nvm/nvm.sh && {inner.strip()} {' '.join(args)} --json"]
    else:
        cmd = bdata_cmd.split() + args + ["--json"]

    print(f"  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    if result.returncode != 0:
        raise RuntimeError(
            f"bdata command failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    # Extract JSON from output (the CLI may print progress lines before the JSON)
    raw = result.stdout.strip()
    # Find last JSON object/array
    for line in reversed(raw.splitlines()):
        line = line.strip()
        if line.startswith("{") or line.startswith("["):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                pass

    # Try parsing the whole output
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError(f"Could not parse bdata JSON output:\n{raw}")


def _verify_collector(api_key: str, collector_id: str) -> bool:
    """Check the collector exists via BD API."""
    try:
        import httpx
        resp = httpx.get(
            f"https://api.brightdata.com/dca/collector?id={collector_id}",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
        return resp.status_code == 200
    except Exception:
        return False


def main() -> None:
    print("=== Bright Data Scraper Studio Setup ===\n")

    # Load current .env
    env = _load_env()
    api_key = env.get("BRIGHTDATA_API_KEY") or os.environ.get("BRIGHTDATA_API_KEY", "")
    if not api_key:
        print("ERROR: BRIGHTDATA_API_KEY not set in .env")
        sys.exit(1)

    try:
        bdata = _find_bdata()
        print(f"Found bdata CLI: {bdata}\n")
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)

    for scraper in _SCRAPERS:
        key = scraper["env_key"]
        platform = key.replace("BRIGHTDATA_", "").replace("_COLLECTOR_ID", "").lower()
        existing = env.get(key) or os.environ.get(key, "")

        print(f"--- {platform.capitalize()} ---")

        if existing:
            print(f"  Collector ID already set: {existing}")
            if _verify_collector(api_key, existing):
                print("  Verification: OK\n")
            else:
                print("  Warning: could not verify collector via API (may still work)\n")
            continue

        print(f"  Creating collector for: {scraper['url']}")
        print("  (AI generation takes 5–10 minutes, please wait...)")

        try:
            result = _run_bdata(
                bdata,
                [
                    "scraper", "create",
                    scraper["url"],
                    scraper["description"],
                    "--name", scraper["name"],
                ],
                timeout=720,
            )
        except RuntimeError as exc:
            print(f"  ERROR creating {platform} collector: {exc}")
            print("  Skipping — you can retry or set the env var manually.\n")
            continue

        collector_id = result.get("collector_id") or result.get("id", "")
        if not collector_id:
            print(f"  ERROR: no collector_id in response: {result}")
            continue

        _set_env_var(key, collector_id)
        print(f"  Status: {result.get('status')}")
        print(f"  View: {result.get('view_url', 'https://brightdata.com/cp/scrapers')}\n")

    print("=== Setup complete ===")
    print("Collector IDs are saved in .env.")
    print("Run 'python main.py' to execute the pipeline.\n")


if __name__ == "__main__":
    main()
