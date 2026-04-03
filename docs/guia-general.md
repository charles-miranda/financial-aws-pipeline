# Financial Data Pipeline en AWS — Guía General

## ¿Qué es este proyecto?

Un pipeline de datos end-to-end completamente automatizado que extrae precios financieros reales del mercado de valores (S&P 500 y ETFs), los transforma aplicando métricas técnicas financieras, y los almacena en un data lake en AWS listo para consultas SQL. Todo corre automáticamente cada día hábil sin intervención manual y dentro del Free Tier de AWS ($0 de costo).

---

## Arquitectura general

```
Yahoo Finance API
       ↓
  Lambda (ingesta)          — extrae datos diariamente
       ↓
   S3 raw/                  — JSON crudo tal como llega
       ↓
  Lambda (transformación)   — limpia y calcula métricas
       ↓
  S3 bronze/silver/gold/    — datos procesados en capas
       ↓
  Glue Data Catalog         — registra el esquema de las tablas
       ↓
       Athena                — consultas SQL sobre los datos
       
  Step Functions            — orquesta ingesta → transformación
  EventBridge               — dispara el pipeline cada día hábil
  CloudWatch                — monitoreo y alertas por email
  GitHub Actions            — CI/CD: deploy automático con cada push
  Terraform                 — infraestructura documentada como código
```

---

## Servicios AWS utilizados y para qué sirve cada uno

### S3 (Simple Storage Service)
Almacenamiento de objetos en la nube. Es el corazón del data lake. Guarda todos los datos del proyecto organizados en capas (raw, bronze, silver, gold). No requiere servidores, escala automáticamente y cobra por lo que usas.

### AWS Lambda
Funciones de código que corren en la nube sin necesidad de servidores. Usamos dos Lambdas escritas en Python:
- **Lambda de ingesta**: conecta con Yahoo Finance y guarda los datos en S3
- **Lambda de transformación**: lee los datos crudos, los limpia y calcula métricas financieras

### EventBridge
Servicio de scheduling y eventos. Actúa como el "reloj" del pipeline — dispara Step Functions automáticamente de lunes a viernes a las 9pm UTC (4pm hora de Nueva York, justo después del cierre del mercado).

### Step Functions
Orquestador de servicios AWS. Define el flujo del pipeline: primero corre la Lambda de ingesta, y si tiene éxito, corre la Lambda de transformación. Si algún paso falla, reintenta hasta 2 veces antes de detenerse.

### Glue Data Catalog
Catálogo de metadata. No mueve ni procesa datos — simplemente registra dónde están los archivos en S3 y cómo están estructurados (columnas, tipos de datos). Permite que Athena sepa cómo leer los archivos.

### Athena
Motor de queries SQL serverless. Permite consultar los datos directamente desde S3 usando SQL estándar, sin necesidad de cargarlos en una base de datos. Cobra por datos escaneados — a nuestro volumen es prácticamente $0.

### CloudWatch
Servicio de monitoreo. Recoge los logs de cada ejecución de Lambda y genera alarmas si algo falla. Configuramos alertas por email para ser notificados si el pipeline tiene errores.

### IAM (Identity and Access Management)
Gestión de permisos. Define qué puede hacer cada servicio. Aplicamos el principio de **least privilege** — cada servicio solo tiene acceso a lo que necesita. Lambda solo puede acceder a nuestro bucket S3, no a toda la cuenta.

### Terraform
Herramienta de infraestructura como código (IaC). Toda la infraestructura del proyecto está documentada en archivos `.tf` que permiten recrear todo el stack desde cero con un solo comando.

### GitHub Actions
CI/CD automatizado. Cada vez que se hace push a la rama `main`, GitHub Actions empaqueta automáticamente las Lambdas y las despliega en AWS.

---

## Arquitectura Medallion — las capas del data lake

El proyecto usa la arquitectura medallion, un estándar de la industria para organizar datos en capas de calidad creciente:

```
raw/     → JSON exacto tal como llega de Yahoo Finance. Nunca se modifica.
bronze/  → Mismo dato convertido a CSV.gz con tipos correctos.
silver/  → Limpio, sin duplicados, particionado por ticker y año.
gold/    → Con métricas calculadas listas para análisis.
```

La ventaja de este diseño es la **trazabilidad** — si un dato en gold es incorrecto, puedes rastrear hacia atrás hasta el JSON original en raw y saber exactamente qué pasó en cada transformación.

---

## Dataset

**Fuente**: Yahoo Finance API (gratuita, a través de la librería `yfinance`)

**Tickers monitoreados** (11 en total):
- Top acciones S&P 500: AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA, JPM
- ETFs de índices: SPY (S&P 500), QQQ (NASDAQ), IWM (Russell 2000)

**Datos por ticker (OHLCV)**:
- Open: precio al abrir el mercado (9:30am NY)
- High: precio máximo del día
- Low: precio mínimo del día
- Close: precio al cierre (4:00pm NY)
- Volume: cantidad de acciones negociadas

**Métricas calculadas en la capa gold**:
- MA7 / MA30: medias móviles de 7 y 30 días
- RSI14: Relative Strength Index de 14 días
- daily_return: retorno porcentual diario
- volatility_30: volatilidad de 30 días

---

## Flujo diario del pipeline

```
4:00pm NY (lunes a viernes)
        ↓
EventBridge dispara Step Functions
        ↓
Paso 1 — Lambda ingesta (~15 segundos)
  • Conecta con Yahoo Finance
  • Descarga OHLCV de 11 tickers
  • Guarda 11 archivos JSON en S3 raw/
        ↓
Paso 2 — Lambda transformación (~30 segundos)
  • Lee los 11 JSONs de raw/
  • Convierte a bronze/ (CSV.gz tipado)
  • Genera silver/ por ticker (limpio y particionado)
  • Calcula métricas y genera gold/ por ticker
        ↓
Datos disponibles en Athena para consultas SQL
```

---

## Costos

| Situación | Costo mensual estimado |
|---|---|
| Pipeline activo (Free Tier, primeros 12 meses) | $0.00 |
| Pipeline activo (después del Free Tier) | ~$0.003 |
| Pipeline apagado | $0.00 (Free Tier) / ~$0.003 (después) |

El almacenamiento actual en S3 es ~132 MB, principalmente los zips de las Lambdas.

---

## Cómo pausar y reactivar el pipeline

**Apagar** (EventBridge deja de disparar el pipeline):
```bash
aws events disable-rule --name "de-project-daily-ingestion" --region us-east-1
```

**Prender**:
```bash
aws events enable-rule --name "de-project-daily-ingestion" --region us-east-1
```

---

## Estructura del repositorio

```
financial-aws-pipeline/
├── ingestion/
│   └── ingestion_lambda/
│       ├── handler.py        — punto de entrada Lambda ingesta
│       ├── extractors.py     — lógica de extracción Yahoo Finance
│       └── utils.py          — cliente S3 y helpers
├── transformations/
│   └── lambda_jobs/
│       ├── handler.py        — punto de entrada Lambda transformación
│       └── transformer.py    — lógica bronze/silver/gold + métricas
├── sql/
│   └── athena/
│       ├── gold_queries.sql  — queries de ejemplo sobre gold_stocks
│       └── README.md         — documentación de tablas Athena
├── infra/
│   └── terraform/
│       ├── main.tf           — configuración del provider AWS
│       ├── variables.tf      — variables del proyecto
│       ├── s3.tf             — bucket S3 y configuración
│       ├── iam.tf            — roles y políticas IAM
│       ├── lambda.tf         — funciones Lambda, EventBridge, Step Functions
│       └── monitoring.tf     — alarmas CloudWatch y SNS
├── .github/
│   └── workflows/
│       └── deploy.yml        — CI/CD con GitHub Actions
├── .gitignore
├── requirements.txt
└── README.md
```

---

## Decisiones técnicas importantes

**¿Por qué Lambda + Pandas en vez de Glue?**
Glue no tiene Free Tier. Lambda con Pandas hace exactamente las mismas transformaciones para nuestro volumen de datos (11 tickers diarios) y cabe completamente dentro del Free Tier.

**¿Por qué CSV.gz en vez de Parquet?**
Parquet es el estándar en producción, pero requiere pyarrow que es una librería muy pesada (~200 MB descomprimida). Los límites de tamaño de Lambda (262 MB descomprimido) hacían imposible incluirla. CSV con compresión gzip es perfectamente válido para este volumen y Athena lo lee sin configuración adicional.

**¿Por qué Athena en vez de Redshift?**
Redshift no tiene Free Tier real. Athena es serverless, no requiere clusters ni mantenimiento, y cobra por datos escaneados — a nuestro volumen el costo es prácticamente cero.

**¿Por qué Step Functions?**
Garantiza que la transformación solo corra si la ingesta fue exitosa. Sin orquestación, si la ingesta falla podrías transformar datos incompletos o del día anterior sin darte cuenta.
