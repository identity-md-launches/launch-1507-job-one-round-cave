#!/usr/bin/env python3
"""Bound an unsigned EIP-1559 fee cap over hypothetical future block usage."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fee-context"))
import fee_context


MAX_BLOCKS = 64


def next_base_fee(parent, full):
    """EIP-1559 step for a full (2x target) or empty (0x target) parent."""
    if type(parent) is not int or not 0 <= parent <= fee_context.UINT256_MAX:
        raise ValueError("parent base fee must be uint256 wei per gas")
    if type(full) is not bool:
        raise ValueError("full must be a boolean")
    return parent + max(parent // 8, 1) if full else parent - parent // 8


def scenario(base, cap, priority, gas):
    covered = base <= cap and priority <= cap
    tip = min(priority, cap - base) if covered else None
    return {
        "baseFeePerGasWei": str(base),
        "feeCapCoversBaseFee": base <= cap,
        "fullPriorityAvailable": tip == priority if covered else None,
        "effectivePriorityFeePerGasWei": str(tip) if covered else None,
        "effectiveGasPriceWei": str(base + tip) if covered else None,
        "feeCeilingAtGasLimitWei": str(gas * (base + tip)) if covered else None,
    }


def inspect(text, parent_base_fee, blocks, input_format="rlp"):
    """Read original unsigned bytes/object and model bounded EIP-1559 extremes.

    Step 1 is the child of the caller's parent block. For the upper path,
    every preceding parent is full; for the lower path, each is empty.
    These are alternative hypothetical paths, not observed blocks.
    """
    if type(blocks) is not int or not 1 <= blocks <= MAX_BLOCKS:
        raise ValueError("blocks must be an integer from 1 through 64")
    # The inherited reader validates bounded original input, chain and uint256
    # fields. It never takes an untrusted decoded summary as input.
    context = fee_context.inspect(text, parent_base_fee, 1, input_format)
    tx = context["inspection"]["transaction"]
    cap = int(tx["maxFeePerGas"])
    priority = int(tx["maxPriorityFeePerGas"])
    gas = int(tx["gasLimit"])
    upper = lower = parent_base_fee
    rows = []
    for step in range(1, blocks + 1):
        upper = next_base_fee(upper, True)
        lower = next_base_fee(lower, False)
        rows.append({
            "futureBlock": step,
            "afterFullParents": scenario(upper, cap, priority, gas),
            "afterEmptyParents": scenario(lower, cap, priority, gas),
            "feeCapGuaranteedAcrossModeledRange": priority <= cap and upper <= cap,
            "feeCapPossibleWithinModeledRange": priority <= cap and lower <= cap,
            "fullPriorityGuaranteedAcrossModeledRange": priority <= cap - upper,
            "fullPriorityPossibleWithinModeledRange": priority <= cap - lower,
        })
    return {
        "schema": "fee-horizon/v1",
        "inputFormat": input_format,
        "model": {
            "name": "EIP-1559 execution base-fee extremes",
            "chainId": "1",
            "parentBaseFeePerGasWei": str(parent_base_fee),
            "parentBaseFeeSource": "Explicit caller assertion; no block or freshness verified.",
            "fullParent": "gas used is exactly twice target; next fee adds max(floor(parent fee / 8), 1)",
            "emptyParent": "gas used is zero; next fee subtracts floor(parent fee / 8)",
            "firstStep": "next child block, based on hypothetical usage of the supplied parent",
        },
        "feeCaps": {"maxFeePerGasWei": str(cap),
                    "maxPriorityFeePerGasWei": str(priority),
                    "feeCeilingAtGasLimitWei": str(gas * cap)},
        "checkedViolations": (["priority-fee-exceeds-max-fee"] if priority > cap else []),
        "rows": rows,
        "inspection": context["inspection"],
        "limits": [
            "Hypothetical EIP-1559 execution-gas arithmetic only; no block was read or forecast.",
            "The upper path uses exactly twice target; an odd gas limit can permit one more unit of gas.",
            "Caller must establish that this model applies at the target block and that the parent fee is authentic.",
            "Fee-cap coverage does not ensure inclusion, balance, nonce, intrinsic gas, execution or safety to sign.",
            "Ceilings multiply gas limit, not actual gas used; ZTO and IMD calls still pay Ethereum gas in ETH.",
        ],
    }


def block_count(text):
    value = fee_context.decimal(text)
    if not 1 <= value <= MAX_BLOCKS:
        raise ValueError("blocks must be an integer from 1 through 64")
    return value


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent-base-fee-wei", required=True)
    parser.add_argument("--blocks", required=True)
    parser.add_argument("--format", choices=("rlp", "json"), default="rlp")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--demo", action="store_true")
    source.add_argument("--transaction")
    source.add_argument("--stdin", action="store_true")
    args = parser.parse_args(argv)
    try:
        base = fee_context.decimal(args.parent_base_fee_wei)
        blocks = block_count(args.blocks)
        if args.demo:
            text = (json.dumps(fee_context.reader.demo_object()) if args.format == "json"
                    else fee_context.reader.D.demo_transaction())
        elif args.stdin:
            text = sys.stdin.read(fee_context.MAX_INPUT_CHARS + 1)
            if len(text) > fee_context.MAX_INPUT_CHARS:
                raise ValueError("transaction text exceeds 512 Ki characters")
            if args.format == "rlp":
                text = text.removesuffix("\n").removesuffix("\r")
        else:
            text = args.transaction
        result = inspect(text, base, blocks, args.format)
    except (ValueError, UnicodeError) as error:
        print("error: " + str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if result["checkedViolations"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
