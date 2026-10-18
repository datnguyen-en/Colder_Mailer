import base64
import json
import os

from app.aws import ssm
from app.worker import RunResult


class FakeSSM:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def get_paginator(self, name):
        assert name == "get_parameters_by_path"
        return self

    def paginate(self, **kwargs):
        self.calls.append(kwargs)
        return iter(self.pages)


def test_ssm_parameters_become_environment_variables(monkeypatch):
    fake = FakeSSM([
        {"Parameters": [{"Name": "/colder-mailer/prod/DATABASE_URL", "Value": "postgres://x"}]},
        {"Parameters": [{"Name": "/colder-mailer/prod/ENV", "Value": "prod"}]},
    ])
    monkeypatch.setenv("SSM_PREFIX", "/colder-mailer/prod")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("ENV", "set-on-lambda")

    ssm.load_into_environment(fake)

    assert fake.calls == [{"Path": "/colder-mailer/prod/", "WithDecryption": True, "Recursive": False}]
    assert os.environ["DATABASE_URL"] == "postgres://x"
    assert os.environ["ENV"] == "set-on-lambda"  # values set on the Lambda win


def test_without_prefix_nothing_is_loaded(monkeypatch):
    monkeypatch.delenv("SSM_PREFIX", raising=False)
    ssm.load_into_environment(client="unused")  # would fail if it tried to call SSM


def function_url_event(method, path, body=b"", headers=None):
    return {
        "version": "2.0", "routeKey": "$default", "rawPath": path, "rawQueryString": "",
        "headers": {"host": "abc.lambda-url.us-east-1.on.aws", **(headers or {})},
        "requestContext": {
            "accountId": "anonymous", "apiId": "abc", "domainName": "abc.lambda-url.us-east-1.on.aws",
            "domainPrefix": "abc", "requestId": "r1", "routeKey": "$default", "stage": "$default",
            "time": "17/Oct/2026:20:00:00 +0000", "timeEpoch": 0,
            "http": {"method": method, "path": path, "protocol": "HTTP/1.1",
                     "sourceIp": "1.2.3.4", "userAgent": "test"},
        },
        "body": base64.b64encode(body).decode(), "isBase64Encoded": True,
    }


def test_api_handler_serves_function_url_requests():
    from app.aws.api import handler

    res = handler(function_url_event("GET", "/health"), None)
    assert res["statusCode"] == 200 and json.loads(res["body"]) == {"ok": True}


def test_api_handler_receives_binary_uploads(client):
    from app.aws.api import handler

    pdf = b"%PDF-1.7\n" + bytes(range(256))  # non-UTF-8 bytes must survive base64
    boundary = "XyZ"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"cv.pdf\"\r\n"
            f"Content-Type: application/pdf\r\n\r\n").encode() + pdf + f"\r\n--{boundary}--\r\n".encode()
    res = handler(function_url_event("POST", "/resume", body,
                                     {"content-type": f"multipart/form-data; boundary={boundary}"}), None)
    assert res["statusCode"] == 200, res["body"]
    assert client.get("/resume").content == pdf


def test_sender_handler_runs_one_queue_pass(monkeypatch):
    from app.aws import sender

    monkeypatch.setattr(sender.worker, "process_queue", lambda: RunResult("skipped", "queue is empty"))
    assert sender.handler({}, None) == {"outcome": "skipped", "detail": "queue is empty", "contact_id": None}
