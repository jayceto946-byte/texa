"""Local human trace review. Never calls a model or enables route takeover."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.services.decision.trace import DEFAULT_ROUTING_DB_PATH, RoutingTraceStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_ROUTING_DB_PATH))
    parser.add_argument("--trace-id")
    parser.add_argument("--reviewer")
    parser.add_argument("--capability")
    parser.add_argument("--group", help="conversation/time group; use the same value for related turns")
    args = parser.parse_args()
    if not Path(args.db).is_file():
        parser.error("routing trace database does not exist; collect shadow traces first")
    store = RoutingTraceStore(args.db)
    if args.trace_id:
        if not all((args.reviewer, args.capability, args.group)):
            parser.error("review requires reviewer, capability and group")
        store.review(args.trace_id, reviewer_id=args.reviewer, expected_capability=args.capability,
                     holdout_group=args.group)
    print(json.dumps({"traces": store.list(), "report": store.review_report()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
