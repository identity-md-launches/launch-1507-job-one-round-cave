#!/usr/bin/env python3
"""Read bounded, strict JSON captures through workspace-only regular files."""
import argparse
import importlib.util
import json
import math
import os
from pathlib import Path
import stat

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MAX_BYTES = 16 * 1024 * 1024


def no_duplicate_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON object has a duplicate key: " + key)
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError("non-finite JSON number: " + value)


def finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("non-finite JSON number")
    return number


def check_nesting(raw):
    """Bound JSON nesting before decoding; ignore delimiters inside strings."""
    depth = 0
    quoted = escaped = False
    for byte in raw:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte in (91, 123):
            depth += 1
            if depth > 64:
                raise ValueError("JSON nesting exceeds 64 levels")
        elif byte in (93, 125):
            depth -= 1


def read_capture(path, max_bytes=MAX_BYTES):
    """Read at most limit+1 bytes; reject links in every relative component.

    Directory descriptors and O_NOFOLLOW avoid a check/open symlink race.
    O_NONBLOCK lets us refuse FIFOs without waiting for a writer. This is a
    POSIX reader; unsupported platforms fail closed before opening input.
    The workspace root is the trusted installation root, not a CLI option.
    """
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_BYTES:
        raise ValueError("byte limit must be an integer in 1..16777216")
    if not all(hasattr(os, flag) for flag in ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK")):
        raise ValueError("workspace reader requires POSIX no-follow file support")
    path = Path(path)
    # Do not resolve caller-controlled components (that would follow links).
    if not path.is_absolute():
        path = Path.cwd() / path
    try:
        parts = path.relative_to(ROOT).parts
    except ValueError as exc:
        raise ValueError("capture must be inside this workspace") from exc
    if not parts or any(part == ".." for part in parts):
        raise ValueError("capture path must name a workspace file without traversal")
    directory = None
    descriptor = None
    try:
        directory = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=directory)
            os.close(directory)
            directory = child
        descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=directory)
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("capture must be a regular file")
        if info.st_size > max_bytes:
            raise ValueError("capture exceeds byte limit")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            raw = stream.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise ValueError("capture exceeds byte limit")
    except OSError as exc:
        raise ValueError("cannot read workspace capture: " + str(exc)) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if directory is not None:
            os.close(directory)
    try:
        check_nesting(raw)
        return json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicate_object,
                          parse_constant=reject_constant, parse_float=finite_float)
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise ValueError("capture is not strict UTF-8 JSON: " + str(exc)) from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--demo", action="store_true", help="validate retained real ZTO evidence offline")
    source.add_argument("--capture", type=Path, help="public capture file inside this workspace")
    args = parser.parse_args(argv)
    path = HERE.parent / "transfer-crosscheck" / "publicnode.json" if args.demo else args.capture
    capture = read_capture(path)
    spec = importlib.util.spec_from_file_location(
        "crosscheck_for_bounded_reader", HERE.parent / "transfer-crosscheck" / "crosscheck.py")
    crosscheck = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(crosscheck)
    try:
        checked = crosscheck.checked(capture)
    except crosscheck.window.RpcError as exc:
        raise ValueError(str(exc)) from exc
    print(json.dumps({
        "kind": "bounded-transfer-capture-check", "read_only": True,
        "token": capture["token"], "from_block": checked["from_block"],
        "to_block": checked["to_block"], "transfer_count": len(checked["transfers"]),
        "max_capture_bytes": MAX_BYTES, "raw_logs_revalidated": True,
        "limitations": "Local validation of retained provider evidence; not a fresh chain read, completeness or finality proof."
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except ValueError as exc:
        raise SystemExit("bounded-capture-reader: " + str(exc))
