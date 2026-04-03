import boto3
import pandas as pd
import json
import logging
import os
import gzip
from io import BytesIO, StringIO
from datetime import date

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def get_s3_client():
    return boto3.client("s3")


def read_raw_from_s3(bucket: str, target_date: date) -> pd.DataFrame:
    """
    Lee todos los JSONs de raw/ para una fecha específica
    y los convierte en un DataFrame.
    """
    s3 = get_s3_client()
    prefix = (
        f"raw/stocks/"
        f"year={target_date.year}/"
        f"month={str(target_date.month).zfill(2)}/"
        f"day={str(target_date.day).zfill(2)}/"
    )

    response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)

    if "Contents" not in response:
        logger.warning(f"No hay archivos en {prefix}")
        return pd.DataFrame()

    records = []
    for obj in response["Contents"]:
        if obj["Key"].endswith(".json"):
            body = s3.get_object(Bucket=bucket, Key=obj["Key"])["Body"].read()
            records.append(json.loads(body))

    df = pd.DataFrame(records)
    logger.info(f"Leídos {len(df)} registros de raw/")
    return df


def transform_to_bronze(df: pd.DataFrame) -> pd.DataFrame:
    """
    Bronze: tipos correctos, columnas limpias.
    Sin modificar los valores, solo estructura.
    """
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["open"] = df["open"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["close"] = df["close"].astype(float)
    df["volume"] = df["volume"].astype(int)
    df["ingested_at"] = pd.to_datetime(df["ingested_at"])
    df = df.drop_duplicates(subset=["ticker", "date"])
    logger.info(f"Bronze: {len(df)} registros")
    return df


def read_historical_silver(bucket: str, ticker: str) -> pd.DataFrame:
    """
    Lee el historial existente de silver/ para un ticker.
    Necesario para calcular moving averages con datos históricos.
    """
    s3 = get_s3_client()
    prefix = f"silver/stocks/ticker={ticker}/"
    response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)

    if "Contents" not in response:
        return pd.DataFrame()

    dfs = []
    for obj in response["Contents"]:
        if obj["Key"].endswith(".csv.gz"):
            body = s3.get_object(Bucket=bucket, Key=obj["Key"])["Body"].read()
            with gzip.open(BytesIO(body), "rt") as f:
                dfs.append(pd.read_csv(f, parse_dates=["date"]))

    if not dfs:
        return pd.DataFrame()

    return pd.concat(dfs).drop_duplicates(subset=["date"]).sort_values("date")


def calculate_metrics(df_ticker: pd.DataFrame) -> pd.DataFrame:
    """
    Gold: calcula métricas financieras sobre el historial completo.
    - MA7, MA30: moving averages de 7 y 30 días
    - daily_return: retorno porcentual diario
    - volatility_30: volatilidad de 30 días
    - RSI14: Relative Strength Index de 14 días
    """
    df = df_ticker.sort_values("date").copy()

    df["ma7"] = df["close"].rolling(window=7).mean().round(4)
    df["ma30"] = df["close"].rolling(window=30).mean().round(4)
    df["daily_return"] = df["close"].pct_change().round(6)
    df["volatility_30"] = df["daily_return"].rolling(window=30).std().round(6)

    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df["rsi14"] = (100 - (100 / (1 + rs))).round(2)

    logger.info(f"Métricas calculadas para {df['ticker'].iloc[0]}")
    return df


def save_csv_gz_to_s3(df: pd.DataFrame, bucket: str, key: str):
    """Guarda un DataFrame como CSV comprimido con gzip en S3."""
    s3 = get_s3_client()
    buffer = BytesIO()
    with gzip.open(buffer, "wt", encoding="utf-8") as f:
        df.to_csv(f, index=False)
    buffer.seek(0)
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=buffer.getvalue(),
        ContentEncoding="gzip",
        ContentType="text/csv"
    )
    logger.info(f"Guardado: s3://{bucket}/{key}")


def run_transformation(bucket: str, target_date: date):
    """
    Orquesta el pipeline completo raw -> bronze -> silver -> gold.
    """
    logger.info(f"Iniciando transformación para {target_date}")

    df_raw = read_raw_from_s3(bucket, target_date)
    if df_raw.empty:
        logger.warning("Sin datos para transformar")
        return {"records": 0}

    # Bronze
    df_bronze = transform_to_bronze(df_raw)
    bronze_key = (
        f"bronze/stocks/"
        f"year={target_date.year}/"
        f"month={str(target_date.month).zfill(2)}/"
        f"day={str(target_date.day).zfill(2)}/"
        f"data.csv.gz"
    )
    save_csv_gz_to_s3(df_bronze, bucket, bronze_key)

    # Silver y Gold por ticker
    for ticker in df_bronze["ticker"].unique():
        df_ticker_new = df_bronze[df_bronze["ticker"] == ticker].copy()

        df_historical = read_historical_silver(bucket, ticker)
        if not df_historical.empty:
            df_ticker_full = pd.concat([df_historical, df_ticker_new])
            df_ticker_full = df_ticker_full.drop_duplicates(subset=["date"])
        else:
            df_ticker_full = df_ticker_new

        df_ticker_full = df_ticker_full.sort_values("date")

        silver_key = (
            f"silver/stocks/ticker={ticker}/"
            f"year={target_date.year}/"
            f"data.csv.gz"
        )
        save_csv_gz_to_s3(df_ticker_full, bucket, silver_key)

        df_gold = calculate_metrics(df_ticker_full)
        gold_key = (
            f"gold/stocks/ticker={ticker}/"
            f"year={target_date.year}/"
            f"data.csv.gz"
        )
        save_csv_gz_to_s3(df_gold, bucket, gold_key)

    logger.info(f"Transformación completada: {len(df_bronze['ticker'].unique())} tickers")
    return {"records": len(df_bronze)}