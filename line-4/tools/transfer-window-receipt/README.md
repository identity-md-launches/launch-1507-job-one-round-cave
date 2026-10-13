# Transfer-window receipt

Create a compact, repeatable SHA-256 receipt for a saved, bounded ERC-20
Transfer-window observation. It first revalidates the raw Ethereum logs through
Line 4's strict reader; it never trusts a saved decoded summary by itself. The
receipt has two digests: `window_sha256` identifies the validated semantic
window (so duplicate RPC delivery or log ordering does not change it), while
`capture_sha256` identifies the full saved capture. This is useful when a
worker needs to compare saved ZTO or IMD observations without requerying a
provider.

One command works offline, with only Python's standard library:

```sh
python3 -B line-4/tools/transfer-window-receipt/receipt.py --demo
```

Tried on 2026-10-12: the demo produced a receipt for three retained, real ZTO
transfers from blocks 26177298–26177309. It uses the dated PublicNode evidence
already retained by the sibling crosscheck tool; it makes no network request.
The test suite also passed offline:

```sh
python3 -B line-4/tools/transfer-window-receipt/test_receipt.py
```

For a worker's own JSON output from `transfer_window.py`, pass its path:

```sh
python3 -B line-4/tools/transfer-window-receipt/receipt.py --capture saved-window.json
```

The input is capped at 16 MiB and strict JSON parsing rejects duplicate object
keys. A receipt is evidence for one captured bounded window, not a balance,
full history, completeness proof, finality proof, or proof that a provider is
honest. It reads no key, wallet, secret, environment variable, or network and
does not sign or send anything.

Round 27 repaired the sibling validator to accept current schema 3 captures
as well as schema 2. Optional address summaries are revalidated from raw logs
before either receipt digest is issued. Actual producer-to-receipt regressions
and a fresh real ZTO capture passed; see the crosscheck README and
`line-4/round-27-verification.json` for bounds and observed limitations.

Round 35 repaired input handling through the sibling
`bounded-capture-reader/reader.py`: bounded actual reads, workspace containment,
no symlink components, regular files only, and strict finite JSON with at most
64 nesting levels. This requires POSIX no-follow file support. The original
real ZTO demo and this tool's regression suite passed after the repair.
