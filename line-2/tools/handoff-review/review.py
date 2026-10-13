#!/usr/bin/env python3
"""Review one immutable HANDOFF v1 snapshot using the inherited offline checks."""
import argparse
import io
import json
import struct
import sys
import zipfile
from pathlib import Path
import importlib.util


def load(name, relative):
    current = Path.cwd()
    for part in Path(relative).parts:
        current /= part
        if current.is_symlink():
            raise ValueError("dependency symlinks are not allowed")
    spec = importlib.util.spec_from_file_location(name, current)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


REPRODUCE = load("handoff_review_reproduce", "line-2/tools/handoff-reproduce/reproduce.py")
PORTABILITY = load("handoff_review_portability", "line-2/tools/handoff-portability/portability.py")
SOURCE = load("handoff_review_source", "line-2/tools/handoff-source/source_check.py")
CONTENT = load("handoff_review_content", "line-2/tools/handoff-content/content.py")
LANDING = load("handoff_review_landing", "line-2/tools/handoff-landing/landing.py")
INSPECT = REPRODUCE.INSPECT
WRITER = REPRODUCE.WRITER


def review_bytes(data, source=None, expected=None, limits=None, expectation_data=None,
                 destination=None):
    """Refuse invalid bytes; retain every diagnostic for valid differing archives.

    Source scans compare against this same snapshot's receipt. No archive path
    is reopened by a companion and no packaged code is imported or executed.
    """
    limits = limits or INSPECT.Limits()
    limits.validate()
    if destination is not None:
        LANDING.destination_parts(destination)
    if not isinstance(data, (bytes, bytearray)):
        raise ValueError("archive snapshot must be bytes")
    if len(data) > limits.archive_bytes:
        raise ValueError("archive exceeds size limit")
    # Reject malformed expectations before archive inspection or source scans.
    # Freeze caller-owned buffers so all checks describe the same captured bytes.
    if expectation_data is not None:
        CONTENT.parse_expectation(expectation_data)
        expectation_data = bytes(expectation_data)
    data = bytes(data)
    receipt = INSPECT.inspect_stream(io.BytesIO(data), limits, expected)
    content_result = (None if expectation_data is None else
                      CONTENT.compare(receipt, expectation_data))
    reproduction = REPRODUCE.check_bytes(data, expected, limits)
    issues = PORTABILITY.analyze([item["path"] for item in receipt["files"]])
    source_result = None
    if source is not None:
        files = SOURCE.source_receipt(source, INSPECT, limits)
        source_result = SOURCE.compare(receipt, files)
    landing_result = (None if destination is None else
                      LANDING.plan_receipt(receipt, destination))
    failed = []
    if not reproduction["byte_reproducible"]:
        failed.append("reproduction")
    if issues:
        failed.append("portability")
    if source_result is not None and not source_result["matches_source"]:
        failed.append("source")
    if content_result is not None and not content_result["content_passed"]:
        failed.append("content")
    if landing_result is not None and not landing_result["ready"]:
        failed.append("landing")
    return {
        "format": "handoff-review-v1",
        "selected_checks_passed": not failed,
        "failed_checks": failed,
        "archive_sha256": receipt["archive_sha256"],
        "archive_bytes": receipt["archive_bytes"],
        "file_count": receipt["file_count"],
        "payload_bytes": receipt["payload_bytes"],
        "trusted_digest_matched": receipt["trusted_digest_matched"],
        "limits": receipt["limits"],
        "checks": {
            "integrity": {"status": "pass"},
            "reproduction": {"status": "pass" if reproduction["byte_reproducible"] else "difference",
                             "receipt": reproduction},
            "portability": {"status": "difference" if issues else "pass",
                            "profile": PORTABILITY.PROFILE, "issues": issues},
            "source": {"status": "not-requested" if source_result is None else
                       ("pass" if source_result["matches_source"] else "difference"),
                       "directory": source, "receipt": source_result},
            "content": {"status": "not-requested" if content_result is None else
                        ("pass" if content_result["content_passed"] else "difference"),
                        "receipt": content_result},
            "landing": {"status": "not-requested" if landing_result is None else
                        ("pass" if landing_result["ready"] else "difference"),
                        "receipt": landing_result},
        },
        "note": "Selected format checks only: no sender authentication, payload safety "
                "assessment, build reproduction or extraction test. Source scans require "
                "a stable workspace and are not atomic snapshots. Content expectations "
                "must be independently trusted to identify the intended revision. Landing "
                "is a bounded, read-only metadata check at one instant, not a reservation; "
                "no destination files are read or written.",
    }


def review_path(archive, source=None, expected=None, limits=None, expectation=None,
                destination=None):
    limits = limits or INSPECT.Limits()
    limits.validate()
    if destination is not None:
        LANDING.destination_parts(destination)
    expectation_data = None
    if expectation is not None:
        expectation_data = CONTENT.read_expectation(expectation)
        CONTENT.parse_expectation(expectation_data)
    # Read once, with a hard budget and no intentional symlink following.
    data = WRITER.regular_bytes(WRITER.workspace_path(archive), limits.archive_bytes)
    return review_bytes(data, source, expected, limits, expectation_data, destination)


def demo():
    result = review_path("line-2/handoff.zip", "line-2/tools/handoff",
                        expectation="line-2/tools/handoff-content/inherited-content.json",
                        destination="line-2/tools/handoff-review/unpacked-demo")
    if not result["selected_checks_passed"]:
        raise ValueError("the inherited handoff failed its selected checks")
    result["demo"] = "actual inherited archive and source; no files written"
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("demo")
    check = commands.add_parser("check")
    check.add_argument("archive", help="relative workspace HANDOFF v1 ZIP")
    check.add_argument("--source", help="optional relative workspace source directory")
    check.add_argument("--expectation", help="separately retained content-expectation JSON")
    check.add_argument("--destination", help="optional workspace-relative landing directory; read only")
    check.add_argument("--sha256", help="independently obtained archive SHA-256")
    check.add_argument("--max-archive-bytes", type=INSPECT.positive, default=INSPECT.Limits.archive_bytes)
    check.add_argument("--max-payload-bytes", type=INSPECT.positive, default=INSPECT.Limits.payload_bytes)
    check.add_argument("--max-files", type=INSPECT.positive, default=INSPECT.Limits.files)
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            result = demo()
        else:
            limits = INSPECT.Limits(archive_bytes=args.max_archive_bytes,
                                    payload_bytes=args.max_payload_bytes, files=args.max_files)
            result = review_path(args.archive, args.source, args.sha256, limits,
                                 args.expectation, args.destination)
        print(json.dumps(result, sort_keys=True, indent=2, ensure_ascii=True))
        return 0 if result["selected_checks_passed"] else 2
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError,
            zipfile.BadZipFile, EOFError, NotImplementedError, struct.error) as error:
        print("handoff-review: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
