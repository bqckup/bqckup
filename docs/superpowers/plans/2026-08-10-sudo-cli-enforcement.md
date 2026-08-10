# Sudo CLI Enforcement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow the Bqckup CLI to run when invoked through `sudo`, while giving non-root invocations an actionable command instead of silently stopping.

**Architecture:** Keep privilege enforcement at the existing Python entrypoint. Replace username-based detection with effective-UID detection, expose the check as a small testable helper, and preserve the existing initialization/CLI flow for root processes.

**Tech Stack:** Python, Typer, pytest.

## Global Constraints

- Do not automatically invoke `sudo` or alter command arguments.
- A process is authorized when its effective UID is 0.
- A non-root invocation exits with status 1 and prints `sudo bqckup ...` guidance.
- Do not change backup behavior after the privilege gate passes.

---

### Task 1: Enforce effective-root execution at the CLI entrypoint

**Files:**
- Modify: `bqckup.py` near the `__main__` entrypoint
- Test: `tests/unit/test_cli.py`

**Interfaces:**
- Produces: a testable privilege helper and a non-root entrypoint message containing the exact re-invocation command.

- [ ] **Step 1: Write the failing tests**

  Add tests for the helper returning false/true based on `os.geteuid`, and for the non-root message including `sudo bqckup` and the original arguments.

- [ ] **Step 2: Run the focused tests and verify they fail**

  Run: `pytest tests/unit/test_cli.py -q`
  Expected: FAIL because the helper and entrypoint behavior do not exist yet.

- [ ] **Step 3: Implement the minimal fix**

  Add a helper that checks `os.geteuid() == 0`; use it in the `__main__` guard. Print a command assembled from `bqckup` plus `sys.argv[1:]`, then raise `SystemExit(1)` for non-root execution. Keep initialization and `bq_cli()` unchanged for root.

- [ ] **Step 4: Run focused and full tests**

  Run: `pytest tests/unit/test_cli.py -q` and `pytest -q`
  Expected: all focused and repository tests pass.

- [ ] **Step 5: Verify the user-facing command path**

  Run the CLI in a non-root simulation and confirm it exits non-zero with the sudo instruction; inspect the diff for unrelated changes.
