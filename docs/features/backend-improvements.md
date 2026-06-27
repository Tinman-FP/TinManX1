# Backend Improvements

The TinManX1 work also includes non-feature-surface improvements that make the app more reliable for real printer workflows.

## Included Themes

- dedicated TinManX1 bundle identity and app-support separation
- local installed-app verification scripts
- upgrade path from the previous local app baseline to the Orca Slicer 2.4.0 source line
- proprietary plugin boundary notes without redistributing binary-only networking components
- profile and printer-control separation notes for local device workflows
- device-agent compatibility context where it affects TinManX1 app behavior
- host/profile persistence philosophy: durable identity should stay separate from temporary reachability

## Public Boundary

This public repo includes scripts and notes, not private app-support trees. Any live-printer configuration, cloud token, local host mapping, access code, or proprietary plugin binary must stay out of this repository.
