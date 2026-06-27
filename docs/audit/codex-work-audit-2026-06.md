# Codex Work Audit - June 2026

Generated: 2026-06-18

## Scope

This audit covers TinManX1 app/profile work from recent Codex chats and
the local repo artifacts. It is intentionally focused on installed-app behavior,
printer-host persistence, and upstream attribution.

## Recent Work

### Printer Host Persistence

- Protected Centauri Carbon #1/#2, Qidi, Prusa, and related printer mappings
  from disappearing across app launches and profile edits.
- Treated canonical device identity as the durable target, while allowing live
  temporary IPs to exist during firmware/network changes.
- Used repair/check scripts before broad app-state resets:
  - `tools/check_printer_host_persistence.py`
  - `tools/repair_printer_host_persistence.py`
  - historical LAN-config repair helpers from the pre-rebrand app

### Installed App Validation

- Validated fixes against `/Applications/TinManX1.app`, not just local
  source state.
- Preserved the practice of replacing only the needed installed app binary or
  wrapper pieces and re-signing where required.
- Added or used warning-only launch/preflight receipts so app launch stays
  resilient while drift remains visible.

### Active Print Guard

- Corrected diagnosis for cases where the app looked slow or stuck while a real
  print was active.
- Before repairing or detaching printer mappings, the app/tooling should check
  printer activity and preserve the live connection when a job is running.

### Camera And Device Tab Work

- K2 camera feed work compared TinManX1 device-tab behavior against Creality
  Print, which successfully showed the camera feed.
- This repo should own app/profile/browser-side device-tab behavior. Live
  printer config remains in `printer-ops-codex`.

## Historical Repo-Backed Work

- Baseline and upgrade notes for OrcaSlicer 2.4.0.
- proprietary-connectivity notes and shutdown-risk checks.
- local printer-control notes.
- TinManX separation docs showing what belongs in TinManX1 versus the
  TinManX product layer.

## Attribution And License Posture

- TinManX1 inherits from OrcaSlicer and the wider Bambu Studio /
  PrusaSlicer / Slic3r lineage.
- Preserve upstream license files and notices.
- Keep Bambu networking/plugin behavior isolated and risk-labeled.
- Keep TinManX-only product experiments out of this repository unless the app
  bridge requires a small integration point.

## GitHub Handling

- Store app-level repair notes, launcher/preflight docs, and profile-persistence
  logic here.
- Do not commit full installed app bundles, native plugins, user app-support
  folders, API keys, or live printer credentials.
- Keep repo docs linked from `NOTICE.md` so future readers can find the
  attribution ledger.
