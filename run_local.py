import json
import sys
from pathlib import Path
from datetime import date

# Agregar el proyecto al path para los imports
sys.path.append(str(Path(__file__).parent))

from ingestion.ingestion_lambda.extractors import extract_batch

TICKERS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL",
    "META", "TSLA", "JPM",
    "SPY", "QQQ", "IWM"
]

if __name__ == "__main__":
    today = date.today()
    print(f"\n=== Extracción local: {today} ===\n")

    records = extract_batch(TICKERS, target_date=today)

    # Guardar resultado para inspección
    output = Path(f"output_test_{today}.json")
    with open(output, "w") as f:
        json.dump(records, f, indent=2)

    print(f"\n✓ {len(records)} registros extraídos")
    print(f"✓ Guardados en: {output}")
    print(f"\nMuestra — primer registro:")
    print(json.dumps(records[0], indent=2))

    # Validaciones básicas
    print("\n=== Validaciones ===")
    for r in records:
        assert r["close"] > 0,        f"Close inválido: {r['ticker']}"
        assert r["volume"] > 0,       f"Volumen inválido: {r['ticker']}"
        assert r["high"] >= r["low"], f"High < Low: {r['ticker']}"
    print("✓ Todas las validaciones pasaron")