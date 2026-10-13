"""Behavioral checks for bounded, offline EIP-1559 fee paths."""

import json
from pathlib import Path
import subprocess
import sys
import unittest

import fee_horizon as h


class HorizonTests(unittest.TestCase):
    def transaction(self, cap=100, priority=10, chain=1):
        obj = h.fee_context.reader.demo_object()
        obj.update(maxFeePerGas=hex(cap), maxPriorityFeePerGas=hex(priority),
                   chainId=hex(chain))
        return json.dumps(obj)

    def test_integer_step_rounding(self):
        self.assertEqual(h.next_base_fee(0, True), 1)
        self.assertEqual(h.next_base_fee(1, True), 2)
        self.assertEqual(h.next_base_fee(7, False), 7)
        self.assertEqual(h.next_base_fee(8, False), 7)
        self.assertEqual(h.next_base_fee(8, True), 9)
        self.assertEqual(h.next_base_fee(100, True), 112)
        self.assertEqual(h.next_base_fee(100, False), 88)

    def test_multiple_steps_and_cap_boundary(self):
        report = h.inspect(self.transaction(cap=120, priority=10), 100, 3, "json")
        rows = report["rows"]
        self.assertEqual([int(row["afterFullParents"]["baseFeePerGasWei"]) for row in rows],
                         [112, 126, 141])
        self.assertEqual([int(row["afterEmptyParents"]["baseFeePerGasWei"]) for row in rows],
                         [88, 77, 68])
        self.assertTrue(rows[0]["feeCapGuaranteedAcrossModeledRange"])
        self.assertFalse(rows[0]["fullPriorityGuaranteedAcrossModeledRange"])
        self.assertEqual(rows[0]["afterFullParents"]["effectivePriorityFeePerGasWei"], "8")
        self.assertFalse(rows[1]["feeCapGuaranteedAcrossModeledRange"])
        self.assertIsNone(rows[1]["afterFullParents"]["effectiveGasPriceWei"])
        self.assertTrue(rows[1]["feeCapPossibleWithinModeledRange"])

    def test_parent_fee_can_start_above_cap_and_empty_path_recovers(self):
        rows = h.inspect(self.transaction(cap=85), 100, 2, "json")["rows"]
        self.assertFalse(rows[0]["feeCapPossibleWithinModeledRange"])
        self.assertTrue(rows[1]["feeCapPossibleWithinModeledRange"])
        self.assertEqual(rows[1]["afterEmptyParents"]["effectiveGasPriceWei"], "85")

    def test_priority_over_cap_never_claims_coverage(self):
        report = h.inspect(self.transaction(cap=100, priority=101), 50, 2, "json")
        self.assertEqual(report["checkedViolations"], ["priority-fee-exceeds-max-fee"])
        for row in report["rows"]:
            self.assertFalse(row["feeCapGuaranteedAcrossModeledRange"])
            self.assertFalse(row["feeCapPossibleWithinModeledRange"])
            self.assertIsNone(row["afterEmptyParents"]["effectiveGasPriceWei"])

    def test_original_json_rlp_equivalence_and_zto(self):
        reader = h.fee_context.reader
        a = h.inspect(reader.D.demo_transaction(), 1_000_000_000, 4)
        b = h.inspect(json.dumps(reader.demo_object()), 1_000_000_000, 4, "json")
        self.assertEqual(a["rows"], b["rows"])
        self.assertEqual(a["inspection"], b["inspection"])
        self.assertEqual(a["inspection"]["destinationLabel"], "ZTO")

    def test_rejects_untrusted_or_unbounded_inputs(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            h.inspect(self.transaction(chain=2), 1, 1, "json")
        for bad in (0, 65, True, 1.5, "3"):
            with self.assertRaises(ValueError):
                h.inspect(self.transaction(), 1, bad, "json")
        for bad in ("00", "65", "-1", "1.5", ""):
            with self.assertRaises(ValueError):
                h.block_count(bad)
        with self.assertRaises(ValueError):
            h.inspect(self.transaction(), -1, 2, "json")
        with self.assertRaises(ValueError):
            h.inspect('{"inspection":{}}', 1, 2, "json")
        obj = json.loads(self.transaction())
        obj["from"] = "0x0"
        with self.assertRaises(ValueError):
            h.inspect(json.dumps(obj), 1, 2, "json")

    def test_cli_demo_and_invalid_exit(self):
        script = Path(__file__).with_name("fee_horizon.py")
        good = subprocess.run([sys.executable, "-B", str(script), "--demo",
                               "--parent-base-fee-wei", "1000000000", "--blocks", "4"],
                              capture_output=True, text=True)
        self.assertEqual(good.returncode, 0, good.stderr)
        report = json.loads(good.stdout)
        self.assertEqual(report["schema"], "fee-horizon/v1")
        self.assertEqual(len(report["rows"]), 4)
        bad = subprocess.run([sys.executable, "-B", str(script), "--demo",
                              "--parent-base-fee-wei", "1000000000", "--blocks", "65"],
                             capture_output=True, text=True)
        self.assertEqual(bad.returncode, 2)
        self.assertEqual(bad.stdout, "")


if __name__ == "__main__":
    unittest.main()
