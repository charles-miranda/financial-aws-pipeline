import boto3
import json
import logging
from datetime import date

logger = logging.getLogger(__name__)


def get_s3_client():
    """
    Retorna cliente S3.
    En Lambda usa el rol IAM automáticamente — no necesita credenciales.
    En local usa el perfil configurado en AWS CLI.
    """
    return boto3.client("s3")


def save_to_s3_raw(record: dict, bucket: str) -> str:
    """
    Guarda un registro en la capa raw/ de S3.
    Particionado por año, mes, día y ticker.

    Ruta resultante:
    raw/stocks/year=2026/month=04/day=02/AAPL.json
    """
    s3 = get_s3_client()

    record_date = date.fromisoformat(record["date"])
    ticker = record["ticker"]

    key = (
        f"raw/stocks/"
        f"year={record_date.year}/"
        f"month={str(record_date.month).zfill(2)}/"
        f"day={str(record_date.day).zfill(2)}/"
        f"{ticker}.json"
    )

    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(record, indent=2),
        ContentType="application/json"
    )

    logger.info(f"Guardado en S3: s3://{bucket}/{key}")
    return key