"""CLI generator for signed license tokens and Ed25519 key material."""

from __future__ import annotations

import argparse
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SRC_PATH = Path(__file__).resolve().parent / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from worklogger.ed25519_py import public_key_from_seed
from worklogger.license_schema import encode_base64url
from worklogger.license_signer import build_payload, payload_to_pretty_json, sign_license


def main() -> None:
    """Run key generation or signed license generation based on CLI command."""
    args = parse_args()
    if args.command == "generate-keys":
        private_key_path, public_key_path = generate_keys(args.output_dir)
        print(f"private_key={private_key_path}")
        print(f"public_key={public_key_path}")
        return
    payload = build_payload(build_payload_fields(args, datetime.now(timezone.utc)))
    print(payload_to_pretty_json(payload))
    print(sign_license(payload, args.private_key))


def parse_args() -> argparse.Namespace:
    """Parse command line arguments for key and license generation."""
    parser = argparse.ArgumentParser(description="Worklogger signed-license tools")
    subparsers = parser.add_subparsers(dest="command", required=True)
    add_key_subcommand(subparsers)
    add_license_subcommand(subparsers)
    return parser.parse_args()


def add_key_subcommand(subparsers: argparse._SubParsersAction) -> None:
    """Register key generation command."""
    parser = subparsers.add_parser("generate-keys", help="Generate Ed25519 key files")
    parser.add_argument("--output-dir", required=True, help="Directory to write key files")


def add_license_subcommand(subparsers: argparse._SubParsersAction) -> None:
    """Register signed-license generation command."""
    parser = subparsers.add_parser("create-license", help="Create signed license token")
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--license-id", required=True)
    parser.add_argument("--customer-id", required=True)
    parser.add_argument("--product", default="worklogger")
    parser.add_argument("--days", type=int, required=True)
    parser.add_argument("--feature", action="append", default=[])
    parser.add_argument("--username")


def generate_keys(output_dir: str) -> tuple[Path, Path]:
    """Create and persist private/public Ed25519 keys as base64url text files."""
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    private_seed = secrets.token_bytes(32)
    public_key = public_key_from_seed(private_seed)
    private_key_path = directory / "private_key.ed25519"
    public_key_path = directory / "public_key.ed25519"
    private_key_path.write_text(f"{encode_base64url(private_seed)}\n", encoding="utf-8")
    public_key_path.write_text(f"{encode_base64url(public_key)}\n", encoding="utf-8")
    return private_key_path, public_key_path


def build_payload_fields(args: argparse.Namespace, issued_at: datetime) -> dict[str, object]:
    """Build canonical payload fields from CLI arguments."""
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
