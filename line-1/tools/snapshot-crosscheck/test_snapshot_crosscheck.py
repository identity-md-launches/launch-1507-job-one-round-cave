#!/usr/bin/env python3
"""Offline checks for the retained real second-provider observations."""
import copy
import importlib.util
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest import mock

SOURCE = Path(__file__).with_name('snapshot_crosscheck.py')
spec = importlib.util.spec_from_file_location('snapshot_crosscheck', SOURCE)
cross = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cross)
SNAPSHOT = cross.TOOLS / 'snapshot-seal' / 'current-zto.json'
EVIDENCE = SOURCE.with_name('example-crosscheck.json')


class CrosscheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Path('test/scratch').mkdir(parents=True, exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(dir='test/scratch')
        cls.folder = Path(cls.temp.name)
        cls.raw, cls.bundle, _ = cross.source(SNAPSHOT)
        cls.saved = json.loads(EVIDENCE.read_text())

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def changed(self, mutator):
        data = copy.deepcopy(self.saved)
        mutator(data)
        return data

    def evidence(self, data):
        return cross.evidence(self.raw, self.bundle,
                              data['second_endpoint'], data['reads'])

    def test_retained_real_observation_offline_and_network_free(self):
        with mock.patch.object(socket, 'create_connection', side_effect=AssertionError('network')):
            report = cross.verify(SNAPSHOT, EVIDENCE)
        self.assertEqual(report['status'], 'agreement')
        self.assertEqual(report['block_number'], '26180977')
        self.assertEqual(report['total_supply_base_units'], '1000000000000000000000000000')
        self.assertFalse(report['network_used'])

    def test_wrong_chain_is_disagreement(self):
        data = self.changed(lambda d: d['reads'][0].update(result='0xaa36a7'))
        self.assertEqual(self.evidence(data)['status'], 'chain_disagreement')

    def test_block_disagreement(self):
        def change(d):
            for index in (1, 3):
                d['reads'][index]['result']['hash'] = '0x' + '1' * 64
        self.assertEqual(self.evidence(self.changed(change))['status'], 'block_disagreement')

    def test_unstable_second_provider(self):
        data = self.changed(lambda d: d['reads'][3]['result'].update(hash='0x' + '1' * 64))
        self.assertEqual(self.evidence(data)['status'], 'unstable_second_provider')

    def test_supply_disagreement(self):
        data = self.changed(lambda d: d['reads'][2].update(result='0x' + '0' * 63 + '1'))
        self.assertEqual(self.evidence(data)['status'], 'result_disagreement')

    def test_wrong_block_number_is_disagreement(self):
        def change(d):
            for index in (1, 3):
                d['reads'][index]['result']['number'] = '0x1'
        self.assertEqual(self.evidence(self.changed(change))['status'], 'block_disagreement')

    def test_hex_letter_case_is_not_a_disagreement(self):
        def change(d):
            for index in (1, 3):
                d['reads'][index]['result']['hash'] = d['reads'][index]['result']['hash'].upper().replace('0X', '0x')
            d['reads'][2]['result'] = d['reads'][2]['result'].upper().replace('0X', '0x')
        self.assertEqual(self.evidence(self.changed(change))['status'], 'agreement')

    def test_request_tampering_rejected(self):
        data = self.changed(lambda d: d['reads'][2]['params'][0].update(data='0x70a08231'))
        with self.assertRaises(ValueError):
            self.evidence(data)

    def test_same_endpoint_rejected_before_network(self):
        with mock.patch.object(cross.rpc, 'capture', side_effect=AssertionError('network')):
            with self.assertRaises(ValueError):
                cross.capture(SNAPSHOT, self.bundle['endpoint'])

    def test_false_status_rejected(self):
        data = self.changed(lambda d: d.update(status='agreement-but-unchecked'))
        path = self.folder / 'false.json'
        path.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            cross.verify(SNAPSHOT, path)

    def test_duplicate_json_key_rejected(self):
        path = self.folder / 'duplicate.json'
        path.write_bytes(EVIDENCE.read_bytes().replace(b'"schema":', b'"schema":"wrong","schema":', 1))
        with self.assertRaises(ValueError):
            cross.verify(SNAPSHOT, path)

    def test_source_byte_change_rejected(self):
        path = self.folder / 'changed-source.json'
        path.write_bytes(SNAPSHOT.read_bytes() + b' ')
        with self.assertRaises(ValueError):
            cross.verify(path, EVIDENCE)


if __name__ == '__main__':
    unittest.main()
