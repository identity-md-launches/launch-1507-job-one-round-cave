#!/usr/bin/env python3
"""Decode an unsigned EIP-1559 Ethereum transaction without network access."""
import json
import sys

MAX_TRANSACTION_BYTES = 128 * 1024
MAX_RLP_DEPTH = 16
MAX_RLP_ITEMS = 16384

ZTO = "0xd782bdea4ef02a0bd391eb9089470c8080f0a68e"


def rlp_item(data, position=0):
    """Parse one canonical RLP item with bounded nesting, items and input bytes.

    Each child is restricted to its parent's payload: a child may never consume
    bytes belonging to a following sibling or outside the enclosing list.
    """
    if not isinstance(data, bytes) or len(data) > MAX_TRANSACTION_BYTES:
        raise ValueError("RLP input must be bytes within the 128 KiB limit")
    if not isinstance(position, int) or position < 0:
        raise ValueError("invalid RLP position")
    budget = [MAX_RLP_ITEMS]

    def parse(cursor, limit, depth):
        if depth > MAX_RLP_DEPTH:
            raise ValueError("RLP nesting exceeds depth limit")
        budget[0] -= 1
        if budget[0] < 0:
            raise ValueError("RLP item count exceeds limit")
        if cursor >= limit:
            raise ValueError("truncated RLP item")
        first = data[cursor]
        if first < 0x80:
            return data[cursor:cursor + 1], cursor + 1
        is_list = first >= 0xc0
        short_base = 0xc0 if is_list else 0x80
        long_base = 0xf7 if is_list else 0xb7
        start = cursor + 1
        if first <= long_base:
            size = first - short_base
        else:
            length_size = first - long_base
            length_end = start + length_size
            if length_end > limit or data[start] == 0:
                raise ValueError("non-canonical or truncated RLP length")
            size = int.from_bytes(data[start:length_end], "big")
            if size < 56:
                raise ValueError("non-canonical long RLP length")
            start = length_end
        end = start + size
        if end > limit:
            raise ValueError("truncated RLP payload")
        if not is_list:
            if size == 1 and data[start] < 0x80:
                raise ValueError("non-canonical RLP string")
            return data[start:end], end
        values = []
        cursor = start
        while cursor < end:
            value, cursor = parse(cursor, end, depth + 1)
            values.append(value)
        return values, end

    return parse(position, len(data), 0)


def integer(value, name):
    if not isinstance(value, bytes) or (value and value[0] == 0):
        raise ValueError(f"invalid {name}")
    return int.from_bytes(value, "big")


def rlp_encode(value):
    if isinstance(value, int):
        value = b"" if value == 0 else value.to_bytes((value.bit_length() + 7) // 8, "big")
    if isinstance(value, list):
        payload = b"".join(rlp_encode(item) for item in value)
        offset = 0xc0
    else:
        if not isinstance(value, bytes):
            raise TypeError("RLP values must be integers, byte strings, or lists")
        if len(value) == 1 and value[0] < 0x80:
            return value
        payload = value
        offset = 0x80
    if len(payload) < 56:
        return bytes([offset + len(payload)]) + payload
    length = len(payload).to_bytes((len(payload).bit_length() + 7) // 8, "big")
    return bytes([offset + 55 + len(length)]) + length + payload


def access_list(value):
    if not isinstance(value, list):
        raise ValueError("accessList must be an RLP list")
    decoded = []
    for entry in value:
        if not isinstance(entry, list) or len(entry) != 2 or not isinstance(entry[0], bytes) or len(entry[0]) != 20:
            raise ValueError("invalid access-list address")
        if not isinstance(entry[1], list) or any(not isinstance(slot, bytes) or len(slot) != 32 for slot in entry[1]):
            raise ValueError("invalid access-list storage key")
        decoded.append({"address": "0x" + entry[0].hex(), "storageKeys": ["0x" + slot.hex() for slot in entry[1]]})
    return decoded


def decode(transaction_hex):
    if not isinstance(transaction_hex, str):
        raise ValueError("transaction must be hexadecimal text")
    if len(transaction_hex) > 2 * MAX_TRANSACTION_BYTES + 2:
        raise ValueError("transaction exceeds the 128 KiB limit")
    if transaction_hex.startswith("0x"):
        transaction_hex = transaction_hex[2:]
    if len(transaction_hex) % 2 or not transaction_hex:
        raise ValueError("transaction must be non-empty, even-length hexadecimal")
    if any(character not in "0123456789abcdefABCDEF" for character in transaction_hex):
        raise ValueError("transaction is not hexadecimal (whitespace is not allowed)")
    try:
        raw = bytes.fromhex(transaction_hex)
    except ValueError as error:
        raise ValueError("transaction is not hexadecimal") from error
    if len(raw) > MAX_TRANSACTION_BYTES:
        raise ValueError("transaction exceeds the 128 KiB limit")
    if raw[0] != 2:
        raise ValueError("only EIP-1559 typed transactions (0x02) are supported")
    fields, end = rlp_item(raw, 1)
    if end != len(raw) or not isinstance(fields, list) or len(fields) != 9:
        raise ValueError("an unsigned EIP-1559 transaction must contain exactly nine fields")
    names = ("chainId", "nonce", "maxPriorityFeePerGas", "maxFeePerGas", "gasLimit", "to", "value", "data", "accessList")
    result = {"type": "EIP-1559", "typeByte": "0x02"}
    for index, name in enumerate(names):
        field = fields[index]
        if name == "to":
            if not isinstance(field, bytes) or len(field) not in (0, 20):
                raise ValueError("to must be empty or a 20-byte address")
            result[name] = None if not field else "0x" + field.hex()
        elif name == "data":
            if not isinstance(field, bytes):
                raise ValueError("data must be bytes")
            result[name] = "0x" + field.hex()
        elif name == "accessList":
            result[name] = access_list(field)
        else:
            result[name] = integer(field, name)
    result["calldataSelector"] = result["data"][:10] if len(result["data"]) >= 10 else None
    return result


def demo_transaction():
    """An unsigned, non-payable call to ZTO's real contract: totalSupply()."""
    payload = [1, 0, 1_000_000_000, 2_000_000_000, 100_000, bytes.fromhex(ZTO[2:]), 0, bytes.fromhex("18160ddd"), []]
    return "0x02" + rlp_encode(payload).hex()


def main(arguments):
    if arguments == ["--demo"]:
        print(json.dumps(decode(demo_transaction()), indent=2, sort_keys=True))
        return
    if len(arguments) != 1:
        raise SystemExit("usage: tx_decode.py --demo | 0x02...")
    print(json.dumps(decode(arguments[0]), indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2) from None
