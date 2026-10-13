#!/usr/bin/env python3
"""Compare a saved ZTO snapshot with read-only observations from another RPC."""
import argparse
import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

TOOLS = Path(__file__).resolve().parents[1]


def sibling(name, file):
    spec = importlib.util.spec_from_file_location(name, TOOLS / name / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


seal = sibling('snapshot-seal', 'snapshot_seal.py')
pinned = seal.pinned
rpc = pinned.rpc
SCHEMA = 'pinned-zto-crosscheck/1'
DEFAULT_RPC = 'https://eth.drpc.org'


def utc_stamp(value):
    if not isinstance(value, str) or not value.endswith('Z'):
        raise ValueError('missing UTC capture time')
    parsed = dt.datetime.fromisoformat(value[:-1] + '+00:00')
    if parsed.utcoffset() != dt.timedelta(0):
        raise ValueError('capture time is not UTC')


def source(path):
    raw, bundle, facts = seal.load_snapshot(path)
    return raw, bundle, facts


def expected_requests(number):
    return [('eth_chainId', []),
            ('eth_getBlockByNumber', [number, False]),
            ('eth_call', [dict(pinned.CALL), number]),
            ('eth_getBlockByNumber', [number, False])]


def evidence(source_raw, source_bundle, endpoint, reads):
    facts = pinned.inspect(source_bundle)
    rpc.validate_endpoint(endpoint)
    if endpoint == source_bundle['endpoint']:
        raise ValueError('the second endpoint must differ from the source endpoint')
    number = source_bundle['block']['number']
    if not isinstance(reads, list) or len(reads) != 4:
        raise ValueError('exactly four observations are required')
    for item, (method, params) in zip(reads, expected_requests(number)):
        if not isinstance(item, dict) or set(item) != {
                'captured_at', 'endpoint', 'method', 'params', 'result'}:
            raise ValueError('invalid read observation')
        utc_stamp(item['captured_at'])
        if (item['endpoint'] != endpoint or item['method'] != method
                or item['params'] != params):
            raise ValueError('read request or endpoint differs')
    chain = reads[0]['result']
    if not isinstance(chain, str):
        raise ValueError('invalid chain response')
    before = pinned.check_block(reads[1]['result'])
    result = reads[2]['result']
    if not rpc.hex_data(result, 32):
        raise ValueError('totalSupply result must be an ABI uint256 word')
    after = pinned.check_block(reads[3]['result'])
    stable = (int(before['number'], 16) == int(after['number'], 16)
              and before['hash'].lower() == after['hash'].lower()
              and before['parentHash'].lower() == after['parentHash'].lower()
              and int(before['timestamp'], 16) == int(after['timestamp'], 16))
    original = source_bundle['block']
    same_block = (int(before['number'], 16) == int(original['number'], 16)
                  and before['hash'].lower() == original['hash'].lower()
                  and before['parentHash'].lower() == original['parentHash'].lower()
                  and int(before['timestamp'], 16) == int(original['timestamp'], 16))
    same_result = result.lower() == source_bundle['result'].lower()
    same_chain = chain == source_bundle['chain_id'] == '0x1'
    status = ('chain_disagreement' if not same_chain else
              'unstable_second_provider' if not stable else
              'block_disagreement' if not same_block else
              'result_disagreement' if not same_result else 'agreement')
    return {
        'schema': SCHEMA,
        'source_sha256': hashlib.sha256(source_raw).hexdigest(),
        'source_observation': {key: facts[key] for key in
                               ('block_number', 'block_hash', 'token', 'total_supply_base_units')},
        'second_endpoint': endpoint,
        'reads': reads,
        'status': status,
        'evidence_limits': ('Two provider observations at one numbered block; '
                            'not a signature, proof of provider independence or honesty, '
                            'finality, or current state.'),
    }


def capture(path, endpoint=DEFAULT_RPC):
    raw, bundle, _ = source(path)
    rpc.validate_endpoint(endpoint)
    if endpoint == bundle['endpoint']:
        raise ValueError('the second endpoint must differ from the source endpoint')
    reads = [rpc.capture(method, params, endpoint) for method, params in
             expected_requests(bundle['block']['number'])]
    return evidence(raw, bundle, endpoint, reads)


def verify(snapshot_path, evidence_path):
    raw, bundle, _ = source(snapshot_path)
    saved = rpc.strict_json(seal.read_bytes(evidence_path))
    if not isinstance(saved, dict) or set(saved) != {
            'schema', 'source_sha256', 'source_observation', 'second_endpoint',
            'reads', 'status', 'evidence_limits'} or saved['schema'] != SCHEMA:
        raise ValueError('invalid crosscheck evidence')
    computed = evidence(raw, bundle, saved['second_endpoint'], saved['reads'])
    if saved != computed:
        raise ValueError('crosscheck evidence does not match source and reads')
    return {'verified': True, 'status': computed['status'],
            'source_sha256': computed['source_sha256'],
            'block_number': computed['source_observation']['block_number'],
            'block_hash': computed['source_observation']['block_hash'],
            'source_endpoint': bundle['endpoint'],
            'second_endpoint': computed['second_endpoint'],
            'total_supply_base_units': computed['source_observation']['total_supply_base_units'],
            'network_used': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    check = commands.add_parser('check', help='make four read-only second-provider observations')
    check.add_argument('snapshot')
    check.add_argument('--rpc', default=DEFAULT_RPC)
    offline = commands.add_parser('verify', help='inspect saved evidence without a network')
    offline.add_argument('snapshot')
    offline.add_argument('crosscheck')
    commands.add_parser('demo', help='verify the retained real ZTO crosscheck offline')
    args = parser.parse_args()
    try:
        if args.command == 'check':
            result = capture(args.snapshot, args.rpc)
        else:
            snapshot = (TOOLS / 'snapshot-seal' / 'current-zto.json' if args.command == 'demo'
                        else args.snapshot)
            crosscheck = (Path(__file__).with_name('example-crosscheck.json') if
                          args.command == 'demo' else args.crosscheck)
            result = verify(snapshot, crosscheck)
    except (OSError, ValueError, TypeError, KeyError, RuntimeError,
            UnicodeError, RecursionError, OverflowError):
        print('snapshot-crosscheck: invalid source, evidence, or RPC response', file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result['status'] == 'agreement' else 2


if __name__ == '__main__':
    raise SystemExit(main())
