#!/usr/bin/env python3
"""Run the line tools' reviewed offline checks in a workspace scratch mirror."""
import datetime
import json
from pathlib import Path
import re
import shutil
import subprocess

from check_round11 import DEMOS as OLD_DEMOS
DEMOS = list(OLD_DEMOS)

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / 'test/scratch/round-15-mirror'
OUT = ROOT / 'gathering/checks/round-15'
EXTRA_DEMOS = [
    ["line-1/tools/snapshot-crosscheck/snapshot_crosscheck.py", "demo"],
    ["line-3/tools/fee-horizon/fee_horizon.py", "--demo", "--parent-base-fee-wei", "1000000000", "--blocks", "4"],
    ["line-4/tools/bounded-capture-reader/reader.py", "--demo"],
    ['line-3/tools/keccak-envelope/keccak_envelope.py', '--demo'],
    ['line-4/tools/transfer-window-stitch/stitch.py', '--demo'],
    ['line-2/tools/handoff-landing/landing.py', 'demo'],
    ['line-3/tools/rlp-byte-map/byte_map.py', '--demo'],
    ['line-4/tools/transfer-window-ledger/ledger.py', '--demo'],
    ['line-1/tools/snapshot-seal/snapshot_seal.py', 'seal', 'line-1/tools/pinned-snapshot/example-zto.json'],

    ['line-1/tools/pinned-transport-check/pinned_transport_check.py', 'demo'],
    ['line-3/tools/amount-view/amount_view.py', '--demo'],
    ['line-3/tools/canonical-envelope/envelope.py', '--demo'],
]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True, exist_ok=True)
    for number in range(1, 5):
        shutil.copytree(ROOT / f'line-{number}', STAGE / f'line-{number}',
                        dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__'))
    (STAGE / 'test/scratch').mkdir(parents=True, exist_ok=True)
    # The original fixture directs temporary files to /tmp. Only this mirror
    # points them into the workspace scratch area.
    fixture = STAGE / 'line-2/tools/handoff-source/test_source.py'
    fixture.write_text(fixture.read_text().replace(
        'dir="/tmp"', 'dir=str(self.previous / "test/scratch")'))
    # Default tempfile fixtures are also confined to the scratch mirror.
    for test in STAGE.glob('line-*/tools/*/test*.py'):
        test.write_text(test.read_text().replace('tempfile.TemporaryDirectory()', "tempfile.TemporaryDirectory(dir='test/scratch')"))
    tests = [['-m', 'unittest', 'discover', '-s', p.parent.relative_to(STAGE).as_posix(), '-p', p.name, '-v'] for number in range(1, 5)
             for p in sorted((STAGE / f'line-{number}/tools').glob('*/test*.py'))]
    commands = [(x, 'suite') for x in tests] + [(x, 'demo') for x in DEMOS + EXTRA_DEMOS]
    summary = []
    for index, (args, kind) in enumerate(commands, 1):
        command = ['python3', '-B', *args]
        try:
            run = subprocess.run(command, cwd=STAGE, capture_output=True,
                                 text=True, timeout=60)
            record = {'exit': run.returncode, 'stdout': run.stdout, 'stderr': run.stderr}
        except subprocess.TimeoutExpired:
            record = {'exit': 124, 'stdout': '', 'stderr': '60-second check timeout'}
        found = re.search(r'Ran (\d+) tests?', record['stderr'])
        record.update({'command': command, 'kind': kind,
                       'tests_run': int(found[1]) if found else 0,
                       'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                       'workspace': 'test/scratch/round-15-mirror'})
        raw = json.dumps(record, indent=2) + '\n'
        if len(raw.encode()) >= 100000:
            raise ValueError('check receipt exceeds 100 KB')
        (OUT / f'tool-{index:02d}.json').write_text(raw)
        summary.append({key: record[key] for key in ('command', 'exit', 'kind', 'tests_run')})
        print(index, kind, record['exit'], record['tests_run'], *args, flush=True)
    (OUT / 'tool-checks.json').write_text(json.dumps(summary, indent=2) + '\n')
    return int(any(item['exit'] for item in summary))


if __name__ == '__main__':
    raise SystemExit(main())
