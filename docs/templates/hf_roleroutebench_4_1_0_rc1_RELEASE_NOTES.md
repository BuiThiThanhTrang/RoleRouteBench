# RoleRouteBench 4.1.0-rc.1 release notes

This candidate updates the two rebalanced Track B domains and refreshes the
reported results for all four domains. It does not upload data or alter the
published Hugging Face repository by itself.

## Dataset changes

- Formal Proof: 30 tasks → 40 tasks; new source mix, Pythagoras-Prover-4B,
  budget 12, and independent proof auditing.
- Structured Data: SpreadsheetBench20 → Table-QA40; 22 WikiTableQuestions,
  14 HiTab, and 4 TableBench tasks with a typed answer/evidence contract.
- Database and Code Debugging: packet banks unchanged; result trajectories
  refreshed on the current source revision.
- Track B total: 82 → 112 tasks.
- Legacy synthetic Track A: unchanged and retained for backward compatibility.
  This LLM-generated simulated state bank is not the unreleased empirical Track A
  V1. Empirical Track A V2 is built but excluded while labeling and review are
  incomplete.

## Result update

The candidate publishes per-domain primary endpoints and an explicitly
heterogeneous 112-task aggregate for the four dynamic routers and the matched
fixed/predefined baseline. It also publishes partial single-agent coverage
without fabricating a Formal40 value.

## Safety and reproducibility

- Packet private/evaluator directories are withheld by default.
- Raw provider outputs, local experiment archives, credentials, and local paths
  are not part of the Hub candidate.
- Reference trajectories use the exact selected JEV episodes from the canonical
  run manifests; no best-of selection is introduced.
- Formal retry selection follows the frozen retry2/infra-retry3 policy recorded
  in `runs/formal_proof/official_run_manifest.json`.

## Required before publication

1. Replace code and dataset revision placeholders.
2. Decide the final semantic version and Hub commit message.
3. Review source notices, especially TableBench revision/license text.
4. Confirm whether evaluator-private artifacts remain withheld.
5. Confirm that Formal40 and Structured40 are described as human-review pending.
6. Run the clean candidate validator and inspect the generated checksum manifest.

