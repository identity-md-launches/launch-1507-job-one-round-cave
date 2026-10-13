#!/usr/bin/env python3
"""Make a reproducible receipt for a validated ERC-20 Transfer log window."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
MAX_CAPTURE_BYTES = 16 * 1024 * 1024
LIMITATION = ("This receipt fingerprints one provider capture after local validation; "
              "it does not prove completeness, finality, provider honesty, or a balance.")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


crosscheck = load_module("line4_transfer_crosscheck",
                         HERE.parent / "transfer-crosscheck" / "crosscheck.py")


reader = load_module(
    "line4_bounded_reader_for_receipt",
    HERE.parent / "bounded-capture-reader" / "reader.py",
)
no_duplicate_object = reader.no_duplicate_object


def read_capture(path):
    """Read strict JSON from one bounded, regular workspace file."""
    return reader.read_capture(path, max_bytes=MAX_CAPTURE_BYTES)


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("ascii")


def sha256(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def receipt(capture):
    """Revalidate raw logs, then create a semantic, order-independent receipt."""
    checked = crosscheck.checked(capture)
    identity = {
        "chain_id": checked["chain_id"],
        "token_address": checked["token_address"],
        "from_block": checked["from_block"],
        "to_block": checked["to_block"],
        "decimals": checked["decimals"],
        "from_block_anchor": checked["from_block_anchor"],
        "to_block_anchor": checked["to_block_anchor"],
        "transfers": checked["transfers"],
    }
    return {
        "schema_version": 1,
        "kind": "erc20-transfer-window-receipt",
        "read_only": True,
        "token": capture["token"],
        "token_address": identity["token_address"],
        "from_block": identity["from_block"],
        "to_block": identity["to_block"],
        "from_block_anchor": identity["from_block_anchor"],
        "to_block_anchor": identity["to_block_anchor"],
        "transfer_count": len(identity["transfers"]),
        "window_sha256": sha256(identity),
        "capture_sha256": sha256(capture),
        "limitations": LIMITATION,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--capture", metavar="PATH", help="validated JSON from transfer_window.py")
    group.add_argument("--demo", action="store_true", help="receipt for retained real ZTO evidence")
    args = parser.parse_args(argv)
    if args.demo:
        capture = read_capture(HERE.parent / "transfer-crosscheck" / "publicnode.json")
    else:
        capture = read_capture(args.capture)
    print(json.dumps(receipt(capture), indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, crosscheck.window.RpcError) as exc:
        raise SystemExit("transfer-window-receipt: " + str(exc))
