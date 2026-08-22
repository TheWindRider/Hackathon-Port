import argparse
import logging

from dotenv import load_dotenv

load_dotenv()

from services.telemetry import factory_step, init_telemetry


def main():
    parser = argparse.ArgumentParser(
        description="Agentic Software Factory — market data pipeline"
    )
    parser.add_argument(
        "--platform",
        choices=["kalshi", "polymarket", "both"],
        default="both",
        help="Platform(s) to scrape (default: both)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max records per platform (default: 50)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

    init_telemetry(service_name="hackathon-factory")

    from services.software_factory.runner import run

    with factory_step("factory.run", platform=args.platform, limit=args.limit):
        results = run(platform=args.platform, limit=args.limit)

    for r in results:
        status_icon = "✓" if r.status == "success" else "✗"
        bd_job = f"  bd_job={r.bd_collection_id}" if r.bd_collection_id else ""
        print(
            f"{status_icon} {r.platform:12s}  {len(r.records):3d} records  [{r.status}]  port_job={r.collector_id}{bd_job}"
        )
        if r.error:
            print(f"  Error: {r.error}")


if __name__ == "__main__":
    main()
