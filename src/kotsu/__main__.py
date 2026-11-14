"""Entry point: `kotsu` (or `python -m kotsu`)."""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from kotsu import __version__


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kotsu", description="Personal finance in the terminal.")
    parser.add_argument("--data", type=Path, help="data folder (default: the user's folder)")
    parser.add_argument(
        "--data-folder",
        type=Path,
        metavar="FOLDER",
        help="saves FOLDER (e.g. on Google Drive) as this computer's data folder and exits",
    )
    parser.add_argument(
        "--default-data-folder",
        action="store_true",
        help="goes back to this computer's default data folder and exits",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="opens even with Kotsu open on another computer or with conflicted copies",
    )
    exchange = parser.add_mutually_exclusive_group()
    exchange.add_argument(
        "--export",
        type=Path,
        metavar="FILE",
        help="writes the data to an exchange file for another device and exits",
    )
    exchange.add_argument(
        "--import",
        dest="import_file",
        type=Path,
        metavar="FILE",
        help="merges another device's exchange file into the data here and exits",
    )
    exchange.add_argument(
        "--verify",
        type=Path,
        nargs="?",
        const=True,
        metavar="FILE",
        help="shows the check code; with FILE, the differences from it, and exits",
    )
    parser.add_argument("--version", action="version", version=f"kotsu {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    if args.data_folder is not None or args.default_data_folder:
        return _configure_folder(args)

    from kotsu.storage import lock
    from kotsu.storage.database import Database
    from kotsu.storage.paths import backups_folder, database_file
    from kotsu.ui.app import KotsuApp

    file = database_file(args.data)
    folder = file.parent
    copies = lock.conflicts(folder, file.name)
    if copies and not args.force:
        listing = "\n".join(f"  {c}" for c in copies)
        print(
            "Drive kept conflicted copies of the database (two computers saved at the same\n"
            f"time):\n{listing}\n"
            "Check which one has the right entries, keep only that one as kotsu.sqlite and\n"
            "move the others out of the folder. To open anyway: kotsu --force",
            file=sys.stderr,
        )
        return 1
    try:
        mine = lock.acquire(folder, f"{dt.datetime.now():%d/%m/%Y %H:%M}", args.force)
    except lock.DatabaseInUse as error:
        print(
            f"{error}\nClose Kotsu there and wait for Drive to finish syncing. If it was\n"
            "closed by force, use: kotsu --force",
            file=sys.stderr,
        )
        return 1
    try:
        database = Database.open(file, backups_folder(folder))
        try:
            if args.export or args.import_file or args.verify:
                return _exchange(database, args)
            KotsuApp(database, theme_folder=folder).run()
        finally:
            database.close()
    finally:
        mine.release()
    return 0


def _exchange(database, args: argparse.Namespace) -> int:
    """`--export`, `--import` and `--verify` (D39): data exchange between devices."""
    from kotsu.domain import merge
    from kotsu.storage import exchange

    try:
        if args.export:
            code = exchange.export(database, args.export.expanduser())
            print(f"Data exported to {args.export}\nCheck code: {code}")
        elif args.import_file:
            summary = exchange.import_file(database, args.import_file.expanduser())
            if summary.nothing:
                print("Nothing changed here: this device already had everything the file brings.")
            else:
                print(
                    f"Entries: {summary.added} added, {summary.changed} changed,"
                    f" {summary.removed} removed."
                )
            print(f"Check code: {exchange.check_code(database)}")
            differences = exchange.compare(database, args.import_file.expanduser())
            if not differences.equal:
                print(
                    "The other device does not have everything that is here yet: export from"
                    " here and import there for the codes to match."
                )
        elif args.verify is True:
            print(f"Check code: {exchange.check_code(database)}")
        else:
            here = exchange.read_state(database)
            there = exchange.read_file(args.verify.expanduser())
            differences = merge.compare(here, there)
            print(f"Code here:    {differences.code_here}")
            print(f"Code in file: {differences.code_there}")
            if differences.equal:
                print("Equal: both have the same data.")
                return 0
            for title, items, state in (
                ("Only here", differences.only_here, here),
                ("Only in the file", differences.only_there, there),
            ):
                if items:
                    print(f"\n{title} ({len(items)}):")
                    for item in items:
                        print(f"  {merge.describe(item, state)}")
            if differences.different:
                print(f"\nDifferent ({len(differences.different)}):")
                for mine, theirs in differences.different:
                    print(f"  here: {merge.describe(mine, here)}")
                    print(f"  file: {merge.describe(theirs, there)}")
            if not (differences.only_here or differences.only_there or differences.different):
                print("The entries are the same; the difference is in accounts, categories,")
                print("monthly series or deletions not exchanged yet.")
            return 2
    except merge.ExchangeError as error:
        print(f"That did not work: {error}", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"Could not write the file: {error}", file=sys.stderr)
        return 1
    return 0


def _configure_folder(args: argparse.Namespace) -> int:
    """`--data-folder`: points this computer to a folder (e.g. on Drive) and exits."""
    from kotsu.storage import paths
    from kotsu.storage.database import copy_database_file

    try:
        if args.default_data_folder:
            paths.save_configured_folder(None)
            print(f"Data folder: {paths.local_folder()} (default).")
            return 0
        target = args.data_folder.expanduser().resolve()
        new = paths.database_file(target)
        current = paths.database_file(paths.data_folder())
        if current.resolve() != new and current.exists():
            if new.exists():
                print(
                    f"There is already a database in {new} and another in {current}. Kotsu\n"
                    "does not join the two: pick the one that counts, move the other out and\n"
                    "run again.",
                    file=sys.stderr,
                )
                return 1
            target.mkdir(parents=True, exist_ok=True)
            copy_database_file(current, new)
            print(f"Database copied to {new} (the original stays in {current}).")
        paths.save_configured_folder(target)
    except OSError as error:
        print(f"Could not configure the folder: {error}", file=sys.stderr)
        return 1
    print(
        f"This computer's data folder: {target}\nBackups (key b) go to "
        f"{paths.local_folder() / 'backups'}, outside the sync."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
