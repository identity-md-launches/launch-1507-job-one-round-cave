"""Offline file-boundary regressions; fixtures stay in test/scratch/."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reader = load('bounded_reader_tests', HERE / 'reader.py')
CONSUMERS = [load('bounded_' + name, HERE.parent / ('transfer-window-' + name) / (name + '.py'))
             for name in ('activity', 'coverage', 'receipt')]


class ReaderTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / 'test/scratch'
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'capture.json'
        self.path.write_text('{"ok":true}')

    def test_real_zto_demo(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            reader.main(['--demo'])
        report = json.loads(output.getvalue())
        self.assertEqual((report['token'], report['transfer_count']), ('ZTO', 3))
        self.assertTrue(report['raw_logs_revalidated'])

    def test_regular_file_and_exact_limit(self):
        self.assertEqual(reader.read_capture(self.path, 11), {'ok': True})
        with self.assertRaisesRegex(ValueError, 'byte limit'):
            reader.read_capture(self.path, 10)

    def test_outside_rejected_before_open(self):
        with mock.patch.object(reader.os, 'open', side_effect=AssertionError('must not open')):
            with self.assertRaisesRegex(ValueError, 'workspace'):
                reader.read_capture(ROOT.parent / 'not-a-real-input.json')

    def test_traversal_rejected_before_open(self):
        with mock.patch.object(reader.os, 'open', side_effect=AssertionError('must not open')):
            with self.assertRaisesRegex(ValueError, 'traversal'):
                reader.read_capture(self.root / '..' / 'capture.json')

    def test_final_symlink_rejected(self):
        link = self.root / 'link.json'
        link.symlink_to(self.path)
        with self.assertRaisesRegex(ValueError, 'cannot read'):
            reader.read_capture(link)

    def test_directory_symlink_rejected(self):
        link = self.root / 'dir-link'
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'cannot read'):
            reader.read_capture(link / 'capture.json')

    def test_directory_and_missing_file_rejected(self):
        for path in (self.root, self.root / 'missing.json'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                reader.read_capture(path)

    def test_fifo_rejected_without_blocking(self):
        fifo = self.root / 'pipe'
        os.mkfifo(fifo)
        result = subprocess.run([sys.executable, '-B', str(HERE / 'reader.py'), '--capture', str(fifo)],
                                cwd=ROOT, capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('regular file', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_strict_json(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":{"a":1,"a":2}}', b'NaN',
                    b'Infinity', b'-Infinity', b'1e999', b'\xff', b'{} {}', b'\xef\xbb\xbf{}'):
            with self.subTest(raw=raw):
                self.path.write_bytes(raw)
                with self.assertRaisesRegex(ValueError, 'strict UTF-8 JSON'):
                    reader.read_capture(self.path)

    def test_deep_json_refused_cleanly(self):
        self.path.write_text('[' * 2000 + ']' * 2000)
        with self.assertRaisesRegex(ValueError, 'strict UTF-8 JSON'):
            reader.read_capture(self.path)

    def test_nesting_limit_ignores_escaped_string_delimiters(self):
        value = {'text': '[' * 100 + '\"' + ']' * 100}
        self.path.write_text(json.dumps(value))
        self.assertEqual(reader.read_capture(self.path), value)
        self.path.write_text('[' * 64 + '0' + ']' * 64)
        self.assertIsInstance(reader.read_capture(self.path), list)
        self.path.write_text('[' * 65 + '0' + ']' * 65)
        with self.assertRaisesRegex(ValueError, 'nesting'):
            reader.read_capture(self.path)

    def test_invalid_limits(self):
        for limit in (0, -1, True, 1.5, reader.MAX_BYTES + 1):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                reader.read_capture(self.path, limit)

    def test_read_is_bounded_even_if_file_grows_after_stat(self):
        fake_stream = mock.MagicMock()
        fake_stream.__enter__.return_value = fake_stream
        fake_stream.read.return_value = b'x' * 13
        def substitute(fd, mode):
            os.close(fd)
            return fake_stream
        with mock.patch.object(reader.os, 'fdopen', side_effect=substitute):
            with self.assertRaisesRegex(ValueError, 'byte limit'):
                reader.read_capture(self.path, 12)
        fake_stream.read.assert_called_once_with(13)

    def test_three_consumers_share_restrictions(self):
        link = self.root / 'link.json'
        link.symlink_to(self.path)
        for consumer in CONSUMERS:
            for path in (ROOT.parent / 'not-a-real-input.json', link):
                with self.subTest(consumer=consumer.__name__, path=path), self.assertRaises(ValueError):
                    consumer.read_capture(path)
            with mock.patch.object(consumer, 'MAX_CAPTURE_BYTES', 10):
                with self.assertRaisesRegex(ValueError, 'byte limit'):
                    consumer.read_capture(self.path)
            with mock.patch.object(consumer.crosscheck.window, 'rpc', side_effect=AssertionError('offline only')):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    consumer.main(['--demo'])
                self.assertEqual(json.loads(output.getvalue())['transfer_count'], 3)

    def test_consumer_cli_rejects_bad_input_cleanly(self):
        self.path.write_text('{"a":NaN}')
        for consumer in CONSUMERS:
            result = subprocess.run([sys.executable, '-B', consumer.__file__, '--capture', str(self.path)],
                                    cwd=ROOT, capture_output=True, text=True, timeout=5)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, '')
            self.assertIn('strict UTF-8 JSON', result.stderr)
            self.assertNotIn('Traceback', result.stderr)


if __name__ == '__main__':
    unittest.main()
