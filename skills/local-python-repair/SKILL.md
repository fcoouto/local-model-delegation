---
name: local-python-repair
description: Use when an understood, nonurgent pure-Python helper defect has a small file allowlist and independent regression checks, and an owner-approved local-model route is configured.
---

# Local Python Repair

Codex owns scope, checks and integration. The local model proposes files only. Follow explicit user restrictions first.

Invoke `python3.11 <this-skill>/scripts/repair.py --state-dir <private-state> <command>`; use `--help` for arguments. Read [the brief contract](references/contracts.md) when preparing a repair.

Use the shared [native orchestration workflow](../local-delegation/SKILL.md) with capability `bounded_python_repair`. Keep the same origin/task key across both skills; never create a competing job. Legacy schema-1 state uses its existing immediate-fallback behavior. Schema-2 state adds assessed selection and shared waiting while preserving the Python checker and explicit fallback snapshot.

The narrow contract excludes trading/risk, authorization, migrations, services, broad investigation and unrestricted tools. Unsupported tasks remain native. Keep independent oracle source private. The helper never applies project files.
