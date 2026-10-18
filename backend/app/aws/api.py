"""The API Lambda: FastAPI behind a Lambda Function URL, through Mangum."""

from app.aws import ssm

ssm.load_into_environment()  # before app.main reads the config

from mangum import Mangum  # noqa: E402

from app.main import app  # noqa: E402

handler = Mangum(app, lifespan="off")
