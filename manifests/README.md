# Manifests

Manifests are sanitized snapshots of local app state. They are meant to answer:

- which app bundle is the active Codex target
- which version the bundle and executable report
- which native Bambu plugin files are expected locally
- which stock-resource differences are intentional
- whether TinManX is separate from TinManX1

Regenerate locally with:

```bash
python3 scripts/collect_baseline_manifest.py --output manifests/current-local.json
```
