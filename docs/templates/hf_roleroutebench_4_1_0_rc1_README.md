---
license: other
language:
- en
pretty_name: "RoleRouteBench: Dynamic Multi-Agent Routing Across Reproducible Tool Environments"
annotations_creators:
- expert-generated
multilinguality:
- monolingual
source_datasets:
- extended
task_categories:
- text-classification
size_categories:
- 1K<n<10K
tags:
- multi-agent
- agent-routing
- llm-routing
- orchestration
- dynamic-routing
- tool-use
- benchmark
- code-debugging
- formal-proof
- database-migration
- table-question-answering
configs:
- config_name: router_state
  default: true
  data_files:
  - split: development
    path: data/router_state/development.parquet
  - split: validation
    path: data/router_state/validation.parquet
  - split: test
    path: data/router_state/test.parquet
- config_name: router_structured
  data_files:
  - split: development
    path: data/router_structured/development.parquet
  - split: validation
    path: data/router_structured/validation.parquet
  - split: test
    path: data/router_structured/test.parquet
- config_name: router_raw_development
  data_files:
  - split: development
    path: data/router_raw_development/development.parquet
- config_name: track_a_labels
  data_files:
  - split: development
    path: data/track_a_labels/development.parquet
  - split: validation
    path: data/track_a_labels/validation.parquet
  - split: test
    path: data/track_a_labels/test.parquet
- config_name: agent_catalog
  data_files:
  - split: train
    path: data/agent_catalog/train.parquet
- config_name: provenance
  data_files:
  - split: development
    path: data/provenance/development.parquet
  - split: validation
    path: data/provenance/validation.parquet
  - split: test
    path: data/provenance/test.parquet
- config_name: human_review
  data_files:
  - split: development
    path: data/human_review/development.parquet
  - split: validation
    path: data/human_review/validation.parquet
  - split: test
    path: data/human_review/test.parquet
- config_name: track_b_tasks
  data_files:
  - split: full
    path: data/track_b_tasks/full.parquet
- config_name: track_b_agents
  data_files:
  - split: full
    path: data/track_b_agents/full.parquet
- config_name: track_b_trajectories
  data_files:
  - split: full
    path: data/track_b_trajectories/full.parquet
- config_name: track_b_results
  data_files:
  - split: full
    path: data/track_b_results/full.parquet
- config_name: track_b_runs
  data_files:
  - split: full
    path: data/track_b_runs/full.parquet
- config_name: track_b_provenance
  data_files:
  - split: full
    path: data/track_b_provenance/full.parquet
- config_name: benchmark_results
  data_files:
  - split: full
    path: data/benchmark_results/full.parquet
---

# RoleRouteBench

> Release candidate `4.1.0-rc.1`. This update refreshes Track B while retaining
> the published legacy synthetic Track A unchanged for backward compatibility.

**Dataset DOI:** [`10.57967/hf/11430`](https://doi.org/10.57967/hf/11430)  
**Code repository:** [`BuiThiThanhTrang/RoleRouteBench`](https://github.com/BuiThiThanhTrang/RoleRouteBench)

**Code revision:** [`e551ae9`](https://github.com/BuiThiThanhTrang/RoleRouteBench/commit/e551ae9d754513be68661cdda55f1a9bf6ec7413)

RoleRouteBench evaluates a decision model that repeatedly observes a public task
state, selects one specialist role or `STOP`, and receives the observable
consequence of that action. It separates one-step routing evaluation (Track A)
from closed-loop task execution (Track B).

## Authors and contributors

- Trang Bui — dataset creator, benchmark and environment designer, release
  maintainer, and author of the current four-domain beta release.
- Tran Ngoc Cam Nguyen — planned domain lead for Multi-hop Knowledge and
  Document/Media.

## What changed in 4.1.0-rc.1

- The legacy synthetic Track A remains byte-for-byte inherited from the published
  beta.2 release for backward compatibility. It was generated through LLM
  simulation and is not the unreleased empirical Track A V1. The rebuilt
  997-state empirical Track A V2 is intentionally excluded from this update.
  A follow-up Track A update is planned within the next few days, after its
  results table finishes running and the outputs are verified.
- Track B now contains 112 tasks: 12 database migration, 20 code debugging,
  40 formal proof, and 40 structured-data/Table-QA tasks.
- Formal Proof replaces the 30-task Goedel cohort with Formal40: 8 MiniF2F,
  20 LeanDojo, 10 APRIL, and 2 Putnam tasks using Pythagoras-Prover-4B,
  budget 12, and independent Lean/kernel auditing.
- Structured Data replaces SpreadsheetBench20 with Structured40: 22
  WikiTableQuestions, 14 HiTab, and 4 TableBench tasks using Qwen3.5-9B,
  budget 12, one tool call per executor turn, and evaluator-only trusted answers.
- Database and Code Debugging results use the reruns produced on the current
  source revision on 2026-11-23.
- A new `benchmark_results` configuration reports matched multi-method results.

## Release scope

| Track | Status | Unit | Split policy |
|---|---|---|---|
| Legacy synthetic Track A | Unchanged from beta.2 | LLM-simulated isolated next-action decision | Existing development/validation/test |
| Empirical Track A V1 | Not included | Recorded live routing states | Unreleased internal track |
| Empirical Track A V2 | Follow-up pending | Rebuilt 997-state multi-router bank | Planned within a few days after the results table finishes and is verified |
| Track B | Updated | Full closed-loop trajectory | One transparent `full` split |
| Track C | Not included | Checkpointed recovery | Deferred |

### Track B task environments

| Domain | Tasks | Executor | Budget | Current review status |
|---|---:|---|---:|---|
| Database migration and integrity | 12 | Qwen3.5-9B | 8 | Packet review inherited; routing labels pending |
| Code debugging | 20 | Gemini 2.5 Flash | 8 | Packet review inherited; routing labels pending |
| Formal proof | 40 | Pythagoras-Prover-4B | 12 | Runtime verified; human packet review pending |
| Structured data / Table QA | 40 | Qwen3.5-9B | 12 | Runtime verified; human packet review pending |

The reference trajectory tables contain one selected JEV run per task. The
`benchmark_results` table additionally reports SOL, DREX, PPLX and matched
baselines without pretending that fixed or single-agent systems share the same
router decision interface.

## Current results

Each domain retains its primary endpoint:

- Database and Code Debugging: public pass with `STOP`, or an independently
  correct final task result without `STOP` (`P + E`).
- Formal Proof: workflow success **and** independent proof audit pass.
- Structured Data: trusted-gold end-task answer pass, independently of `STOP`.

Because these endpoints differ, the aggregate describes release coverage and
must not be treated as a homogeneous statistical leaderboard.

| Method | Database / 12 | Code / 20 | Formal / 40 | Structured / 40 | Aggregate / 112 |
|---|---:|---:|---:|---:|---:|
| SOL | 10 | 15 | 13 | 27 | **65 (58.04%)** |
| DREX 9B | 9 | 11 | 10 | 28 | **58 (51.79%)** |
| JEV | 9 | 12 | 12 | 23 | **56 (50.00%)** |
| PPLX Decider Flash | 8 | 14 | 13 | 20 | **55 (49.11%)** |
| Single agent | 9 | 13 |  | 25 |  |
| Fixed workflow | 7 | 14 | 11 | 29 | **61 (54.46%)** |

Blank cells mean that no matched result is available. In particular, there is
no matched single-agent Formal40 run, so no artificial 112-task single-agent
aggregate is reported. One Code single-agent final audit is `UNAVAILABLE` and
remains visible in the result metadata.

These are one-run measurements on small cohorts. They do not establish stable
rankings, statistical dominance, or causal usefulness of a role.

### Database migration and integrity

On the 12-task Database cohort, SOL reaches 10 `P + E` passes; DREX, JEV and
single agent reach 9; PPLX reaches 8; and the fixed workflow reaches 7. The
differences correspond to only one to three tasks, so this run does not support
a stable ranking. The endpoint intentionally credits an independently correct
final database even when the router did not emit `STOP`; public stopping behavior
and end-task correctness should therefore be inspected separately.

The dynamic routers also follow visibly different strategies. JEV and SOL
frequently combine schema inspection with migration authoring and transactional
execution; DREX concentrates more heavily on author/executor transitions; PPLX
uses the data-profiler branch more often in this run. These role counts describe
the observed trajectories, not the causal usefulness of a role. The fixed
workflow uses fewer executor calls overall but achieves fewer `P + E` passes;
with only 12 tasks and one run per method, this is not a general efficiency or
accuracy claim.

### Code debugging

On the 20-task Code cohort, SOL reaches 15 `P + E` passes, PPLX and the fixed
workflow reach 14, single agent reaches 13, JEV reaches 12, and DREX reaches 11.
The gap between STOP-gated public completion and independent final evaluation is
especially important in this domain: a run may exhaust its routing budget or
omit `STOP` while still leaving a correct patch. For that reason, the table uses
the declared `P + E` endpoint and preserves stopping diagnostics separately.

The trajectories again show different policies rather than one shared pipeline.
JEV emphasizes patch authoring and regression verification, SOL combines patch
authoring with diagnosis and reproduction, DREX repeatedly continues patch and
verification branches, and PPLX calls the diagnostician most often in this run.
The fixed workflow reaches 14/20 with a literal predefined sequence and terminal
short-circuit; it is not an intelligent gated pipeline. One unavailable
single-agent final audit remains explicit instead of being imputed. Provider
behavior, executor generation, routing, tool outcomes and termination all affect
these results.

### Formal proof

Formal40 contains 8 MiniF2F, 20 LeanDojo, 10 APRIL and 2 Putnam tasks across the
two pinned Lean runtimes. SOL and PPLX each reach 13/40, JEV 12/40, the fixed
workflow 11/40, and DREX 10/40. DREX has 11 proof-audit passes but only 10 full
workflow successes, illustrating why proof validity and workflow completion are
reported separately. No matched single-agent Formal40 result is available.

Recovery from an observed proof failure occurs in 3/29 SOL, 2/29 PPLX, 1/28
fixed, 1/29 JEV and 0/30 DREX trajectories. SOL uses more evidence/retrieval
branches, JEV is diagnosis-heavy, DREX repeatedly remains in repair, and PPLX is
compiler-heavy in this run. The fixed workflow has the lowest observed executor
text-token proxy (19.9k per task, versus 36.3k--48.5k for the dynamic routers),
but this proxy excludes router tokens, is not USD cost, and does not normalize
provider load or run time. The small recovery counts and one run per method do
not establish statistical dominance.

### Structured data / Table QA

Structured40 replaces the earlier SpreadsheetBench20 cohort with 22
WikiTableQuestions, 14 HiTab and 4 TableBench tasks under a normalized typed
answer/evidence contract. Trusted-gold passes are 29/40 for the fixed workflow,
28/40 for DREX, 27/40 for SOL, 25/40 for single agent, 23/40 for JEV and 20/40
for PPLX. This is a task-family and contract change, not a causal before/after
comparison of router quality.

Among the dynamic routers, STOP F1 is 91.7% for SOL, 90.5% for JEV, 85.7% for
DREX and 65.4% for PPLX; it is a stopping metric, not overall task accuracy.
Observed recovery after public failure is 13/23 for DREX, 11/24 for SOL, 9/23
for JEV and 1/17 for PPLX, compared with 13/23 for single agent and 12/23 for the
fixed workflow. JEV is answer-composer-heavy, SOL uses more inspection and
analysis, DREX combines analysis, selection and composition, and PPLX performs
more repeated inspection and diagnosis. These trajectories demonstrate strategy
diversity, but the 40-task, single-run measurements do not prove causal role
utility or a stable leaderboard.

## Loading

```python
from datasets import load_dataset

# Published legacy synthetic Track A
track_a = load_dataset("TrangBui/RoleRouteBench", "router_state")
track_a_labels = load_dataset("TrangBui/RoleRouteBench", "track_a_labels")

# Updated Track B
tasks = load_dataset("TrangBui/RoleRouteBench", "track_b_tasks", split="full")
agents = load_dataset("TrangBui/RoleRouteBench", "track_b_agents", split="full")
trajectories = load_dataset(
    "TrangBui/RoleRouteBench", "track_b_trajectories", split="full"
)
results = load_dataset("TrangBui/RoleRouteBench", "track_b_results", split="full")
benchmark_results = load_dataset(
    "TrangBui/RoleRouteBench", "benchmark_results", split="full"
)
```

JSON-valued columns are stored as JSON strings. Decode them with `json.loads`.

## Visibility and publication policy

The candidate exposes router-visible task artifacts, role cards, compact public
trajectories, and outcome summaries. It does **not** publish packet `private/`
directories, trusted answers, reference proofs, gold patches, raw provider
responses, credentials, local paths, or experiment archives.

The `evaluator_packet_path` field is null in this candidate. Outcome tables are
for analysis only and must never be supplied to the router. This is a visibility
contract, not a claim that the benchmark is a sealed test set.

## Sources and licenses

- Database and Code Debugging retain per-packet upstream provenance and notices.
- Formal40 records source identifiers and revisions for MiniF2F, LeanDojo,
  APRIL, and Putnam-derived tasks.
- Structured40 uses WikiTableQuestions (CC-BY-SA-4.0), HiTab (Computational Use
  of Data Agreement v1.0), and TableBench metadata declaring Apache-2.0.

Source-specific notices and per-packet metadata take precedence over any single
repository-level license label. TableBench's exact upstream revision and license
text remain a publication checklist item. This dataset card is not legal advice.

## Limitations

- Formal40 and Structured40 are runtime-verified but not fully human-reviewed.
- The legacy synthetic Track A is not aligned with the new Formal40/Table-QA40
  environments; use it only as a historical simulated one-step track. Empirical
  Track A V2 is not part of this release and must not be inferred from the
  unchanged legacy tables. Its results will be published in the planned
  follow-up after the new results table is complete and verified.
- Track B uses transparent public cohorts and one reference run per method; it is
  not contamination-free and does not estimate production reliability.
- Executor stochasticity, provider behavior, tool outcomes, termination, and
  routing all affect closed-loop success.

See `RELEASE_NOTES.md`, `PUBLICATION_CHECKLIST.md`, `release_manifest.json`, and
`track_b_package_report.json` in this candidate for exact provenance and gates.

## Roadmap

- publish the empirical Track A V2 follow-up within the next few days, after the
  results table finishes and is verified;
- restore the redesigned Track C recovery benchmark;
- finish structured-data human review; and
- add four additional Track B domains to reach the planned eight-domain suite,
  including Multi-hop Knowledge and Document/Media led by Tran Ngoc Cam Nguyen.

