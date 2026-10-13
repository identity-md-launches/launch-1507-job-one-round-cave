#!/usr/bin/env python3
"""Read-only current trials; preserve explicit failures and exact public evidence."""
import datetime
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'gathering/checks/round-15'


def command(name, args, input_text=None):
    argv = ['python3', '-B', *args]
    try:
        run = subprocess.run(argv, cwd=ROOT, input=input_text,
                             capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        record = {'command': argv, 'exit': 124, 'stdout': '',
                  'stderr': '60-second trial timeout'}
        (OUT / (name + '-trial.json')).write_text(json.dumps(record, indent=2)+'\n')
        print(name, 124, 'timeout', flush=True)
        return None
    record = {'command': argv, 'exit': run.returncode, 'stdout': run.stdout,
              'stderr': run.stderr, 'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    data = json.dumps(record, indent=2)+'\n'
    if len(data.encode()) >= 100000:
        raise ValueError('trial receipt exceeds 100 KB')
    (OUT / (name + '-trial.json')).write_text(data)
    if run.returncode == 0:
        evidence = json.loads(run.stdout)
        # Preserve the native CLI's exact JSON bytes, not a rewritten capture.
        (OUT / (name + '.json')).write_text(run.stdout)
    else:
        evidence = None
    print(name, run.returncode, run.stderr.strip(), flush=True)
    return evidence


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    snapshot = command('original-zto-supply', [
        'line-1/tools/rpc-snapshot/rpc_snapshot.py', 'eth_call',
        '[{"to":"0xd782bdea4ef02a0bd391eb9089470c8080f0a68e","data":"0x18160ddd"},"finalized"]'])
    command('pinned-zto-supply', ['line-1/tools/pinned-snapshot/pinned_snapshot.py', 'capture'])
    command('block-audit', ['line-1/tools/block-audit/block_audit.py', 'demo'])
    result = command('historical-zto-publicnode', [
        'line-4/tools/erc20-transfer-window/transfer_window.py',
        '--from-block', '26177298', '--to-block', '26177309'])
    if result is None:
        # PublicNode was attempted first; switch only after its explicit refusal.
        result = command('historical-zto-drpc', [
            'line-4/tools/erc20-transfer-window/transfer_window.py',
            '--rpc', 'https://eth.drpc.org', '--from-block', '26177298', '--to-block', '26177309'])
    current = command('current-zto-publicnode', [
        'line-4/tools/erc20-transfer-window/transfer_window.py', '--latest-window', '2'])
    if current is None:
        current = command('current-zto-drpc', [
            'line-4/tools/erc20-transfer-window/transfer_window.py',
            '--rpc', 'https://eth.drpc.org', '--latest-window', '2'])
    if snapshot:
        command('original-zto-inspection', ['line-1/tools/snapshot-check/check_snapshot.py'],
                (OUT / 'original-zto-supply.json').read_text())
    for prefix in ('historical-zto-publicnode', 'historical-zto-drpc',
                   'current-zto-publicnode', 'current-zto-drpc'):
        capture = OUT / (prefix + '.json')
        if capture.exists():
            command(prefix + '-ledger', ['line-4/tools/transfer-window-ledger/ledger.py',
                                       '--capture', str(capture.relative_to(ROOT))])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
