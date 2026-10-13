# Bounded capture reader

Load a public saved ERC-20 transfer observation without reading outside the
workspace or allocating an unbounded input buffer. This standard-library
Python tool repairs the activity, coverage and receipt readers identified in
the Gathering 14 report. Those three tools now use this shared loader; their
report formats and raw-log validation remain unchanged.

From the repository root, one command works offline:

```sh
python3 -B line-4/tools/bounded-capture-reader/reader.py --demo
```

Tried on 2026-10-13: it revalidated the retained real PublicNode ZTO capture,
blocks 26177298–26177309, and reported three transfers. The activity, coverage
and receipt demos also passed. This is dated chain evidence, not a fresh RPC
observation. No network call, installation, wallet, key or environment lookup
is needed. Keep the sibling `transfer-crosscheck` and `erc20-transfer-window`
folders when copying this tool; all runtime dependencies are ordinary Python
files already in this repository.

To inspect a public capture you selected inside this workspace:

```sh
python3 -B line-4/tools/bounded-capture-reader/reader.py --capture saved-window.json
```

The shared `read_capture(path, max_bytes=16777216)` function accepts a regular
file, bounds its actual read to limit + 1 bytes, and rejects excessive size
before JSON parsing. It refuses outside paths, `..` traversal, symlinks in
any path component, directories and FIFOs. Directory-relative no-follow
opens prevent symlink replacement between checking and opening. It uses
POSIX file flags and fails closed on unsupported platforms. The installation
root is trusted; this is not a sandbox against processes that can rename
already-open directories, make hard links, or rewrite workspace contents.
Do not select files containing secrets.

Strict UTF-8 JSON parsing refuses duplicate keys, non-finite numbers (including
exponent overflow), malformed input and nesting above 64 levels. The parser
accepts JSON values; the CLI and consumer tools separately require a valid
capture and rebuild its events from raw logs. These checks do not establish
provider honesty, chain completeness, current balances or finality.

Tests:

```sh
python3 -B line-4/tools/bounded-capture-reader/test_reader.py
```

All 15 focused tests passed, including exact-size limits, a simulated file
growing after stat, symlink components, traversal rejected before open, FIFO
refusal with a timeout, malformed/deep JSON, each consumer's restrictions,
and real ZTO demos. The three repaired consumer suites add 14 passing tests
(29 total). The initial deep-nesting test showed that the runtime accepted
2,000 levels; an explicit pre-parse 64-level bound fixed that issue. Fixtures
are created only beneath `test/scratch/` and no network is used in tests.
