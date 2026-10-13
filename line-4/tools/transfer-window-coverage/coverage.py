#!/usr/bin/env python3
"""Summarize block coverage in a validated bounded ERC-20 log capture."""

import argparse
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
MAX_CAPTURE_BYTES = 16 * 1024 * 1024
LIMITATION = (
    "Coverage describes one validated provider window; empty blocks do not prove "
    "complete history or finality, and totals are not a token balance."
)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


crosscheck = load_module(
    "line4_transfer_crosscheck_for_coverage",
    HERE.parent / "transfer-crosscheck" / "crosscheck.py",
)


reader = load_module(
    "line4_bounded_reader_for_coverage",
    HERE.parent / "bounded-capture-reader" / "reader.py",
)
no_duplicate_object = reader.no_duplicate_object


def read_capture(path):
    """Read strict JSON from one bounded, regular workspace file."""
    return reader.read_capture(path, max_bytes=MAX_CAPTURE_BYTES)


def coverage(capture):
    """Revalidate raw evidence and aggregate its canonical transfers by block."""
    checked = crosscheck.checked(capture)
    start, end = checked["from_block"], checked["to_block"]
    decimals = checked["decimals"]
    by_block = {}
    for event in checked["transfers"]:
        block = event["block"]
        item = by_block.setdefault(block, {
            "block": block,
            "log_indices": [],
            "raw_value_total": 0,
            "senders": set(),
            "receivers": set(),
        })
        item["log_indices"].append(event["log_index"])
        item["raw_value_total"] += int(event["raw_value"])
        item["senders"].add(event["from"])
        item["receivers"].add(event["to"])

    blocks = []
    for block in sorted(by_block):
        item = by_block[block]
        raw_total = item["raw_value_total"]
        blocks.append({
            "block": block,
            "transfer_count": len(item["log_indices"]),
            "log_indices": sorted(item["log_indices"]),
            "raw_value_total": str(raw_total),
            "value_total": crosscheck.window.display_units(raw_total, decimals),
            "sender_count": len(item["senders"]),
            "receiver_count": len(item["receivers"]),
        })

    block_count = end - start + 1
    populated = len(blocks)
    return {
        "schema_version": 1,
        "kind": "erc20-transfer-window-coverage",
        "read_only": True,
        "validated": True,
        "token": capture["token"],
        "token_address": checked["token_address"],
        "decimals": decimals,
        "from_block": start,
        "to_block": end,
        "block_count": block_count,
        "transfer_count": len(checked["transfers"]),
        "populated_block_count": populated,
        "empty_block_count": block_count - populated,
        "populated_blocks": blocks,
        "limitations": LIMITATION,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--capture", metavar="PATH", help="validated JSON from transfer_window.py")
    group.add_argument("--demo", action="store_true", help="summarize retained real ZTO evidence")
    args = parser.parse_args(argv)
    if args.demo:
        capture = read_capture(HERE.parent / "transfer-crosscheck" / "publicnode.json")
    else:
        capture = read_capture(args.capture)
    print(json.dumps(coverage(capture), indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, crosscheck.window.RpcError) as exc:
        raise SystemExit("transfer-window-coverage: " + str(exc))
