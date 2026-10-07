"""`kit lanes ...`: runs one lanes command and turns its result into output and an exit code.

Imported lazily by cli.py, so a fault in the lane code can't take the protected guard down.
"""

import sys
from pathlib import Path

from kitlib import lane_cycle, lane_owners, lane_setup, lane_status, lanes
from kitlib.config import ConfigError, find_root, load

OK, UNFINISHED, USAGE = 0, 1, 2


def run(args) -> int:
    try:
        here = Path.cwd()
        config = load(find_root(here))
        command = args.lanes_command
        if command == "create":
            lines = lane_setup.create(here, config, args.names, args.dry_run)
            # Said where lanes are set up too, so a split's overlaps are seen before work starts.
            notes, problems = lane_owners.tracked_overlaps(lanes.main_checkout(here), config)
            lines += [f"Note: {note}" for note in notes] + [f"! {problem}" for problem in problems]
        elif command == "remove":
            lines = [lane_setup.remove(here, config, args.name, args.force)]
        elif command == "start":
            lines = lane_cycle.start(here, config, args.task, args.abandon)
        elif command == "sync":
            lines = lane_cycle.sync(here, config)
        elif command == "finish":
            lines = lane_cycle.finish(here, config, args.title, args.body_file)
        else:
            lines = [lane_status.format_status(lane_status.status(here, config, args.offline))]
    except lane_setup.PartialCreate as error:
        print("\n".join(error.lines))
        print(f"kit: {error}", file=sys.stderr)
        return USAGE
    except lanes.Unfinished as error:  # before LaneError, its base class
        print(f"kit: {error}", file=sys.stderr)
        return UNFINISHED
    except (ConfigError, lanes.LaneError) as error:
        print(f"kit: {error}", file=sys.stderr)
        return USAGE
    print("\n".join(lines))
    return OK
