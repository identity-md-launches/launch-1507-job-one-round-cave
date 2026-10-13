#!/usr/bin/env python3
"""Capture and inspect a block-pinned public Ethereum ZTO supply observation."""
import argparse
import datetime
import importlib.util
import json
from pathlib import Path
import sys
import urllib.request

source = Path(__file__).resolve().parents[1] / 'rpc-snapshot' / 'rpc_snapshot.py'
spec = importlib.util.spec_from_file_location('rpc_snapshot', source)
rpc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rpc)
ZTO = '0xd782bdea4ef02a0bd391eb9089470c8080f0a68e'
CALL = {'to': ZTO, 'data': '0x18160ddd'}
LIMIT = rpc.MAX_RESPONSE_BYTES


def quantity(value):
    return isinstance(value, str) and rpc.block_tag(value) and value.startswith('0x')


def public_read(endpoint, method, params):
    # Keep one transport policy for both original and pinned observations.
    # capture validates before opening its explicit proxy-free, no-redirect opener.
    return rpc.capture(method, params, endpoint)['result']


def check_block(block, number=None):
    if not isinstance(block, dict) or not quantity(block.get('number')):
        raise ValueError('missing or malformed block number')
    if not rpc.hex_data(block.get('hash'), 32):
        raise ValueError('missing or malformed block hash')
    if number is not None and block['number'] != number:
        raise ValueError('provider returned a different block number')
    if not rpc.hex_data(block.get('parentHash'), 32) or not quantity(block.get('timestamp')):
        raise ValueError('malformed block parent or timestamp')
    return block


def capture(endpoint=rpc.DEFAULT_RPC, tag='finalized', read=None):
    rpc.validate_endpoint(endpoint)
    if not rpc.block_tag(tag):
        raise ValueError('invalid block tag')
    if tag == 'pending':
        raise ValueError('pending has no stable block identity')
    read = read or (lambda method, params: public_read(endpoint, method, params))
    chain = read('eth_chainId', [])
    if chain != '0x1':
        raise ValueError('ZTO capture requires Ethereum mainnet chain ID 0x1')
    block = check_block(read('eth_getBlockByNumber', [tag, False]), tag if quantity(tag) else None)
    number = block['number']
    result = read('eth_call', [dict(CALL), number])
    if not rpc.hex_data(result, 32):
        raise ValueError('totalSupply result must be exactly one ABI uint256 word')
    after = check_block(read('eth_getBlockByNumber', [number, False]), number)
    if after['hash'] != block['hash']:
        raise ValueError('block hash changed during capture; discard and retry')
    bundle = {'schema': 'pinned-zto-snapshot/1',
              'captured_at': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z'),
              'endpoint': endpoint, 'chain_id': chain, 'requested_block': tag,
              'block': block, 'block_after': after,
              'method': 'eth_call', 'params': [dict(CALL), number], 'result': result}
    inspect(bundle)
    if len(json.dumps(bundle, indent=2, sort_keys=True).encode()) + 1 > LIMIT:
        raise ValueError('combined snapshot exceeds 4 MiB')
    return bundle


def inspect(bundle):
    if not isinstance(bundle, dict) or set(bundle) != {
            'schema', 'captured_at', 'endpoint', 'chain_id', 'requested_block',
            'block', 'block_after', 'method', 'params', 'result'}:
        raise ValueError('invalid snapshot fields')
    if bundle['schema'] != 'pinned-zto-snapshot/1' or bundle['chain_id'] != '0x1':
        raise ValueError('unsupported schema or chain')
    rpc.validate_endpoint(bundle['endpoint'])
    stamp = bundle['captured_at']
    if not isinstance(stamp, str) or not stamp.endswith('Z'):
        raise ValueError('capture time must be UTC')
    datetime.datetime.fromisoformat(stamp[:-1] + '+00:00')
    tag = bundle['requested_block']
    if not rpc.block_tag(tag) or tag == 'pending':
        raise ValueError('invalid requested block')
    block = check_block(bundle['block'])
    after = check_block(bundle['block_after'], block['number'])
    if quantity(tag) and tag != block['number']:
        raise ValueError('requested number differs from captured block')
    for field in ('hash', 'parentHash', 'timestamp'):
        if block[field] != after[field]:
            raise ValueError('block identity changed during capture')
    if bundle['method'] != 'eth_call' or bundle['params'] != [CALL, block['number']]:
        raise ValueError('call is not ZTO totalSupply pinned to the captured number')
    if not rpc.hex_data(bundle['result'], 32):
        raise ValueError('invalid ABI uint256 result')
    return {'block_number': str(int(block['number'], 16)), 'block_hash': block['hash'],
            'token': ZTO, 'total_supply_base_units': str(int(bundle['result'], 16)),
            'evidence_limits': 'Provider observation with before/after block identity checks; not cryptographic proof, independent corroboration, or a guarantee of finality. A reorg between reads and back again can escape detection.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    cap = sub.add_parser('capture')
    cap.add_argument('--rpc', default=rpc.DEFAULT_RPC)
    cap.add_argument('--block', default='finalized')
    sub.add_parser('inspect', help='offline; reads snapshot from stdin')
    args = parser.parse_args()
    try:
        if args.command == 'capture':
            result = capture(args.rpc, args.block)
        else:
            raw = sys.stdin.buffer.read(LIMIT + 1)
            if len(raw) > LIMIT:
                raise ValueError('snapshot exceeds 4 MiB')
            result = inspect(rpc.strict_json(raw))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (ValueError, TypeError, KeyError, RuntimeError, OSError, TimeoutError, RecursionError):
        print('pinned-snapshot: invalid snapshot, inconsistent response, or RPC failure', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
