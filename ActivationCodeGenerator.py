"""CLI generator for signed license tokens."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SRC_PATH = Path(__file__).resolve().parent / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from worklogger.license_signer import build_payload, payload_to_pretty_json, sign_license


def main() -> None:
    """Generate a signed license from CLI parameters."""
    args = parse_args()
    issued_at = datetime.now(timezone.utc)
    payload = build_payload(_payload_fields(args, issued_at))
    print(payload_to_pretty_json(payload))
    print(sign_license(payload, args.private_key))


def parse_args() -> argparse.Namespace:
    """Parse generator arguments."""
    parser = argparse.ArgumentParser(description="Create a signed Worklogger license")
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--license-id", required=True)
    parser.add_argument("--customer-id", required=True)
    parser.add_argument("--product", default="worklogger")
    parser.add_argument("--days", type=int, required=True)
    parser.add_argument("--feature", action="append", default=[])
    parser.add_argument("--username")
    return parser.parse_args()


def _payload_fields(args: argparse.Namespace, issued_at: datetime) -> dict[str, object]:
    expires_at = issued_at + timedelta(days=args.days)
    return {
        "version": 1,
        "license_id": args.license_id,
        "customer_id": args.customer_id,
        "product": args.product,
        "issued_at": issued_at.isoformat().replace("+00:00", "Z"),
        "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
        "features": args.feature,
        "username": args.username,
    }


if __name__ == "__main__":
    main()
