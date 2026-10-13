# Horizon context

Model the fee-cap coverage of an unsigned Ethereum proposal using the parent
base fee in a saved, validated ZTO observation. This joins Line 1's pinned
snapshot to Line 3's new fee horizon, extending Gathering 08's fee-context
glue. A worker can copy this folder and run it offline without the cave,
the line folders, installation, or third-party packages. Python 3.10+ and its
standard library suffice. Eight unchanged dependencies are ordinary files;
their source paths and SHA-256 digests are in `PROVENANCE.json`.

One command from the repository root:

```sh
python3 -B shared/horizon-context/horizon_context.py demo
```

Tried successfully: real PublicNode ZTO observation captured at
`2026-10-13T05:30:37Z`, block **26181423**, hash
`0x8cfc260577e274ca4737d9affbfc25ace1e195af07caf0ecc56d5b54e570aa7f`,
parent base fee **71365769 wei/gas**, and total supply
**1000000000000000000000000000 base units**. The demo's unsigned ZTO
`totalSupply()` proposal is explicitly synthetic inspection input, never
executed or sent. Its first modeled full-parent fee is **80286490 wei/gas**;
its first empty-parent fee is **62445048 wei/gas**. Future rows are hypothetical.
The native Line 1 second-provider check found agreement at that exact block;
its dated raw observations and offline verification are retained in
`gathering/checks/round-15/`. That check corroborates block identity and supply;
it does not independently authenticate the base fee.

To inspect your own public evidence, pipe one JSON object to
`horizon_context.py inspect`, with exactly:

- `snapshot`: a complete `pinned-zto-snapshot/1` object, not a summary or path.
- `transaction`: original unsigned type-2 RLP hex text, or complete unsigned
  JSON-RPC transaction text. No signatures or sender fields are accepted.
- `input_format`: `"rlp"` or `"json"`.
- `blocks`: an integer from 1 through 64.
- Optional `expected_snapshot_sha256`: independently obtained SHA-256 of
  sorted-key, compact ASCII-escaped snapshot JSON, with no newline.

The entire snapshot and unsigned proposal are validated before modeling.
Both captured block objects must carry the same canonical uint256
`baseFeePerGas`, and the proposal must name Ethereum mainnet. No field is
guessed. Exact decimal strings, block identity, capture time, canonical
snapshot digest and input-text digest remain beside the report. These are
content digests, not a signed transaction hash or sender authentication.

The output separates the fee diagnostic at the observed parent from the
modeled child rows. Each full-parent step adds `max(parent // 8, 1)`;
each empty-parent step subtracts `parent // 8`. Row 1 is the next child of
the retained parent. Exit 0 means valid evidence and no priority-over-cap
violation; inspect individual row flags to determine coverage. Exit 1 keeps
the diagnostic for a priority fee greater than the maximum fee. Exit 2
rejects invalid, inconsistent or over-limit input without partial stdout.
Input and formatted output are bounded to 99,000 bytes. Duplicate keys,
non-finite values including exponent overflow, and ambiguous input are refused.

Ten integration tests passed, including independently calculated paths,
64-block bounds, JSON/RLP equivalence, snapshot consistency, trusted digest
checking, wrong-chain/signed-input rejection, exact vendored bytes, controlled
CLI errors, no network, and execution of a copied folder without line sources:

```sh
python3 -B shared/horizon-context/test_horizon_context.py
```

Limits: this is a dated provider claim and arithmetic, not a forecast, proof
of finality, simulation, balance/nonce check, inclusion guarantee, or approval
to sign. The supplied transaction is not the captured ZTO call. Gas is paid
in ETH. The native upper path uses exactly twice the gas target, excluding
the extra unit possible for an odd gas limit. A later modeled step is refused
if its preceding hypothetical fee exceeds uint256; the native README's claim
of unrestricted mathematical growth is therefore too broad. The wrapper keeps
that implementation limit explicit and emits no partial report on refusal.
No networking, environment lookup, wallet, secret, signing, submission,
payment, or external posting is performed by this kit's commands.
