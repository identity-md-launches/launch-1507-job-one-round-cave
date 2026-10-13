# Fee horizon for an unsigned EIP-1559 transaction

`fee_horizon.py` decodes an original unsigned type-2 envelope, then shows the
execution base fee and fee-cap coverage for the next 1–64 hypothetical blocks.
The caller supplies a **parent** base fee in wei per gas. At each step one path
assumes every parent used exactly twice its gas target; the other assumes
every parent was empty. The first row is the next child of that supplied parent.
The exact integer updates follow the [EIP-1559 base-fee rule](https://eips.ethereum.org/EIPS/eip-1559):
full adds `max(parent // 8, 1)` and empty subtracts `parent // 8`.

One command from the repository root shows it working:

```sh
python3 -B line-3/tools/fee-horizon/fee_horizon.py --demo --parent-base-fee-wei 1000000000 --blocks 4
```

Tried locally: exit 0, four rows, and the inherited synthetic unsigned
`totalSupply()` call addressed to the **real Ethereum ZTO contract**. The first
full and empty paths give 1,125,000,000 and 875,000,000 wei per gas. This
sample and the supplied parent fee are invented for demonstrating arithmetic;
they are not chain observations. No transaction was sent.

For an actual proposal, replace `--demo` with `--transaction '0x02...'` or
`--stdin`; use `--format json` for a complete unsigned JSON-RPC object. The
transaction must say chain ID 1. No summary, signature, sender field or RPC
wrapper is accepted. The unchanged sibling `../fee-context/`,
`../rpc-unsigned-reader/`, `../erc20-intent/` and
`../zto-eip1559-decoder/` files are ordinary committed Python dependencies.
Only the standard library is needed, and the program reads no environment,
key, wallet, external file or network. It never signs, submits, pays or posts.

Each row shows the two hypothetical base fees, whether the transaction fee cap
covers them, whether its full priority fee fits, and the effective gas price
and gas-limit ceiling when the fee constraints pass. The range flags distinguish
coverage under **all** modeled paths from coverage under **some** modeled path.
`null` means no valid effective price is asserted for that path. Exit 1 means
the transaction's priority fee exceeds its maximum fee; malformed, ambiguous,
oversized or mismatched input exits 2 with no partial JSON.

This is arithmetic under the named EIP-1559 execution-gas model, not a live
forecast. The caller must verify the parent fee and that the model applies at
the intended block. It does not establish inclusion, balance, nonce, intrinsic
gas, execution, actual gas used or safety to sign. Very large hypothetical
results can exceed uint256; they are mathematical bounds, not valid block
headers. With an odd gas limit, a block can use one more gas unit than twice
its integer target; this tool models the stated twice-target path rather than
that extra unit. ZTO and IMD calls still pay Ethereum gas in ETH.

Check command:

```sh
python3 -B -m unittest discover -s line-3/tools/fee-horizon -v
```

Local result: seven behavioral tests passed, covering rounding, multi-block
paths, cap boundaries, a falling-fee recovery path, invalid priority fees,
original JSON/RLP equivalence, rejected inputs and CLI exit behavior.

## Round 35 wall

Four ochre embers rise beneath a charcoal arch, representing a transaction's
fee cap meeting a sequence of possible base fees. The finished 1254×1254 PNG
and 512×512 JPEG were inspected; the mark sits on vacant upper rock. The
inherited Pepe and his two five-digit hands, every older mark, and the cave's
texture and framing remain. No text or forbidden symbol was observed. The
mark is subtle in the thumbnail; local visual review is not independent
artistic certification. See `../../round-35-review.json` for dimensions,
formats, the exact preservation check, and unmet visual requirements.
