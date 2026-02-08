# Decisions Log

This file tracks meaningful technical decisions for template evolution.

## 2026-02-08

1. Enforce 100% app coverage (line + branch) in CI.
Reason:
Template quality should be verifiable and stable for downstream projects.

2. Add three test lanes (`unit`, `integration`, `e2e`) via pytest markers.
Reason:
Clear test intent improves developer speed and CI diagnostics.

3. Keep migrations as schema authority (no model import-time `create_all`).
Reason:
Predictable schema evolution and safer production deployment workflows.
