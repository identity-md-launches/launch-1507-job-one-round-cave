"""Behavioral integration checks over retained real Ethereum evidence."""
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import horizon_context as tool


class HorizonContextTests(unittest.TestCase):
    def setUp(self):
        self.obj = tool.demo_input()

    def test_real_parent_and_independently_computed_paths_offline(self):
        with patch.object(socket, 'socket', side_effect=AssertionError('network forbidden')):
            result = tool.inspect(self.obj)
        base = int(self.obj['snapshot']['block']['baseFeePerGas'], 16)
        upper = lower = base
        for row in result['hypothetical_children']['rows']:
            upper += max(upper // 8, 1)
            lower -= lower // 8
            self.assertEqual(int(row['afterFullParents']['baseFeePerGasWei']), upper)
            self.assertEqual(int(row['afterEmptyParents']['baseFeePerGasWei']), lower)
        self.assertEqual(result['snapshot']['block_hash'], self.obj['snapshot']['block']['hash'])
        self.assertEqual(result['snapshot']['token'], '0xd782bdea4ef02a0bd391eb9089470c8080f0a68e')
        self.assertFalse(result['transaction_execution_verified'])
        self.assertEqual(result, tool.inspect(self.obj))

    def test_same_original_transaction_json_or_rlp(self):
        a = tool.inspect(self.obj)
        self.obj.update(transaction=json.dumps(tool.horizon.fee_context.reader.demo_object()), input_format='json')
        b = tool.inspect(self.obj)
        self.assertEqual(a['hypothetical_children']['rows'], b['hypothetical_children']['rows'])
        self.assertEqual(a['hypothetical_children']['inspection'], b['hypothetical_children']['inspection'])

    def test_untrusted_snapshot_rejected_before_model(self):
        for mutation in ('chain', 'fee', 'hash', 'method'):
            obj = copy.deepcopy(self.obj)
            s = obj['snapshot']
            if mutation == 'chain': s['chain_id'] = '0x2'
            if mutation == 'fee': s['block_after']['baseFeePerGas'] = '0x0'
            if mutation == 'hash': s['block_after']['hash'] = s['block']['parentHash']
            if mutation == 'method': s['method'] = 'eth_blockNumber'
            with self.subTest(mutation=mutation), patch.object(tool.horizon, 'inspect', side_effect=AssertionError('model used')):
                with self.assertRaises(ValueError): tool.inspect(obj)

    def test_original_transaction_only_and_chain_must_match(self):
        for field in ('chainId', 'from', 'r'):
            tx = tool.horizon.fee_context.reader.demo_object()
            tx[field] = '0x2' if field == 'chainId' else '0x1'
            self.obj.update(transaction=json.dumps(tx), input_format='json')
            with self.subTest(field=field), self.assertRaises(ValueError): tool.inspect(self.obj)
        self.obj.update(transaction='{"inspection":{}}', input_format='json')
        with self.assertRaises(ValueError): tool.inspect(self.obj)

    def test_expected_snapshot_digest(self):
        self.obj['expected_snapshot_sha256'] = hashlib.sha256(tool.context.canonical(self.obj['snapshot'])).hexdigest()
        self.assertTrue(tool.inspect(self.obj)['snapshot']['expected_digest_matched'])
        self.obj['expected_snapshot_sha256'] = 'f' * 64
        with self.assertRaises(ValueError): tool.inspect(self.obj)

    def test_block_boundaries_and_uint256_model_limit(self):
        for count in (1, 64):
            self.obj['blocks'] = count
            self.assertEqual(len(tool.inspect(self.obj)['hypothetical_children']['rows']), count)
        for bad in (True, 0, 65, '4', 4.0):
            self.obj['blocks'] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError): tool.inspect(self.obj)
        self.obj['blocks'] = 2
        for key in ('block', 'block_after'):
            self.obj['snapshot'][key]['baseFeePerGas'] = hex(2**256 - 1)
        # Document rather than silently repair the native model's overflow limit.
        with self.assertRaises(ValueError): tool.inspect(self.obj)

    def test_priority_violation_retains_diagnostic_and_exit_one(self):
        tx = tool.horizon.fee_context.reader.demo_object()
        tx.update(maxPriorityFeePerGas='0x2', maxFeePerGas='0x1')
        self.obj.update(transaction=json.dumps(tx), input_format='json')
        report = tool.inspect(self.obj)
        self.assertEqual(report['hypothetical_children']['checkedViolations'], ['priority-fee-exceeds-max-fee'])
        self.assertFalse(any(row['feeCapPossibleWithinModeledRange'] for row in report['hypothetical_children']['rows']))
        stream = io.TextIOWrapper(io.BytesIO(json.dumps(self.obj).encode()))
        with patch.object(sys, 'stdin', stream), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(tool.main(['inspect']), 1)

    def test_strict_json_and_no_partial_cli_output(self):
        for raw in (b'{"x":1,"x":2}', b'NaN', b'1e999', b'\xff', b'x' * 99001):
            with self.subTest(raw=raw[:30]), self.assertRaises((ValueError, UnicodeError)):
                tool.parse(raw)
        for obj in (None, [], {}, dict(self.obj, extra=True)):
            with self.assertRaises(ValueError): tool.inspect(obj)
        out, err = io.StringIO(), io.StringIO()
        with patch.object(sys, 'stdin', io.TextIOWrapper(io.BytesIO(b'{}'))), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(tool.main(['inspect']), 2)
        self.assertEqual(out.getvalue(), '')
        self.assertNotIn('Traceback', err.getvalue())

    def test_all_vendored_bytes_match_provenance(self):
        workspace = tool.HERE.parents[1]
        for entry in json.loads((tool.HERE / 'PROVENANCE.json').read_text()):
            for path in (workspace / entry['source'], tool.HERE / entry['copy']):
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), entry['sha256'])

    def test_standalone_folder_in_scratch_without_line_folders(self):
        scratch = tool.HERE.parents[1] / 'test/scratch'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as temporary:
            copied = Path(temporary) / 'kit'
            shutil.copytree(tool.HERE, copied, ignore=shutil.ignore_patterns('__pycache__'))
            run = subprocess.run([sys.executable, '-B', str(copied / 'horizon_context.py'), 'demo'],
                                 cwd=copied, capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertTrue(json.loads(run.stdout)['offline'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
