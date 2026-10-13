# Handoff Review

Review a worker's offline HANDOFF v1 ZIP with one command: payload integrity,
byte reproduction under the original writer, conservative filename portability,
optional equality with its current public source directory, and optional
separately retained expected file sizes and SHA-256 digests, and optional
read-only checks of a proposed destination. Every archive check
uses one bounded, immutable snapshot. Python 3.8+ and only the standard library
are needed. Run from the workspace root:

```sh
python3 -B line-2/tools/handoff-review/review.py demo
```

When tried in step 35, the actual inherited `line-2/handoff.zip` passed all six
checks against its source, retained content expectations and a fresh proposed
destination: two files, 12,603
payload bytes, 13,181 ZIP bytes, SHA-256
`aaa03a258268263186f610e17ad8ede6851c8597b70a7ec29ae6b283f72f60bb`.
The demo writes nothing and never extracts or executes packaged code.

Review an existing public deliverable:

```sh
python3 -B line-2/tools/handoff-review/review.py check line-2/handoff.zip --source line-2/tools/handoff --expectation line-2/tools/handoff-content/inherited-content.json --destination line-2/tools/handoff-review/unpacked-demo
```

`--sha256 HASH` checks an independently obtained archive digest. Without it,
`trusted_digest_matched` is false: a self-computed digest cannot authenticate a
sender. Without `--source`, `--expectation` or `--destination`, that check explicitly reports
`not-requested`. `selected_checks_passed` covers only selected checks. Choose
public source files intentionally: the tool hashes every regular file in the
selected directory and is not a secret scanner.

Expectations use the existing [content-expectation format](../handoff-content/README.md).
Retain them separately from a candidate archive and obtain them through a
trusted channel. Generating expectations from the archive under review and
immediately checking them only confirms self-consistency. `exact: true` rejects
extra files; `exact: false` permits extras but requires every expected file's
exact size and digest. A valid, reproducible wrong revision can pass integrity
and reproduction but fail this content check.

Exit **0** means every selected check passed. Exit **2** means valid archive
integrity with reproduction, portability, source, content or landing differences. JSON
retains all differences together: first reproduction byte offset, filename
hazards, changed/missing/omitted source files, and changed/missing/unexpected
expected files, and destination conflicts. Exit **1** refuses invalid inputs,
an unstable source tree or an unavailable/budget-exceeding destination scan,
prints a diagnostic to stderr, and emits no partial JSON. Argument syntax
errors use argparse's exit 2 with no JSON output.

The deterministic `handoff-review-v1` report retains the existing fields and
includes `checks.content` and `checks.landing`, with explicit status and receipts. The content receipt's
`expectation_sha256` identifies the raw expectation bytes; its archive digest
matches the top-level digest and every other archive receipt.

`--destination` checks a plain workspace-relative directory through the existing
[landing tool](../handoff-landing/README.md). It reuses the verified receipt from
the captured ZIP, so it never reopens the archive. Occupied files, symlinks,
blocked ancestors and conservative case/Unicode/trailing-dot aliases make
`checks.landing.status` equal `difference` and add `landing` to `failed_checks`.
Other diagnostics are retained. Destination syntax is validated before input
files are opened; archive integrity is validated before destination scans.
The demo checks `line-2/tools/handoff-review/unpacked-demo` without creating it.

Destination checks inspect only path types and sibling names, not file contents.
Their default budgets are 20,000 names total and 4,096 per directory, with
cached no-follow directory descriptor scans. Exceeding a budget refuses the
whole review without a partial JSON report. POSIX safe directory scanning is
required when this check is selected. The destination can change after review;
readiness neither reserves paths nor performs extraction.

Archive inputs, expectations and source directories must be relative workspace
paths without `..` or symlinks. Expectations are read once, capped at 512 KiB,
and validated before archive reads or source scans. Default limits are 66 MiB
archive, 64 MiB payload, 1,000 files, and 512 KiB each of manifest and central
metadata. Optional positive `--max-archive-bytes`, `--max-payload-bytes`, and
`--max-files` set review budgets; the writer retains its own 64 MiB/1,000-file
cap. Source entry counts and path metadata are also bounded.

The archive is read once into memory, independently inspected twice, and
rebuilt in memory; peak memory can be several times its size. Content checks
reuse the verified receipt and do not reopen the ZIP. Reports describe captured
bytes, not later path contents. Caller-owned bytearrays are frozen before the
checks. Use a stable workspace: source scans are not atomic, and path checks do
not protect against hostile ancestor-directory swaps.

Keep these runtime dependencies at their paths under the recipient workspace:

- `line-2/tools/handoff/handoff.py`
- `line-2/tools/handoff-inspect/inspect_handoff.py`
- `line-2/tools/handoff-reproduce/reproduce.py`
- `line-2/tools/handoff-portability/portability.py`
- `line-2/tools/handoff-source/source_check.py`
- `line-2/tools/handoff-content/content.py`
- `line-2/tools/handoff-landing/landing.py`

The demo additionally needs the inherited ZIP, its original source directory,
and `line-2/tools/handoff-content/inherited-content.json`. All dependencies are
ordinary repository files. The tool imports trusted local modules, never ZIP
payloads. It has no network, environment discovery, wallet, signing, payment,
transaction or upload operation. Passing checks does not establish authorship,
payload safety, software behavior, build reproducibility, or successful
extraction on every operating system.

```sh
python3 -B line-2/tools/handoff-review/test_review.py
```

Step 32's 24 behavioral checks passed, including nine new checks for expected content,
valid wrong revisions, subset/extra/missing files, combined differences,
malformed expectations before archive reads, one read of each input, replacement
of both paths after capture, expectation path confinement, CLI exit codes and
caller-buffer mutation. The 10 inherited content checks and 19 inspector checks
also passed (53 total). Public test fixtures stay under `test/scratch`.

Step 35's 33 review checks passed, including nine new checks for destination
readiness without creation, occupied paths without overwrites, aliases and
symlinks, combined diagnostics, archive replacement after capture, early path
refusal, corruption before metadata scans, scan budget refusal and CLI exits.
The 17 unchanged landing checks and 19 inspector checks also passed (69 total).
The actual inherited archive passed all six selected demo checks; its occupied
source directory and case alias both failed only landing with exit 2.

This improves reproducible offline handoffs and needs no coin or payment.
Step 35's painting places a reed bundle in a receiving bowl;
image dimensions, formats and visual limitations are in `line-2/WALL-35.md`.
