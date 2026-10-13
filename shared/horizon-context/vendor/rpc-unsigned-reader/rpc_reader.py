#!/usr/bin/env python3
"""Inspect complete unsigned type-2 JSON-RPC transaction objects offline."""
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "erc20-intent"))
import intent

D = intent.decoder
MAX_JSON_CHARS = 512 * 1024
QUANTITIES = ("chainId", "nonce", "maxPriorityFeePerGas", "maxFeePerGas", "gas", "value")
REQUIRED = frozenset((*QUANTITIES, "type", "to", "accessList"))
ALLOWED = REQUIRED | {"data", "input"}


def reject_number(_):
    raise ValueError("JSON numbers are not accepted; use canonical 0x quantities")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def quantity(value, name):
    if (not isinstance(value, str) or len(value) > 66
            or re.fullmatch(r"0x(?:0|[1-9a-fA-F][0-9a-fA-F]*)", value) is None):
        raise ValueError(f"{name} must be a canonical 0x quantity of at most 256 bits")
    return int(value[2:], 16)


def hex_bytes(value, name, size=None):
    if (not isinstance(value, str) or len(value) > 2 * D.MAX_TRANSACTION_BYTES + 2
            or re.fullmatch(r"0x(?:[0-9a-fA-F]{2})*", value) is None):
        raise ValueError(f"{name} must be bounded, even-length 0x data")
    if size is not None and len(value) != 2 + 2 * size:
        raise ValueError(f"{name} must contain exactly {size} bytes")
    return bytes.fromhex(value[2:])


def inspect_json(text):
    """Accept JSON text, reject ambiguity, and reuse the unsigned RLP reader.

    No defaults or RPC discovery: all nine unsigned fields must be supplied.
    No input files, environment, network, wallet, keys, signing or sending.
    """
    if not isinstance(text, str) or len(text) > MAX_JSON_CHARS:
        raise ValueError("input must be JSON text within 512 Ki characters")
    try:
        obj = json.loads(text, object_pairs_hook=unique_object,
                         parse_int=reject_number, parse_float=reject_number,
                         parse_constant=reject_number)
    except (json.JSONDecodeError, RecursionError) as error:
        raise ValueError("malformed or excessively nested JSON") from error
    if not isinstance(obj, dict):
        raise ValueError("expected one unsigned transaction object")
    if set(obj) - ALLOWED:
        raise ValueError("unsupported fields; signatures, sender, RPC wrappers and metadata are not accepted")
    missing = REQUIRED - set(obj)
    if missing:
        raise ValueError("missing required fields: " + ", ".join(sorted(missing)))
    if ("data" in obj) == ("input" in obj):
        raise ValueError("supply exactly one of data or input, including for empty calldata")
    if quantity(obj["type"], "type") != 2:
        raise ValueError("only unsigned EIP-1559 type 0x2 is supported")
    numbers = {name: quantity(obj[name], name) for name in QUANTITIES}
    to = b"" if obj["to"] is None else hex_bytes(obj["to"], "to", 20)
    data_field = "data" if "data" in obj else "input"
    data = hex_bytes(obj[data_field], data_field)
    access = obj["accessList"]
    if not isinstance(access, list):
        raise ValueError("accessList must be an array")
    # Root + nine fields, then three containers/scalars per entry and its slots.
    item_count = 10
    entries = []
    for entry in access:
        if not isinstance(entry, dict) or set(entry) != {"address", "storageKeys"}:
            raise ValueError("access-list entry must contain only address and storageKeys")
        slots = entry["storageKeys"]
        if not isinstance(slots, list):
            raise ValueError("storageKeys must be an array")
        item_count += 3 + len(slots)
        if item_count > D.MAX_RLP_ITEMS:
            raise ValueError("access list exceeds inherited RLP item limit")
        entries.append([hex_bytes(entry["address"], "access-list address", 20),
                        [hex_bytes(slot, "storage key", 32) for slot in slots]])
    fields = [numbers["chainId"], numbers["nonce"], numbers["maxPriorityFeePerGas"],
              numbers["maxFeePerGas"], numbers["gas"], to, numbers["value"], data, entries]
    raw = b"\x02" + D.rlp_encode(fields)
    if len(raw) > D.MAX_TRANSACTION_BYTES:
        raise ValueError("normalized unsigned envelope exceeds the 128 KiB limit")
    return {"schema": "rpc-unsigned-reader/v1", "inputFormat": "unsigned-json-rpc-object",
            "calldataSourceField": data_field,
            "inspection": intent.interpret(raw.hex()),
            "normalization": "gas maps to gasLimit; input/data maps to data; null to means contract creation. "
                             "No fields defaulted; access-list order and duplicates retained."}


def demo_object():
    """Re-express the inherited synthetic ZTO totalSupply inspection sample."""
    tx = D.decode(D.demo_transaction())
    result = {name: hex(tx["gasLimit" if name == "gas" else name]) for name in QUANTITIES}
    result.update(type="0x2", to=tx["to"], data=tx["data"], accessList=tx["accessList"])
    return result


def main(arguments):
    try:
        if arguments == ["--demo"]:
            text = json.dumps(demo_object())
        elif arguments == ["--stdin"]:
            text = sys.stdin.read(MAX_JSON_CHARS + 1)
        elif len(arguments) == 1 and not arguments[0].startswith("--"):
            text = arguments[0]
        else:
            print("usage: rpc_reader.py --demo | --stdin | 'JSON_OBJECT'", file=sys.stderr)
            return 2
        report = inspect_json(text)
    except (ValueError, UnicodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
