#!/usr/bin/env python3
"""Describe populated and empty runs inside a validated ERC-20 window."""

import argparse
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
MAX_CAPTURE_BYTES = 16 * 1024 * 1024
LIMITATION = (
    "Activity is a shape summary of one validated provider window; it does not "
    "prove complete history, finality, provider honesty, or a token balance."
)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


crosscheck = load_module(
    "line4_transfer_crosscheck_for_activity",
    HERE.parent / "transfer-crosscheck" / "crosscheck.py",
)


reader = load_module(
    "line4_bounded_reader_for_activity",
    HERE.parent / "bounded-capture-reader" / "reader.py",
)
no_duplicate_object = reader.no_duplicate_object


def read_capture(path):
    """Read strict JSON from one bounded, regular workspace file."""
    return reader.read_capture(path, max_bytes=MAX_CAPTURE_BYTES)


def activity(capture):
    """Revalidate evidence and return contiguous populated/empty block runs."""
    checked = crosscheck.checked(capture)
    start, end = checked["from_block"], checked["to_block"]
    populated = {event["block"] for event in checked["transfers"]}
    runs = []
    run_start = start
    prior = start in populated
    for block in range(start + 1, end + 1):
        state = block in populated
        if state != prior:
            runs.append({
                "state": "populated" if prior else "empty",
                "from_block": run_start,
                "to_block": block - 1,
                "block_count": block - run_start,
            })
            run_start, prior = block, state
    runs.append({
        "state": "populated" if prior else "empty",
        "from_block": run_start,
        "to_block": end,
        "block_count": end - run_start + 1,
    })
    longest_empty = max(
        (run["block_count"] for run in runs if run["state"] == "empty"),
        default=0,
    )
    return {
        "schema_version": 1,
        "kind": "erc20-transfer-window-activity",
        "read_only": True,
        "validated": True,
        "token": capture["token"],
        "token_address": checked["token_address"],
        "from_block": start,
        "to_block": end,
        "block_count": end - start + 1,
        "transfer_count": len(checked["transfers"]),
        "populated_block_count": len(populated),
        "empty_block_count": end - start + 1 - len(populated),
        "longest_empty_run": longest_empty,
        "runs": runs,
        "limitations": LIMITATION,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--capture", metavar="PATH", help="saved transfer-window JSON")
    group.add_argument("--demo", action="store_true", help="use retained real ZTO evidence")
    args = parser.parse_args(argv)
    path = HERE.parent / "transfer-crosscheck" / "publicnode.json" if args.demo else args.capture
    print(json.dumps(activity(read_capture(path)), indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, crosscheck.window.RpcError) as exc:
        raise SystemExit("transfer-window-activity: " + str(exc))
