# RoleRouteBench

RoleRouteBench is a standalone benchmark for evaluating dynamic role routing in
multi-agent systems. This repository contains the benchmark schemas, execution
harness, domain adapters, routing baselines, builders, validators, release tools,
and human-review utilities extracted from the original research workspace.

The extraction intentionally preserves the benchmark harness, state protocols,
executor contracts, routing logic, and evaluation logic. Only workspace-specific
training code, local run artifacts, caches, machine paths, and legacy project
wrappers were removed.

## Track identity

The Track A configurations already published on Hugging Face are a legacy
synthetic state bank generated through LLM simulation. They are not the empirical
Track A V1 used internally by this project.

| Track | Origin | Publication status |
|---|---|---|
| Legacy synthetic Track A | LLM-generated simulated states | Published for backward compatibility |
| Empirical Track A V1 | Recorded live routing states | Not released |
| Empirical Track A V2 | Current multi-router Track B trajectories | Built and validated; labeling/review incomplete |
| Track B | Closed-loop router/executor trajectories | Published and under active revision |

Release metadata must retain this distinction. In particular, the legacy
synthetic Track A must never be described as empirical Track A V1.

## Installation

```powershell
python -m pip install -e ".[test]"
```

Optional review UI and formal-proof dependencies:

```powershell
python -m pip install -e ".[review]"
python -m pip install -e ".[formal]"
```

## Common commands

```powershell
python scripts/build_roleroutebench_track_a_v2.py
python scripts/validate_roleroutebench_track_a_v2.py
python scripts/run_shared_environment.py --help
python scripts/evaluate_shared_environment.py --help
python scripts/prepare_roleroutebench_hf_4_1_rc1.py --help
```

Generated packet banks, runs, reports, provider outputs, and release candidates
are intentionally excluded from Git. Restore them from their source release or
build them using the scripts and manifests in this repository.

## Local runtime profiles

Code-debugging environments are machine-specific. Copy
`config/shared_environment/code_runtime_profiles.example.json` to
`config/shared_environment/code_runtime_profiles.json`, then replace every
placeholder with the corresponding local interpreter or repository mirror. The
active file is ignored by Git.

## Reproducibility contract

- Router-visible state and private evaluator state remain separated.
- State schemas, action protocols, budgets, and executor contracts are unchanged.
- Release builders fail closed when required source artifacts are absent.
- Machine-local paths and credentials are not release inputs.
- Generated Hugging Face payloads are built outside the source tree and validated
  before publication.

