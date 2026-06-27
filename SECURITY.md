# Security And Privacy

This public repository is designed to contain source patches, helper scripts, documentation, sanitized manifests, and attribution only.

Do not commit:

- printer credentials, access codes, cloud tokens, API keys, or passwords
- private keys, certificates, or local network secrets
- full app-support directories or private printer profile dumps
- `.app`, `.dmg`, `.deb`, `.AppImage`, `.dylib`, or other binary payloads
- proprietary Bambu networking plugin binaries
- private validation logs that identify printers, hostnames, serials, users, or local paths

Before opening a pull request or publishing a release, run:

```bash
python3 checks/verify_release.py
```

The checker looks for required release files, required attribution markers, public-license markers, and common private-path or credential patterns. It is a guardrail, not a substitute for human review.

If a sensitive value is accidentally published, rotate the affected credential immediately and treat the Git history as exposed.
