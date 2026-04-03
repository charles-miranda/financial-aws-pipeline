import yfinance as yf
import pandas as pd
import logging
from datetime import datetime, date
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def extract_daily_ohlcv(
    ticker: str,
    target_date: Optional[date] = None
) -> Optional[dict]:
    """
    Extrae datos OHLCV de un ticker para una fecha.
    Retorna None si el mercado no operó ese día.
    """
    if target_date is None:
        target_date = date.today()

    logger.info(f"Extrayendo {ticker} para {target_date}")

    stock = yf.Ticker(ticker)
    hist = stock.history(
        start=target_date,
        end=target_date + pd.Timedelta(days=5),
        auto_adjust=True
    )

    if hist.empty:
        logger.warning(f"Sin datos para {ticker} en {target_date}")
        return None

    row = hist.iloc[0]
    actual_date = hist.index[0].date()

    return {
        "ticker":            ticker,
        "date":              str(actual_date),
        "open":              round(float(row["Open"]), 4),
        "high":              round(float(row["High"]), 4),
        "low":               round(float(row["Low"]), 4),
        "close":             round(float(row["Close"]), 4),
        "volume":            int(row["Volume"]),
        "ingested_at":       datetime.utcnow().isoformat() + "Z",
        "source":            "yahoo_finance",
        "extractor_version": "1.0.0"
    }


def extract_batch(
    tickers: list,
    target_date: Optional[date] = None
) -> list:
    """Extrae múltiples tickers. Continúa aunque uno falle."""
    results, errors = [], []

    for ticker in tickers:
        try:
            record = extract_daily_ohlcv(ticker, target_date)
            if record:
                results.append(record)
        except Exception as e:
            logger.error(f"Error en {ticker}: {e}")
            errors.append({"ticker": ticker, "error": str(e)})

    logger.info(f"Extraídos: {len(results)} | Errores: {len(errors)}")
    return results