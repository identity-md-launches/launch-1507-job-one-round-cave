#!/usr/bin/env python3
"""Offline behavioral checks; disposable public fixtures stay in test/scratch."""
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import review as R


def altered(data, comment=b"", corrupt=False):
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(out, "w") as target:
        for item in source.infolist():
            payload = source.read(item.filename)
            if corrupt and item.filename != "HANDOFF.json":
                payload = b"x" * len(payload)
            target.writestr(item, payload)
        target.comment = comment
    return out.getvalue()


class ReviewTests(unittest.TestCase):
    def setUp(self):
        root = Path("test/scratch")
        root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=root)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve().relative_to(Path.cwd())
        self.source = self.root / "source"
        self.source.mkdir()
        self.files = {"README.md": b"public fixture\n", "nested/empty": b""}
        for name, data in self.files.items():
            dest = self.source / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        self.data = R.WRITER.build(self.files)
        self.archive = self.root / "bundle.zip"
        self.archive.write_bytes(self.data)

    def test_real_archive_and_source(self):
        result = R.demo()
        self.assertTrue(result["selected_checks_passed"])
        self.assertEqual(result["file_count"], 2)
        self.assertEqual(result["payload_bytes"], 12603)
        self.assertEqual(result["checks"]["source"]["status"], "pass")
        self.assertEqual(result["checks"]["content"]["status"], "pass")

    def test_without_source_is_explicitly_skipped(self):
        result = R.review_bytes(self.data)
        self.assertTrue(result["selected_checks_passed"])
        self.assertEqual(result["checks"]["source"]["status"], "not-requested")
        self.assertIsNone(result["checks"]["source"]["receipt"])
        self.assertFalse(result["trusted_digest_matched"])
        self.assertEqual(result["checks"]["content"],
                         {"status": "not-requested", "receipt": None})

    def expectation(self, exact=True):
        return json.dumps({"format": R.CONTENT.FORMAT, "exact": exact,
                           "files": [{"path": name, "bytes": len(data),
                                      "sha256": R.WRITER.digest(data)}
                                     for name, data in sorted(self.files.items())]}).encode()

    def test_expected_content_matches_same_digest(self):
        expected = self.expectation()
        result = R.review_bytes(self.data, expectation_data=expected)
        content = result["checks"]["content"]["receipt"]
        self.assertTrue(result["selected_checks_passed"])
        self.assertEqual(content["archive_sha256"], result["archive_sha256"])
        self.assertEqual(content["expectation_sha256"], R.WRITER.digest(expected))
        self.assertEqual(content["matched"], sorted(self.files))

    def test_valid_wrong_revision_fails_content_only(self):
        revised = dict(self.files, **{"README.md": b"another revision\n"})
        result = R.review_bytes(R.WRITER.build(revised), expectation_data=self.expectation())
        self.assertEqual(result["failed_checks"], ["content"])
        self.assertEqual(result["checks"]["integrity"]["status"], "pass")
        self.assertEqual(result["checks"]["reproduction"]["status"], "pass")
        self.assertEqual(result["checks"]["content"]["receipt"]["changed"][0]["path"], "README.md")

    def test_missing_extra_and_subset_content(self):
        revised = dict(self.files)
        del revised["nested/empty"]
        revised["extra.txt"] = b"extra"
        result = R.review_bytes(R.WRITER.build(revised), expectation_data=self.expectation())
        content = result["checks"]["content"]["receipt"]
        self.assertEqual(content["missing"], ["nested/empty"])
        self.assertEqual(content["unexpected"], ["extra.txt"])
        data = R.WRITER.build(dict(self.files, **{"extra.txt": b"extra"}))
        for exact in (True, False):
            result = R.review_bytes(data, expectation_data=self.expectation(exact))
            self.assertEqual(result["selected_checks_passed"], not exact)
            self.assertEqual(result["checks"]["content"]["receipt"]["unexpected"], ["extra.txt"])

    def test_content_differences_do_not_hide_other_diagnostics(self):
        data = altered(R.WRITER.build({"CON.txt": b"public"}), comment=b"different")
        result = R.review_bytes(data, str(self.source), expectation_data=self.expectation())
        self.assertEqual(result["failed_checks"], ["reproduction", "portability", "source", "content"])

    def test_malformed_expectation_prevents_archive_and_source_reads(self):
        expectation = self.root / "expectation.json"
        for data in (b"{}", b'{"exact":true,"exact":false}',
                     b" " * (R.CONTENT.MAX_EXPECTATION + 1)):
            expectation.write_bytes(data)
            with patch.object(R.WRITER, "regular_bytes") as reader, \
                    patch.object(R.SOURCE, "source_receipt") as scanner:
                with self.assertRaises(ValueError):
                    R.review_path(str(self.archive), str(self.source), expectation=str(expectation))
                reader.assert_not_called()
                scanner.assert_not_called()

    def test_content_uses_captured_archive_and_expectation_once(self):
        expectation = self.root / "expectation.json"
        expected = self.expectation()
        expectation.write_bytes(expected)
        original = R.WRITER.regular_bytes
        def replace_after_read(path, limit):
            data = original(path, limit)
            self.archive.write_bytes(R.WRITER.build({"wrong": b"revision"}))
            expectation.write_bytes(b"invalid replacement")
            return data
        with patch.object(R.WRITER, "regular_bytes", side_effect=replace_after_read) as reader, \
                patch.object(R.CONTENT, "read_expectation", wraps=R.CONTENT.read_expectation) as er:
            result = R.review_path(str(self.archive), expectation=str(expectation))
        self.assertEqual(reader.call_count, 1)
        self.assertEqual(er.call_count, 1)
        self.assertTrue(result["selected_checks_passed"])
        self.assertEqual(result["archive_sha256"], R.WRITER.digest(self.data))
        self.assertEqual(result["checks"]["content"]["receipt"]["expectation_sha256"],
                         R.WRITER.digest(expected))

    def test_expectation_paths_stay_in_workspace(self):
        expectation = self.root / "expectation.json"
        expectation.write_bytes(self.expectation())
        link = self.root / "expectation-link.json"
        link.symlink_to("expectation.json")
        for path in (str(link), str(expectation.absolute()), "../expectation.json", str(self.source)):
            with self.assertRaises((ValueError, OSError)):
                R.review_path(str(self.archive), expectation=path)

    def test_content_cli_statuses(self):
        expectation = self.root / "expectation.json"
        expectation.write_bytes(self.expectation())
        command = [sys.executable, "-B", "line-2/tools/handoff-review/review.py", "check",
                   str(self.archive), "--expectation", str(expectation)]
        for data, status in ((self.data, 0), (R.WRITER.build({"other": b"revision"}), 2), (b"bad", 1)):
            self.archive.write_bytes(data)
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, status, result.stderr)
            if status == 1:
                self.assertEqual(result.stdout, "")
            else:
                report = json.loads(result.stdout)
                self.assertEqual(report["checks"]["content"]["status"], "pass" if status == 0 else "difference")
        expectation.write_bytes(b"{}")
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")

    def test_mutable_archive_buffer_is_frozen_between_checks(self):
        data = bytearray(self.data)
        original = R.CONTENT.compare
        def compare_then_mutate(receipt, expectation):
            data[:] = b"bad"
            return original(receipt, expectation)
        with patch.object(R.CONTENT, "compare", side_effect=compare_then_mutate):
            result = R.review_bytes(data, expectation_data=self.expectation())
        self.assertTrue(result["selected_checks_passed"])

    def test_deterministic_report_and_trusted_digest(self):
        a = R.review_bytes(self.data, str(self.source), R.WRITER.digest(self.data))
        b = R.review_bytes(self.data, str(self.source), R.WRITER.digest(self.data))
        self.assertEqual(a, b)
        self.assertTrue(a["trusted_digest_matched"])
        self.assertEqual(a["archive_sha256"], a["checks"]["source"]["receipt"]["archive_sha256"])
        self.assertEqual(a["archive_sha256"], a["checks"]["reproduction"]["receipt"]["archive_sha256"])

    def test_valid_alternate_serialization_is_difference(self):
        result = R.review_bytes(altered(self.data, comment=b"public comment"), str(self.source))
        self.assertEqual(result["failed_checks"], ["reproduction"])
        self.assertEqual(result["checks"]["integrity"]["status"], "pass")
        self.assertEqual(result["checks"]["source"]["status"], "pass")

    def test_portability_hazard_is_difference(self):
        result = R.review_bytes(R.WRITER.build({"CON.txt": b"public"}))
        self.assertEqual(result["failed_checks"], ["portability"])
        self.assertIn("windows-device-name", [i["code"] for i in result["checks"]["portability"]["issues"]])

    def test_source_diagnostics_retained(self):
        (self.source / "README.md").write_bytes(b"changed")
        (self.source / "nested/empty").unlink()
        (self.source / "added.txt").write_bytes(b"new")
        result = R.review_bytes(self.data, str(self.source))
        self.assertEqual(result["failed_checks"], ["source"])
        counts = result["checks"]["source"]["receipt"]["counts"]
        self.assertEqual(counts, {"changed": 1, "missing_from_source": 1,
                                  "omitted_from_archive": 1, "unchanged": 0})

    def test_all_differences_reported_together(self):
        data = altered(R.WRITER.build({"CON.txt": b"public"}), comment=b"different")
        result = R.review_bytes(data, str(self.source))
        self.assertFalse(result["selected_checks_passed"])
        self.assertEqual(result["failed_checks"], ["reproduction", "portability", "source"])

    def test_corruption_prevents_source_scan(self):
        with patch.object(R.SOURCE, "source_receipt") as scanner:
            with self.assertRaisesRegex(ValueError, "integrity mismatch"):
                R.review_bytes(altered(self.data, corrupt=True), str(self.source))
            scanner.assert_not_called()

    def test_trusted_digest_refusals(self):
        for digest in ("f" * 64, "invalid"):
            with self.assertRaises(ValueError):
                R.review_bytes(self.data, expected=digest)

    def test_budgets_and_invalid_archive(self):
        for limits in (R.INSPECT.Limits(archive_bytes=1), R.INSPECT.Limits(payload_bytes=1),
                       R.INSPECT.Limits(files=1)):
            with self.assertRaises(ValueError):
                R.review_path(str(self.archive), limits=limits)
        for data in (b"not a ZIP", self.data[:-1], self.data + b"trailing"):
            with self.assertRaises(ValueError):
                R.review_bytes(data)

    def test_archive_is_read_once(self):
        original = R.WRITER.regular_bytes
        with patch.object(R.WRITER, "regular_bytes", wraps=original) as reader:
            result = R.review_path(str(self.archive), str(self.source))
            self.assertTrue(result["selected_checks_passed"])
            self.assertEqual(reader.call_count, 1)

    def test_landing_skipped_and_fresh_destination_not_created(self):
        result = R.review_bytes(self.data)
        self.assertEqual(result["checks"]["landing"],
                         {"status": "not-requested", "receipt": None})
        destination = self.root / "fresh"
        result = R.review_bytes(self.data, destination=str(destination))
        self.assertTrue(result["selected_checks_passed"])
        self.assertEqual(result["checks"]["landing"]["status"], "pass")
        self.assertFalse(destination.exists())

    def test_occupied_destination_fails_only_landing(self):
        before = {p: p.read_bytes() for p in self.source.rglob("*") if p.is_file()}
        result = R.review_bytes(self.data, str(self.source), destination=str(self.source))
        self.assertEqual(result["failed_checks"], ["landing"])
        self.assertEqual(result["checks"]["source"]["status"], "pass")
        self.assertEqual(result["checks"]["landing"]["status"], "difference")
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_landing_name_alias_and_symlink_diagnostics(self):
        destination = self.root / "Source"
        result = R.review_bytes(self.data, destination=str(destination))
        issues = result["checks"]["landing"]["receipt"]["path_issues"]
        self.assertEqual({i["kind"] for i in issues}, {"existing-name-collision"})
        link = self.root / "linked"
        link.symlink_to("source", target_is_directory=True)
        result = R.review_bytes(self.data, destination=str(link))
        self.assertEqual(result["failed_checks"], ["landing"])
        self.assertEqual({i["kind"] for i in result["checks"]["landing"]["receipt"]["path_issues"]},
                         {"symlink-at-leaf"})

    def test_landing_retains_other_differences(self):
        data = altered(R.WRITER.build({"CON.txt": b"public"}), comment=b"different")
        result = R.review_bytes(data, str(self.source), expectation_data=self.expectation(),
                                destination=str(self.root / "fresh"))
        self.assertEqual(result["failed_checks"],
                         ["reproduction", "portability", "source", "content", "landing"])

    def test_landing_uses_captured_receipt_without_reopening_archive(self):
        original = R.WRITER.regular_bytes
        def replace_after_read(path, limit):
            data = original(path, limit)
            self.archive.write_bytes(b"invalid replacement")
            return data
        with patch.object(R.WRITER, "regular_bytes", side_effect=replace_after_read) as reader, \
                patch.object(R.LANDING, "plan", side_effect=AssertionError("reopened archive")), \
                patch.object(R.LANDING, "plan_receipt", wraps=R.LANDING.plan_receipt) as planner:
            result = R.review_path(str(self.archive), destination=str(self.root / "fresh"))
        self.assertEqual(reader.call_count, 1)
        self.assertEqual(planner.call_count, 1)
        self.assertTrue(result["selected_checks_passed"])
        self.assertEqual(result["archive_sha256"],
                         result["checks"]["landing"]["receipt"]["archive_sha256"])
        self.assertEqual(result["archive_sha256"], R.WRITER.digest(self.data))

    def test_unsafe_destination_refused_before_archive_read(self):
        for destination in ("../outside", "/outside", "", "a/../b", "a\\b"):
            with patch.object(R.WRITER, "regular_bytes") as reader, \
                    patch.object(R.LANDING, "plan_receipt") as planner:
                with self.assertRaises(ValueError):
                    R.review_path(str(self.archive), destination=destination)
                reader.assert_not_called()
                planner.assert_not_called()

    def test_corrupt_archive_prevents_landing_scan(self):
        with patch.object(R.LANDING, "plan_receipt") as planner:
            with self.assertRaises(ValueError):
                R.review_bytes(altered(self.data, corrupt=True),
                               destination=str(self.root / "fresh"))
            planner.assert_not_called()

    def test_landing_scan_limit_refuses_review(self):
        def bounded(receipt, destination):
            return original(receipt, destination, max_names=1, max_directory_names=1)
        original = R.LANDING.plan_receipt
        with patch.object(R.LANDING, "plan_receipt", side_effect=bounded):
            with self.assertRaisesRegex(ValueError, "scan exceeds limit"):
                R.review_bytes(self.data, destination=str(self.root / "fresh"))

    def test_landing_cli_statuses(self):
        command = [sys.executable, "-B", "line-2/tools/handoff-review/review.py", "check",
                   str(self.archive), "--destination"]
        for destination, status in ((str(self.root / "fresh"), 0),
                                    (str(self.source), 2), ("../outside", 1)):
            result = subprocess.run(command + [destination], capture_output=True, text=True)
            self.assertEqual(result.returncode, status, result.stderr)
            if status == 1:
                self.assertEqual(result.stdout, "")
                self.assertIn("handoff-review:", result.stderr)
            else:
                report = json.loads(result.stdout)
                self.assertEqual(report["checks"]["landing"]["status"],
                                 "pass" if status == 0 else "difference")
        self.assertFalse((self.root / "fresh").exists())

    def test_archive_replacement_after_snapshot(self):
        original = R.WRITER.regular_bytes
        def read_then_replace(path, limit):
            data = original(path, limit)
            self.archive.write_bytes(b"invalid replacement")
            return data
        with patch.object(R.WRITER, "regular_bytes", side_effect=read_then_replace):
            result = R.review_path(str(self.archive), str(self.source))
        self.assertTrue(result["selected_checks_passed"])
        self.assertEqual(result["archive_sha256"], R.WRITER.digest(self.data))

    def test_workspace_paths_and_symlinks_refused(self):
        link = self.root / "link.zip"
        link.symlink_to("bundle.zip")
        for name in (str(link), str(self.archive.absolute()), "../outside.zip"):
            with self.assertRaises(ValueError):
                R.review_path(name)
        directory_link = self.root / "source-link"
        directory_link.symlink_to("source", target_is_directory=True)
        for source in (str(directory_link), str(self.source.absolute()), "../outside"):
            with self.assertRaises(ValueError):
                R.review_bytes(self.data, source)

    def test_nonregular_source_is_refused(self):
        (self.source / "link").symlink_to("README.md")
        with self.assertRaises(ValueError):
            R.review_bytes(self.data, str(self.source))

    def test_cli_statuses_and_no_partial_json(self):
        command = [sys.executable, "-B", "line-2/tools/handoff-review/review.py", "check", str(self.archive)]
        for data, status in ((self.data, 0), (altered(self.data, comment=b"x"), 2),
                             (R.WRITER.build({"NUL": b"hazard"}), 2), (b"bad", 1)):
            self.archive.write_bytes(data)
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, status, result.stderr)
            if status == 1:
                self.assertEqual(result.stdout, "")
                self.assertIn("handoff-review:", result.stderr)
            else:
                self.assertEqual(json.loads(result.stdout)["selected_checks_passed"], status == 0)
        self.archive.write_bytes(self.data)
        (self.source / "extra").write_bytes(b"new")
        result = subprocess.run(command + ["--source", str(self.source)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(json.loads(result.stdout)["failed_checks"], ["source"])
        result = subprocess.run(command + ["--sha256", "bad"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
