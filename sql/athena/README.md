# Athena Queries

Base de datos: `de_project_financial`
Workgroup: `de-project-workgroup`
Resultados: `s3://financial-de-project-awsp1/logs/athena-results/`

## Tabla: gold_stocks

Apunta a: `s3://financial-de-project-awsp1/gold/stocks/`
Formato: CSV.gz particionado por ticker y año

## Columnas

| Columna | Tipo | Descripción |
|---|---|---|
| ticker | string | Símbolo bursátil |
| date | string | Fecha de cierre |
| open | double | Precio apertura |
| high | double | Precio máximo |
| low | double | Precio mínimo |
| close | double | Precio cierre |
| volume | bigint | Volumen negociado |
| ma7 | string | Media móvil 7 días |
| ma30 | string | Media móvil 30 días |
| daily_return | string | Retorno diario % |
| volatility_30 | string | Volatilidad 30 días |
| rsi14 | string | RSI 14 días |