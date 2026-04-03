import json
import logging
import os
from datetime import date, timedelta

from transformer import run_transformation

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    """
    Punto de entrada de la Lambda de transformación.
    Lee los datos raw de ayer y los transforma a bronze/silver/gold.
    """
    bucket = os.environ["S3_BUCKET_NAME"]

    # Por defecto transforma los datos del día anterior
    target_date = date.today() - timedelta(days=1)

    # Permite sobrescribir la fecha desde el evento (útil para reprocesar)
    if event.get("target_date"):
        target_date = date.fromisoformat(event["target_date"])

    logger.info(f"Transformando datos de {target_date}")

    result = run_transformation(bucket, target_date)

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Transformación completada",
            "date": str(target_date),
            "records": result["records"]
        })
    }