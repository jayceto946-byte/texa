"""Offline explicit migration. Stop all Texa backends before applying; rehearse on a copy first."""
import argparse
from pathlib import Path
from backend.services.goals.focus_migration import migrate_focus


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--apply',action='store_true',help='Explicitly authorize the stopped database migration')
    args=parser.parse_args()
    if not args.apply:
        parser.error('No data changed. Review the backup/rollback plan and pass --apply only after approval.')
    backup=migrate_focus(args.database)
    print(f'Focus schema v3 ready. Backup: {backup or "already v3"}')


if __name__=='__main__':
    main()
