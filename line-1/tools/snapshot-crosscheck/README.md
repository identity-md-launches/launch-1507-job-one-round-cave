# Snapshot crosscheck

Check a saved, block-pinned ZTO `totalSupply()` snapshot against a second
Ethereum JSON-RPC provider. The tool reads the original snapshot with the
line's strict bounded workspace reader, then requests mainnet chain ID, the
same numbered block, ZTO supply at that number, and the block again from the
second endpoint. It saves all four read observations and recomputes an
explicit agreement or disagreement status. The verifier works offline.
Python 3.10+ standard library only; keep the sibling `rpc-snapshot`,
`pinned-snapshot`, and `snapshot-seal` folders, all ordinary repository files.

From the repository root, one command shows the retained real observation
working **without network access**:

```sh
python3 -B line-1/tools/snapshot-crosscheck/snapshot_crosscheck.py demo
```

It printed `"verified": true`, `"status": "agreement"`, and
`"network_used": false` in this round. On 2026-10-13 at 05:02:39 UTC, the
read-only live `check` command queried `https://eth.drpc.org` using the saved
PublicNode-named finalized snapshot in `snapshot-seal/current-zto.json`.
dRPC reported mainnet, block **26180977** with hash
`0xfffa2f6981064c0c17c939eae510a1d8e9add2b9775e1dab07cf4f2b196dae27`
before and after the call, and ZTO supply
**1000000000000000000000000000** base units. These agreed with the saved
snapshot. The four responses and their capture times are retained in
`example-crosscheck.json` for offline use; they are dated provider observations.

For a fresh read-only check, from the repository root:

```sh
python3 -B line-1/tools/snapshot-crosscheck/snapshot_crosscheck.py check line-1/tools/snapshot-seal/current-zto.json
```

`--rpc` selects a different credential-free HTTPS endpoint. The second
endpoint must differ from the source endpoint. To inspect an evidence file
offline, use `verify SNAPSHOT CROSSCHECK`. Exit 0 means agreement, 2 means a
validated disagreement, and 1 means invalid input or an RPC failure.
`verify` checks exact source bytes, all four methods and parameters, block
identity, ABI result size, stored status, and strict JSON. File reads are
bounded to 4 MiB and confined to this checkout through the existing secure
reader. The original capture and this crosscheck are still provider claims;
agreement does not prove provider independence, honesty, finality or current
state. A transient reorg between reads may escape either reader. No signing,
wallet, payment or transaction submission is involved.

The twelve offline tests passed, including changed chain, block, supply,
second-provider instability, false status, altered source, duplicate JSON,
request tampering, hex letter case, and same-endpoint refusal before any
network call:

```sh
python3 -B line-1/tools/snapshot-crosscheck/test_snapshot_crosscheck.py
```
