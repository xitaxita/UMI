"""Fill in or change the task of one recorded online session."""

import argparse
import sys
from pathlib import Path

from umi_ros2.session.layout import read_session, session_task, set_task


def argument_parser():
    """Build the command-line interface."""
    parser = argparse.ArgumentParser(
        description=(
            'Set the natural-language task in session.yaml. Only session.yaml '
            'changes; MP4 and MCAP data are never touched. Version 1 sessions '
            'are upgraded to version 2.'))
    parser.add_argument('session', help='online_session_<time> directory')
    parser.add_argument('task', help='task text; use "" to clear it')
    parser.add_argument(
        '--force', action='store_true',
        help='also modify a session still marked active (only when its '
             'launch is no longer running)')
    return parser


def main(argv=None):
    """Update one session task and print the change."""
    args = argument_parser().parse_args(argv)
    session = Path(args.session).expanduser().resolve()
    try:
        metadata = read_session(session)
    except (OSError, ValueError) as error:
        print(f'error: cannot read {session}/session.yaml: {error}',
              file=sys.stderr)
        return 1
    if metadata.get('status') == 'active' and not args.force:
        print(
            f'error: {session.name} is still active; a running launch may be '
            'writing session.yaml. Stop it first, or pass --force if the '
            'launch was interrupted.', file=sys.stderr)
        return 1
    previous = session_task(metadata)
    updated = set_task(session, args.task)
    print(f'{session.name}: task {previous!r} -> {updated["task"]!r} '
          f'(schema_version {updated["schema_version"]})')
    if not updated['task']:
        print('warning: the task is empty; dataset export will require one',
              file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
