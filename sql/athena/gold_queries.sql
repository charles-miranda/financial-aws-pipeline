-- Query 1: Ver precios y métricas de todos los tickers
SELECT ticker, date, close, ma7, ma30, rsi14
FROM gold_stocks
ORDER BY ticker, date;

-- Query 2: Tickers con mayor precio de cierre
SELECT ticker, close
FROM gold_stocks
WHERE date = '2026-04-02'
ORDER BY CAST(close AS DOUBLE) DESC;

-- Query 3: Verificar conteo de registros por ticker
SELECT ticker, COUNT(*) as dias
FROM gold_stocks
GROUP BY ticker
ORDER BY ticker;