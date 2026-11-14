# AGENTS.md

Guide for anyone changing this repository, person or agent. Read it before changing code.

## What it is

Kotsu: a terminal app (Python + Textual) for the month's income, expenses, categories,
accounts and installments. Main target: Windows Terminal, working the same on Linux.

## Commands

```bash
pip install -e ".[dev]"
kotsu --data ./tmp                   # opens the app with a test folder
python tools/check.py --quick        # before every commit
python tools/check.py                # before every PR (same as CI)
python tools/layers.py               # only the layers rule
python tools/check_install.py        # pipx install; uses the network only to install
python tools/generate_vectors.py     # rewrites vectors/*.json (Android cases)
```

## Layers (the test fails if they are broken)

| Folder | May import | Must not |
|---|---|---|
| `src/kotsu/domain/` | only the standard library without I/O | `storage`, `ui`, `sqlite3`, `os`, `pathlib`, `io`, Textual, Rich |
| `src/kotsu/storage/` | `domain` | `ui`, Textual, Rich |
| `src/kotsu/ui/` | `domain`, `storage` | `sqlite3` directly |

`src/kotsu/__main__.py` is the assembly point and may see everything.
Financial rules (totals, installments, quick-line parser) live in `domain/`; the UI only shows.

## Data rules

- An amount is an `int` in cents, always positive; the sign comes from `kind` (income/expense).
  Never `float`.
- Every entry has an account (D21): the domain and the database refuse an entry without one.
  The category is optional.
- Dates are calendar dates (`datetime.date`), no time zone, stored as `YYYY-MM-DD`.
- Totals (income, expenses, balance) are never stored: SQL computes them per month.
- Month queries use the range `date >= start AND date < end` so the index is used.
  Lists are paginated (`limit`, `offset`).
- On screen, a negative amount shows only in red, without a sign (`domain.currency.format_cents`).
- Amounts are typed and shown in the Brazilian format (`1.234,56`) and dates as `dd/mm/yyyy`;
  everything else (code, UI text, docs) is in English.

## Database and migrations

- Every write goes through `Database.transaction()`: all or nothing. The installments of a
  purchase go in a single transaction.
- Schema changed? Create `src/kotsu/storage/migrations/NNNN_name.sql` with the next number.
  Never edit a published migration. Before migrating an existing database, the app copies the
  file to `kotsu.before-vN.sqlite`.
- Test every new migration with a database at the previous version.
- Migrations 0001 to 0003 still use the original Portuguese table names; 0004 renames
  everything to English (and `receita`/`despesa` to `income`/`expense`).
- Recurrence (D36): `recurring` category + `recurrence` table (series template and
  `generated_until`). `Database.extend_recurrences(month)` generates the missing months and
  only moves forward, so a deleted month does not come back. The UI calls it when drawing,
  limited to today + 24 months.
- Backup is manual only (D35): key `b` copies the database to `backups/` with date and time in
  the name, without overwriting, and keeps only the 5 most recent (pruned after publishing).
  The app never backs up on its own. Test clock and failures with temporary data. In-memory
  (`Database.in_memory()`) makes no backup.

## Exchange between devices (D39)

- Each device has its own database; data is joined through an exchange file
  (`--export`, `--import`, `--verify`). The merge rule is pure and lives in
  `domain/merge.py`; reading, writing and applying live in `storage/exchange.py`.
- Every write to `account`, `category`, `entry` and the `recurrence` template stamps
  `changed_at` with `Database.stamp(c)` (one stamp per transaction). Editing an entry clears
  `generated`. Deleting an entry writes the tombstone before the `DELETE`. Forgot the stamp?
  The change loses to the other device on merge.
- Advancing `generated_until` does not stamp: the generated month uses the fixed `uid`
  (`month_uid`) and the series template's stamp.
- A new field in a synced table goes into: the migration, `exchange.read_state`,
  `exchange._apply`, `merge.validate`, the canonical form (changes the check code) and
  `FORMAT` if old files stop working. Format 1 files (Portuguese keys) are translated by
  `merge.upgrade_v1`.
- `vectors/*.json` are the cases shared with the Android app. Changed a domain rule
  (quick line, dates, currency, stamp, merge)? Add the case in `tools/generate_vectors.py`, run
  it and review the JSON diff. The test fails if the files are out of date.

## Compatibility with older versions

- Files named `money.*` (database, copies, backups) are renamed to `kotsu.*` by
  `storage.paths.upgrade_old_names`, never overwriting. The old `money-cli` local folder is
  renamed to `kotsu`. These two are the only places that know the old name.
- `pasta_dados` in `local.toml`, `tema.toml` and `kotsu.trava` are still read.
- Removed: the `money` command, the Portuguese flags and `MONEY_CLI_DADOS`.

## How to work

- Everything in English: code, messages, UI text, documents and file names.
- New or changed product decision: describe it in the PR and update the README in the same PR.
- Nothing goes into `main` without the maintainer's approval. Work on a branch and open a PR.
- Tests use neither the network nor the real data folder (use `Database.in_memory()` or
  `tmp_path`).
- The README and this file are updated in the same PR that changes what they describe.
- Fixed palette in `ui/colors.py`; change it little and on purpose.
- Never version databases, backups or exports (`.gitignore` blocks SQLite, `*.mcv`, `*.mcp`
  and `*.csv`).
- Real install tests via pipx run outside the checkout on Windows/Linux CI; they need the
  network only to install. Unit tests stay offline.
- Commits with the GitHub noreply e-mail, fully in English.
