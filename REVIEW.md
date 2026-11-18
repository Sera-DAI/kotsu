# Review rules

Read from the base branch, never from the PR under review.

Before every PR, three read-only reviewers (security, tests, docs) review the diff in
parallel, each as a separate agent, and their result goes in the PR description.

## Severity labels
- **Important**: blocks the PR (bug, secret or personal data, weakened check, disabled test,
  missing error case).
- **Nit**: suggestion; apply it or justify skipping it.
- **Pre-existing**: a problem that was already there; report it, do not block on it.

## What to check
- Secrets, tokens, account IDs, real names, real addresses or local paths in code, tests, docs
  or logs. Real financial data never enters the repository.
- Any change to `.github/`, `.claude/`, `tools/check.py`, `tools/layers.py`,
  `tools/pre_push_gate.py`, `CODEOWNERS`, `REVIEW.md` or `AGENTS.md`: always a finding to justify.
- Workflows: minimal `permissions`, Actions pinned by commit SHA, no `pull_request_target`.
- Tests: no `skip`, `xfail`, retry-until-pass or sleep; new code has an error case; the test
  count did not drop (deleting a test needs the maintainer's approval).
- Layers (`AGENTS.md`) and data rules (cents as `int`, transactions, migrations) respected.
- Docs: README and `AGENTS.md` updated in the same PR that changes what they describe; links exist.
- Anything that could not be verified here is listed as a limitation.

## Answer format
finding, `file:line`, label, blocks or suggests; last line: `approved` or `not approved`.
