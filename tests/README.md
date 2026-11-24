# Test layers

The test suite has two layers:

1. Source-only regression tests run in a clean clone and exercise schemas,
   routing protocols, transport diagnostics, scoring, and policy behavior.
2. Integration tests require packet banks or generated Track A/Track B artifacts
   under `data/`. Those artifacts are distributed separately and are intentionally
   excluded from the source repository.

Run the source-only gate:

```powershell
python scripts/validate_source_tree.py
```

After restoring the external packet banks, run the complete suite:

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

