#!/usr/bin/env python3
"""Offline interpretation of standard ERC-20 calldata in unsigned type-2 envelopes."""
import json
from pathlib import Path
import sys

# Import only the inherited decoder beside this workspace tool. No input files,
# environment, network, wallet interfaces or transaction submission are used.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'zto-eip1559-decoder'))
import tx_decode as decoder

IMD = '0xd34a99bc0f67ae1bbd63c660e6d0b0dd03e263b7'
UINT256_MAX = 2**256 - 1
METHODS = {
    '18160ddd': ('totalSupply', []),
    '70a08231': ('balanceOf', [('account', 'address')]),
    'dd62ed3e': ('allowance', [('owner', 'address'), ('spender', 'address')]),
    'a9059cbb': ('transfer', [('recipient', 'address'), ('amountBaseUnits', 'uint256')]),
    '095ea7b3': ('approve', [('spender', 'address'), ('amountBaseUnits', 'uint256')]),
    '23b872dd': ('transferFrom', [('from', 'address'), ('recipient', 'address'),
                                ('amountBaseUnits', 'uint256')]),
}


def interpret(transaction_hex):
    """Return structural summary, exact decimal quantities and cautious intent.

    ABI interpretation is a selector pattern match, never evidence of contract
    execution or ownership. No decimals, sender or chain state are inferred.
    """
    tx = decoder.decode(transaction_hex)
    warnings = [
        'Offline inspection only: no chain state, simulation, sender or contract behavior verified.',
        'Selectors can collide; an ABI pattern match does not prove ERC-20 behavior.',
    ]
    # Decimal strings preserve large exact quantities in JavaScript consumers.
    summary = {key: str(value) if type(value) is int else value
               for key, value in tx.items()}
    gas_cap = tx['gasLimit'] * tx['maxFeePerGas']
    result = {
        'transaction': summary,
        'destinationLabel': None,
        'feeBudget': {
            'gasFeeCapWei': str(gas_cap),
            'valuePlusGasFeeCapWei': str(gas_cap + tx['value']),
            'meaning': 'Gas limit times maximum fee per gas; excludes token transfers. Not an estimate.',
        },
        'calldata': {'status': 'unrecognized', 'selector': tx['calldataSelector']},
        'warnings': warnings,
    }
    if tx['chainId'] == 1:
        result['destinationLabel'] = {decoder.ZTO: 'ZTO', IMD: 'IMD'}.get(tx['to'])
    else:
        warnings.append('ZTO and IMD labels apply only to the supplied Ethereum chain-1 addresses.')
    if tx['maxPriorityFeePerGas'] > tx['maxFeePerGas']:
        warnings.append('Priority fee exceeds maximum fee per gas.')
    for name in ('chainId', 'nonce', 'maxPriorityFeePerGas', 'maxFeePerGas', 'gasLimit', 'value'):
        if tx[name] > UINT256_MAX:
            warnings.append(f'{name} exceeds 256 bits; structural decoding is not protocol validity.')
    if tx['to'] is None:
        result['calldata']['status'] = 'contract-creation'
        return result
    data = bytes.fromhex(tx['data'][2:])
    if not data:
        result['calldata']['status'] = 'empty'
        return result
    selector = data[:4].hex()
    if len(data) < 4 or selector not in METHODS:
        return result
    method, fields = METHODS[selector]
    call = result['calldata']
    call.update({'status': 'malformed-known-selector', 'candidateMethod': method})
    if len(data) != 4 + 32 * len(fields):
        call['reason'] = 'Expected exact static ABI length; trailing bytes are not accepted.'
        return result
    arguments = {}
    for index, (name, kind) in enumerate(fields):
        word = data[4 + 32 * index:36 + 32 * index]
        if kind == 'address':
            if word[:12] != bytes(12):
                call['reason'] = f'{name} has nonzero address padding.'
                return result
            arguments[name] = '0x' + word[12:].hex()
        else:
            arguments[name] = str(int.from_bytes(word, 'big'))
    call.update({'status': 'abi-pattern-match', 'arguments': arguments})
    if 'amountBaseUnits' in arguments:
        call['amountUnit'] = 'raw token base units; decimals are unknown'
    if method == 'approve':
        amount = int(arguments['amountBaseUnits'])
        call['approvalKind'] = ('zero' if amount == 0 else
                                'maximum-uint256' if amount == UINT256_MAX else 'finite')
        warnings.append('Approval calldata sets a spender allowance under standard ERC-20 semantics; inspect the spender.')
        if amount == UINT256_MAX:
            warnings.append('Maximum uint256 approval amount: potentially unlimited spending authority.')
    if method == 'transferFrom':
        warnings.append('transferFrom relies on existing allowance and balances, neither checked here.')
    if tx['value']:
        warnings.append('Native ETH value accompanies a standard ERC-20 selector; payable behavior is unverified.')
    return result


def main(arguments):
    if arguments == ['--demo']:
        # Reuse the inherited unsigned zero-value call to the real ZTO address.
        transaction = decoder.demo_transaction()
    elif len(arguments) == 1:
        transaction = arguments[0]
    else:
        print('usage: intent.py --demo | 0x02...', file=sys.stderr)
        return 2
    print(json.dumps(interpret(transaction), indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main(sys.argv[1:]))
    except ValueError as error:
        print(f'error: {error}', file=sys.stderr)
        raise SystemExit(2) from None
