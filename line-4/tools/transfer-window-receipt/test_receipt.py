"""Offline tests for semantic receipts over retained real ZTO evidence."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest import mock


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("receipt", HERE / "receipt.py")
receipt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(receipt)


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.capture = json.loads((HERE.parent / "transfer-crosscheck" / "publicnode.json").read_text())

    def test_retained_real_evidence_has_stable_receipt(self):
        result = receipt.receipt(self.capture)
        self.assertEqual(result["token"], "ZTO")
        self.assertEqual(result["transfer_count"], 3)
        self.assertEqual(len(result["window_sha256"]), 64)
        self.assertEqual(len(result["capture_sha256"]), 64)

    def test_duplicate_delivery_and_log_order_do_not_change_window_fingerprint(self):
        altered = copy.deepcopy(self.capture)
        altered["raw_logs"] = list(reversed(altered["raw_logs"])) + [altered["raw_logs"][0]]
        events, duplicate_count = receipt.crosscheck.window.validate_logs(
            altered["raw_logs"], altered["decimals"], altered["token_address"],
            altered["from_block"], altered["to_block"])
        altered.update(transfers=events, transfer_count=len(events), duplicate_count=duplicate_count)
        self.assertEqual(receipt.receipt(self.capture)["window_sha256"],
                         receipt.receipt(altered)["window_sha256"])
        self.assertNotEqual(receipt.receipt(self.capture)["capture_sha256"],
                            receipt.receipt(altered)["capture_sha256"])

    def test_tampered_summary_or_raw_log_is_rejected(self):
        bad_summary = copy.deepcopy(self.capture)
        bad_summary["transfer_count"] = 0
        with self.assertRaises(receipt.crosscheck.window.RpcError):
            receipt.receipt(bad_summary)
        bad_log = copy.deepcopy(self.capture)
        bad_log["raw_logs"][0]["removed"] = True
        with self.assertRaises(receipt.crosscheck.window.RpcError):
            receipt.receipt(bad_log)

    def test_reader_rejects_duplicate_json_keys_and_oversized_inputs(self):
        duplicate = HERE / "duplicate.json"
        duplicate.write_text('{"token":"ZTO","token":"IMD"}')
        self.addCleanup(duplicate.unlink)
        with self.assertRaises(ValueError):
            receipt.read_capture(duplicate)
        with mock.patch.object(receipt, "MAX_CAPTURE_BYTES", 8):
            with self.assertRaisesRegex(ValueError, "byte limit"):
                receipt.read_capture(duplicate)

    def test_demo_emits_valid_json(self):
        from contextlib import redirect_stdout
        output = io.StringIO()
        with redirect_stdout(output):
            receipt.main(["--demo"])
        self.assertEqual(json.loads(output.getvalue())["kind"], "erc20-transfer-window-receipt")


if __name__ == "__main__":
    unittest.main()
