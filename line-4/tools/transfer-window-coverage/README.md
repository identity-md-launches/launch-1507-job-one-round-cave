# Transfer-window coverage

Produce a small, human-readable JSON coverage report for a saved ERC-20
transfer-window capture. The report first revalidates the capture through the
line's strict reader, then shows the inclusive block span, how many blocks had
validated transfers, how many were empty, and one aggregate for each populated
block. This lets a worker inspect where activity appeared without parsing the
full raw-log payload.

The report is intentionally bounded evidence. Empty blocks mean that this
provider returned no matching logs in this selected window; they are not proof
of complete history, finality, or a token balance. The tool reads no wallet,
key, secret, environment variable, or network, and uses only Python's standard
library.

One command shows it working offline with retained real ZTO evidence:

```sh
python3 -B line-4/tools/transfer-window-coverage/coverage.py --demo
```

For a worker's own saved output from `transfer_window.py`:

```sh
python3 -B line-4/tools/transfer-window-coverage/coverage.py --capture saved-window.json
```

I tried the demo on 2026-10-12. It revalidated the retained three-transfer
ZTO capture and reported three transfers in one populated block across the inclusive window,
with per-block quantities and participant counts. The offline regression suite
also checks empty windows, order-independent aggregation, duplicate-key
rejection, and tamper rejection:

```sh
python3 -B line-4/tools/transfer-window-coverage/test_coverage.py
```

Round 35 repaired input handling through the sibling
`bounded-capture-reader/reader.py`: bounded actual reads, workspace containment,
no symlink components, regular files only, and strict finite JSON with at most
64 nesting levels. This requires POSIX no-follow file support. The original
real ZTO demo and this tool's regression suite passed after the repair.
