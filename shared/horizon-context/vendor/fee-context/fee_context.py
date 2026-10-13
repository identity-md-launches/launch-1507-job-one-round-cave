#!/usr/bin/env python3
"""Explain unsigned EIP-1559 fee caps against an explicitly supplied base fee."""
import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'rpc-unsigned-reader'))
import rpc_reader as reader

MAX_INPUT_CHARS = reader.MAX_JSON_CHARS
UINT256_MAX = 2**256 - 1


def decimal(text):
    """Canonical bounded decimal wei/chain ID, never a float or a boolean."""
    if not isinstance(text, str) or len(text) > 78 or re.fullmatch(r'0|[1-9][0-9]*', text) is None:
        raise ValueError('use a canonical nonnegative decimal integer of at most 256 bits')
    value = int(text)
    if value > UINT256_MAX:
        raise ValueError('decimal integer exceeds uint256')
    return value


def inspect(text, base_fee, context_chain, input_format='rlp'):
    if type(base_fee) is not int or not 0 <= base_fee <= UINT256_MAX:
        raise ValueError('base fee must be a uint256 integer in wei per gas')
    if type(context_chain) is not int or not 1 <= context_chain <= UINT256_MAX:
        raise ValueError('context chain must be a positive uint256 integer')
    if input_format not in ('rlp', 'json'):
        raise ValueError('input format must be rlp or json')
    if not isinstance(text, str) or len(text) > MAX_INPUT_CHARS:
        raise ValueError('transaction text exceeds 512 Ki characters or is not text')
    evidence = (reader.inspect_json(text)['inspection'] if input_format == 'json'
                else reader.intent.interpret(text))
    tx = evidence['transaction']
    for field in ('chainId', 'nonce', 'maxPriorityFeePerGas', 'maxFeePerGas', 'gasLimit', 'value'):
        if not 0 <= int(tx[field]) <= UINT256_MAX:
            raise ValueError(field + ' exceeds uint256')
    if int(tx['chainId']) != context_chain:
        raise ValueError('supplied base-fee context chain does not match transaction chain')
    cap = int(tx['maxFeePerGas'])
    priority = int(tx['maxPriorityFeePerGas'])
    gas = int(tx['gasLimit'])
    value = int(tx['value'])
    violations = []
    if priority > cap:
        violations.append('priority-fee-exceeds-max-fee')
    if base_fee > cap:
        violations.append('base-fee-exceeds-max-fee')
    passes = not violations
    # Negative fee room is never clamped into an apparently valid price.
    tip = min(priority, cap - base_fee) if passes else None
    effective = base_fee + tip if passes else None
    return {
        'schema': 'fee-context/v1', 'inputFormat': input_format,
        'inspection': evidence,
        'context': {'chainId': str(context_chain), 'baseFeePerGasWei': str(base_fee),
                    'source': 'Explicit caller-supplied value; no block or freshness verified.'},
        'fees': {
            'maxFeePerGasWei': str(cap), 'maxPriorityFeePerGasWei': str(priority),
            'maxBaseFeeForFeeCapWei': str(cap),
            'maxBaseFeeForFullPriorityWei': str(cap - priority) if priority <= cap else None,
            'baseFeeShortfallPerGasWei': str(max(0, base_fee - cap)),
            'effectivePriorityFeePerGasWei': None if tip is None else str(tip),
            'effectiveGasPriceWei': None if effective is None else str(effective),
            'fullPriorityAvailable': tip == priority if passes else None,
            'feeCeilingAtGasLimitWei': str(gas * cap),
            'valuePlusFeeCeilingWei': str(value + gas * cap),
            'contextFeeCeilingAtGasLimitWei': None if effective is None else str(gas * effective),
            'contextBurnCeilingAtGasLimitWei': None if effective is None else str(gas * base_fee),
            'contextPriorityCeilingAtGasLimitWei': None if tip is None else str(gas * tip),
            'nativeFeeAsset': 'ETH' if context_chain == 1 else 'Unspecified chain native asset',
        },
        'checkedViolations': violations, 'passesCheckedFeeConstraints': passes,
        'warnings': list(evidence['warnings']) + [
            'EIP-1559 arithmetic only; caller must establish that these rules apply to the supplied context.',
            'Base fee is unverified input, not a live quote or prediction. Token destination does not change the native gas asset.',
            'Ceilings use gasLimit, not gas used; actual gas charges, refunds, execution, balance, nonce, block limits and inclusion are unverified.',
            'No sender is supplied. Value plus fee ceiling is arithmetic, not proof of funds or safety to sign.',
        ],
    }


def main(arguments):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-fee-wei', required=True)
    parser.add_argument('--context-chain', required=True)
    parser.add_argument('--format', choices=('rlp', 'json'), default='rlp')
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--demo', action='store_true')
    source.add_argument('--stdin', action='store_true')
    source.add_argument('--transaction')
    args = parser.parse_args(arguments)
    try:
        base_fee = decimal(args.base_fee_wei)
        chain = decimal(args.context_chain)
        if args.demo:
            text = json.dumps(reader.demo_object()) if args.format == 'json' else reader.D.demo_transaction()
        elif args.stdin:
            text = sys.stdin.read(MAX_INPUT_CHARS + 1)
            if len(text) > MAX_INPUT_CHARS:
                raise ValueError('transaction text exceeds 512 Ki characters')
            if args.format == 'rlp':
                text = text.removesuffix('\n').removesuffix('\r')
        else:
            text = args.transaction
        result = inspect(text, base_fee, chain, args.format)
    except (ValueError, UnicodeError) as error:
        print('error: ' + str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result['passesCheckedFeeConstraints'] else 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
