import json
import logging
import os
from datetime import date

# noqa
from extractors import extract_batch # noqa
from utils import save_to_s3_raw    # noqa

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Tickers a extraer diariamente
TICKERS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL",
    "META", "TSLA", "JPM",
    "SPY", "QQQ", "IWM"
]


def lambda_handler(event, context):
    """
    Punto de entrada de Lambda.
    AWS llama esta función automáticamente según el trigger.

    event   → datos del evento que disparó la Lambda (en nuestro caso EventBridge)
    context → información del entorno de ejecución (memoria, tiempo restante, etc.)
    """
    logger.info("Iniciando extracción diaria de datos financieros")

    bucket = os.environ["S3_BUCKET_NAME"]
    target_date = date.today()

    # Extraer datos de todos los tickers
    records = extract_batch(TICKERS, target_date=target_date)

    if not records:
        logger.warning("No se extrajeron datos — posible feriado o fin de semana")
        return {
            "statusCode": 200,
            "body": json.dumps({"message": "Sin datos para hoy", "records": 0})
        }

    # Guardar cada ticker en S3
    saved_keys = []
    for record in records:
        key = save_to_s3_raw(record, bucket)
        saved_keys.append(key)

    logger.info(f"Pipeline completado: {len(saved_keys)} archivos guardados en S3")

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Extracción completada",
            "date": str(target_date),
            "records": len(saved_keys),
            "keys": saved_keys
        })
    }