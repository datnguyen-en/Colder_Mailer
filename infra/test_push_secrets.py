"""Offline regression checks: python3 -m unittest discover -s infra -p 'test_*.py'."""

import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import push_secrets


class PushSecretsTests(unittest.TestCase):
    def check_payload(self, *, fail=False):
        paths = []

        def run(args, **kwargs):
            self.assertEqual(args[:4], ["aws", "ssm", "put-parameter", "--cli-input-json"])
            self.assertTrue(args[4].startswith("file://"))
            path = Path(args[4][7:])
            paths.append(path)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(path.read_text()), {
                "Name": "/colder-mailer/prod/TEST_SECRET",
                "Value": 'quoted "value" with \\ slashes',
                "Type": "SecureString", "Overwrite": True,
            })
            self.assertNotIn("quoted", " ".join(args))
            self.assertTrue(kwargs["check"])
            if fail:
                raise subprocess.CalledProcessError(1, args)

        with tempfile.TemporaryDirectory() as folder:
            env = Path(folder) / ".env.prod"
            env.write_text('TEST_SECRET=quoted "value" with \\ slashes\n')
            output = io.StringIO()
            with patch("sys.argv", ["push_secrets.py", "--env-file", str(env)]), \
                    patch("push_secrets.subprocess.run", side_effect=run), \
                    contextlib.redirect_stdout(output):
                if fail:
                    with self.assertRaises(subprocess.CalledProcessError):
                        push_secrets.main()
                else:
                    push_secrets.main()
            self.assertNotIn("quoted", output.getvalue())
        self.assertEqual(len(paths), 1)
        self.assertFalse(paths[0].exists())

    def test_private_json_file_is_readable_during_call_and_removed_afterwards(self):
        self.check_payload()

    def test_private_json_file_is_removed_on_aws_failure(self):
        self.check_payload(fail=True)


if __name__ == "__main__":
    unittest.main()
