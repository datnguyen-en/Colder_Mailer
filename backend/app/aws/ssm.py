"""Secrets from AWS SSM Parameter Store, loaded into the environment on a cold start.

Each SecureString parameter under SSM_PREFIX (e.g. /colder-mailer/prod/DATABASE_URL)
becomes an environment variable named after its last path part, before the app's
config is read. Values set directly on the Lambda win over SSM.
"""

import os
from typing import Any


def load_parameters(prefix: str, client: Any = None) -> dict[str, str]:
    if client is None:
        import boto3  # provided by the Lambda runtime; not needed anywhere else

        client = boto3.client("ssm")
    prefix = prefix.rstrip("/") + "/"
    values: dict[str, str] = {}
    for page in client.get_paginator("get_parameters_by_path").paginate(
        Path=prefix, WithDecryption=True, Recursive=False
    ):
        for param in page["Parameters"]:
            values[param["Name"][len(prefix):]] = param["Value"]
    return values


def load_into_environment(client: Any = None) -> None:
    prefix = os.environ.get("SSM_PREFIX")
    if not prefix:
        return  # local runs and tests use .env
    for name, value in load_parameters(prefix, client).items():
        os.environ.setdefault(name, value)
