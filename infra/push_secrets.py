"""Copy .env.prod into SSM Parameter Store as SecureStrings, one per setting.

    python3 infra/push_secrets.py            # uses ../.env.prod
    python3 infra/push_secrets.py --dry-run  # list what would be written

Values never appear in the output or in the process list (the AWS CLI reads
a private temporary JSON file, deleted after each call). After changing settings,
run infra/deploy.sh again so the Lambdas restart and read them.
"""

import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path

PREFIX = "/colder-mailer/prod"
# Used by the website only, or by migrations from your laptop; not needed in Lambda.
SKIP = {"SUPABASE_PUBLISHABLE_KEY", "MIGRATIONS_DATABASE_URL"}


def read_env(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text().splitlines():
        match = re.match(r"^([A-Z][A-Z0-9_]*)=(.*)$", line.strip())
        if match and match.group(2).strip() and match.group(1) not in SKIP:
            values[match.group(1)] = match.group(2).strip()
    return values


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--env-file", default=Path(__file__).resolve().parents[1] / ".env.prod", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    values = read_env(args.env_file)
    for name, value in sorted(values.items()):
        print(f"{PREFIX}/{name}")
        if args.dry_run:
            continue
        request = {"Name": f"{PREFIX}/{name}", "Value": value, "Type": "SecureString", "Overwrite": True}
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".json") as payload:
            json.dump(request, payload)
            payload.flush()
            subprocess.run(
                ["aws", "ssm", "put-parameter", "--cli-input-json", f"file://{payload.name}"],
                check=True, stdout=subprocess.DEVNULL,
            )
    print(f"{'Would write' if args.dry_run else 'Wrote'} {len(values)} settings under {PREFIX}/")


if __name__ == "__main__":
    main()
