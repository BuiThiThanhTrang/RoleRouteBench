# Structured Data update: difficulty rebalancing and trajectory diversity

This is a dataset-card/changelog fragment for the upcoming combined RoleRouteBench
release. The global release number and final Hub paths are assigned during assembly.
The local component is not a standalone upload folder.

## What changed

The Structured Data domain now includes a versioned cohort of40 normalized Table QA
tasks:22 WikiTableQuestions,14 HiTab, and4 TableBench examples. This replaces the
SpreadsheetBench task family for the new revision; it is not a nested20-example
extension of the old cohort. The historical release remains separately identified.

The update targets tasks on which a small executor can make observable progress
and follow different workflows: direct answers, header resolution, evidence
selection, numerical analysis, verification and recovery. It also includes a
minimal fix that restores a reread inspection when its cached artifact has left
the visible state. Existing artifacts are reused; an already-visible repeated
read retains no-progress semantics.

This release does not require dynamic routing to outperform a predefined workflow.
It provides a common task/tool/visibility contract to study end-to-end behavior.

## Experimental protocol

The six reported methods use the same40-task cohort, Qwen3.5-9B executor,12 attempted
role calls, one tool call per executor turn, and a16,384-token response cap.
Executor requests use temperature0. Dynamic methods receive all seven specialist
roles and STOP without a rejection guard. Single-agent receives the union of tools;
the predefined baseline uses an explicit sequence with terminal short circuit.

The source/config fingerprints of historical runs are preserved. The four dynamic
routers share241 tracked files with matching hashes. Baseline/current source
snapshots differ; recorded tool/state replay confirms equivalence for240 episodes,
2,084 states and1,616 tool calls. Replay is not fresh model generation or a claim
of byte-identical engine versions across every run.

## Results

| Method | Public pass + STOP | End-task answer pass | STOP F1 | Recovery@PublicFailure |
|---|---:|---:|---:|---:|
| JEV |21/40 |23/40 |90.5% |9/23 (39.1%) |
| SOL |24/40 |27/40 |91.7% |11/24 (45.8%) |
| DREX |28/40 |28/40 |85.7% |13/23 (56.5%) |
| PPLX |18/40 |20/40 |65.4% |1/17 (5.9%) |
| Single-agent |26/40 |25/40 |89.4% |13/23 (56.5%) |
| Predefined |28/40 |29/40 |78.8% |12/23 (52.2%) |

Public pass requires fresh public verification and router STOP. It can still be
wrong against the trusted answer. End-task pass checks the fresh final answer
against the evaluator-only gold, independently of STOP. These columns overlap;
they must not be added. The joint pass counts are19/22/27/17/21/26 respectively.

STOP F1 treats a state with a fresh gold-correct answer and passed public verification
as ready: STOP is positive; premature STOP is FP; continuing at a ready state is FN.
The reserved zero-budget STOP opportunity is included. This is evaluator-derived
termination evaluation, not human multi-class action accuracy.

Recovery counts episodes with a public error or action rejection while no fresh
correct answer exists and budget remains. Success means a fresh correct final
answer; STOP is not required. Opportunity sets vary by policy and the metric is
observational system recovery, not a causal estimate of the router alone.

## Diversity and limits

All seven roles are used by each dynamic router. Distinct dispatched-role sequences
number27/32/31/24 for JEV/SOL/DREX/PPLX. Diversity alone does not establish productive
coordination. A direct solution may be appropriate, and a longer trajectory may
reflect repeated unsuccessful operations.

All40 reference paths pass through public tools and a trusted evaluator.20 automated
tests pass in the prepared payload. These checks establish executable tasks and
contracts, not universal backbone solvability or completed human review.
Results come from one full run per method and small recovery subsets; no stable
leaderboard ranking or statistical dominance is claimed.

Gold and upstream answer formulas remain evaluator-only at runtime. Public verification
checks public evidence and the executor's stated issue; it is not a gold oracle.
Local preparation archives contain evaluator files and raw logs for audit. Their
publication policy must be applied during final assembly, before uploading.

## Sources, normalization and notices

- WikiTableQuestions: Git7d455a5a707b96341ef72aff9428749d443d8aa9; CC-BY-SA-4.0.
- HiTab: Gitd179602662b490249baf068a76fbe4137029126e; Computational Use of Data Agreement v1.0.
- TableBench TQA_test: exact cached-file SHA-256 retained; source metadata declares
  Apache-2.0. The upstream dataset revision and license text require final provenance review.

The component records source splits, hashes, original/adapted questions and per-source
license notices.16 question strings differ from upstream through typo, scope,
order or unit clarification. Hierarchical headers and answers are normalized.
These adapted-cohort scores are not official scores for the source benchmarks.
Do not replace source-specific license notices with a blanket new data license.

## Review status and next revisions

Human packet review and routing labels remain pending. Runtime verification does
not promote them to human-verified. No labels are transferred from historical
Track A states by packet ID. The40 examples are a full curated cohort, not a
new sealed test set; upstream test splits do not establish absence of model exposure.

This revision establishes a versioned rebalancing/diversification milestone.
Later revisions may add samples and sources after checking solvability/progress,
workflow coverage, deduplication, trusted evaluation and provenance. No fixed future
sample quota, source list or publication date is promised. Keep previous cohorts,
denominators, protocols and results identifiable; changes to tools or visibility
require an explicitly versioned environment and parity checks.
