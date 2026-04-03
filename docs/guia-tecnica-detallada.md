# Financial Data Pipeline en AWS — Guía Técnica Detallada

## Consideraciones previas

- Todo el proyecto corre dentro del **Free Tier de AWS** ($0 de costo)
- Sistema operativo usado: **Windows 10** con PowerShell
- Región AWS: **us-east-1** (Virginia del Norte) para todos los servicios
- Perfil AWS CLI: **de-project** (nunca el perfil default)
- El caracter de continuación de línea en PowerShell es el backtick `` ` `` (no `\` como en Linux)

---

## FASE 1 — Fundamentos y configuración del entorno

### Paso 1: Cuenta AWS + billing alerts

1. Crear cuenta en aws.amazon.com (requiere tarjeta de crédito)
2. Activar MFA en el usuario root: nombre de usuario → Security credentials → Assign MFA device
3. Activar billing alerts: Billing → Billing Preferences → activar "Receive Free Tier Usage Alerts" y "Receive Billing Alerts"
4. Crear alarma de gasto en CloudWatch (ejecutar después de configurar el CLI):

```bash
aws cloudwatch put-metric-alarm \
  --alarm-name "BillingAlert-10USD" \
  --metric-name EstimatedCharges \
  --namespace AWS/Billing \
  --statistic Maximum \
  --period 86400 \
  --threshold 10 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=Currency,Value=USD \
  --evaluation-periods 1 \
  --alarm-actions arn:aws:sns:us-east-1:TU_ACCOUNT_ID:billing-alerts \
  --region us-east-1
```

**Importante**: El usuario root solo para este setup inicial. Todo el trabajo diario se hace con usuario IAM.

---

### Paso 2: Usuario IAM + AWS CLI

**Crear usuario IAM:**
1. IAM Console → Users → Create user → nombre: `de-project-user`
2. NO marcar "Provide user access to the AWS Management Console"
3. Adjuntar política: `AdministratorAccess`
4. Generar Access Key: usuario → Security credentials → Create access key → CLI
5. Descargar CSV con las credenciales

**Instalar AWS CLI v2 en Windows:**
Descargar e instalar desde: `https://awscli.amazonaws.com/AWSCLIV2.msi`

```bash
# Verificar instalación
aws --version
# Salida: aws-cli/2.x.x Windows/10
```

**Configurar perfil del proyecto:**
```bash
aws configure --profile de-project
# AWS Access Key ID:     [del CSV descargado]
# AWS Secret Access Key: [del CSV descargado]
# Default region name:   us-east-1
# Default output format: json

# Verificar
aws sts get-caller-identity --profile de-project

# Setear variable de entorno para la sesión
$env:AWS_PROFILE = "de-project"

# Hacer permanente
[System.Environment]::SetEnvironmentVariable("AWS_PROFILE", "de-project", "User")
```

---

### Paso 3: Estructura de buckets S3

```bash
$BUCKET = "financial-de-project-awsp1"

# Crear bucket
aws s3api create-bucket --bucket $BUCKET --region us-east-1

# Bloquear acceso público
aws s3api put-public-access-block `
  --bucket $BUCKET `
  --public-access-block-configuration `
  "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

# Habilitar versioning
aws s3api put-bucket-versioning `
  --bucket $BUCKET `
  --versioning-configuration Status=Enabled

# Verificar
aws s3api get-bucket-versioning --bucket $BUCKET

# Crear estructura medallion
foreach ($prefix in @(
  "raw/stocks/", "raw/market_indices/",
  "bronze/stocks/", "silver/stocks/",
  "gold/stocks/", "gold/aggregates/",
  "scripts/", "logs/"
)) {
  aws s3api put-object --bucket $BUCKET --key "$prefix.keep"
  Write-Host "Creado: $prefix"
}

# Verificar estructura
aws s3 ls s3://$BUCKET/ --recursive
```

**Nota**: El nombre del bucket debe ser globalmente único en toda AWS. Solo letras minúsculas, números y guiones.

---

### Paso 4: Roles IAM para los servicios

```bash
# Política S3 restrictiva (solo nuestro bucket)
'{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["s3:GetObject","s3:PutObject","s3:DeleteObject","s3:ListBucket"],"Resource":["arn:aws:s3:::financial-de-project-awsp1","arn:aws:s3:::financial-de-project-awsp1/*"]}]}' | Out-File -FilePath "$env:TEMP\s3-policy.json" -Encoding ascii

aws iam create-policy `
  --policy-name "de-project-s3-policy" `
  --policy-document file://$env:TEMP\s3-policy.json

# Rol para Lambda de ingesta
'{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}' | Out-File -FilePath "$env:TEMP\lambda-trust.json" -Encoding ascii

aws iam create-role `
  --role-name "de-project-lambda-role" `
  --assume-role-policy-document file://$env:TEMP\lambda-trust.json

$ACCOUNT = (aws sts get-caller-identity --query Account --output text)

aws iam attach-role-policy `
  --role-name "de-project-lambda-role" `
  --policy-arn "arn:aws:iam::${ACCOUNT}:policy/de-project-s3-policy"

aws iam attach-role-policy `
  --role-name "de-project-lambda-role" `
  --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"

# Rol para transformación (Lambda + Glue Data Catalog)
'{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":["glue.amazonaws.com","lambda.amazonaws.com"]},"Action":"sts:AssumeRole"}]}' | Out-File -FilePath "$env:TEMP\glue-trust.json" -Encoding ascii

aws iam create-role `
  --role-name "de-project-glue-role" `
  --assume-role-policy-document file://$env:TEMP\glue-trust.json

aws iam attach-role-policy `
  --role-name "de-project-glue-role" `
  --policy-arn "arn:aws:iam::${ACCOUNT}:policy/de-project-s3-policy"

aws iam attach-role-policy `
  --role-name "de-project-glue-role" `
  --policy-arn "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"

# Verificar roles creados
aws iam list-roles --query "Roles[?starts_with(RoleName,'de-project')].[RoleName]" --output table
```

---

### Paso 5: Estructura del repositorio Git

```bash
mkdir financial-aws-pipeline
cd financial-aws-pipeline

mkdir infra\terraform
mkdir ingestion\ingestion_lambda
mkdir ingestion\tests
mkdir transformations\lambda_jobs
mkdir transformations\tests
mkdir sql\redshift sql\athena
mkdir monitoring docs

New-Item README.md
New-Item .env.example
New-Item requirements.txt
New-Item requirements-dev.txt

git init
git add .
git commit -m "chore: initial project structure"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/financial-aws-pipeline.git
git push -u origin main
```

**Contenido del .gitignore:**
```
__pycache__/
*.py[cod]
.venv/
venv/
.pytest_cache/
.env
*.env.local
.aws/
credentials
*.tfstate
*.tfstate.backup
.terraform/
*.zip
.idea/
.vscode/
.DS_Store
output_test_*.json
.cache/
lambda_package/
lambda_package_transform/
layer_pyarrow/
layer_pandas/
layer_all/
response.json
response_transform.json
*.csv.gz
infra/terraform/.terraform/
.terraform.lock.hcl
```

---

### Paso 6: Script Python local — extracción con yfinance

```bash
# Crear entorno virtual
python -m venv .venv
.venv\Scripts\activate

# Instalar dependencias
pip install yfinance pandas boto3 python-dotenv pyarrow
pip freeze > requirements.txt
```

**Archivo `ingestion/ingestion_lambda/extractors.py`:**
```python
import yfinance as yf
import pandas as pd
import logging
from datetime import datetime, date
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def extract_daily_ohlcv(ticker: str, target_date: Optional[date] = None) -> Optional[dict]:
    if target_date is None:
        target_date = date.today()
    logger.info(f"Extrayendo {ticker} para {target_date}")
    stock = yf.Ticker(ticker)
    hist = stock.history(start=target_date, end=target_date + pd.Timedelta(days=5), auto_adjust=True)
    if hist.empty:
        logger.warning(f"Sin datos para {ticker} en {target_date}")
        return None
    row = hist.iloc[0]
    actual_date = hist.index[0].date()
    return {
        "ticker": ticker, "date": str(actual_date),
        "open": round(float(row["Open"]), 4), "high": round(float(row["High"]), 4),
        "low": round(float(row["Low"]), 4), "close": round(float(row["Close"]), 4),
        "volume": int(row["Volume"]), "ingested_at": datetime.utcnow().isoformat() + "Z",
        "source": "yahoo_finance", "extractor_version": "1.0.0"
    }

def extract_batch(tickers: list, target_date: Optional[date] = None) -> list:
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
```

```bash
# Crear __init__.py en los módulos
New-Item ingestion\__init__.py
New-Item ingestion\ingestion_lambda\__init__.py

# Ejecutar prueba local
python run_local.py
```

---

## FASE 2 — Ingesta automática con Lambda + S3

### Archivos del código

**`ingestion/ingestion_lambda/utils.py`** — cliente S3:
```python
import boto3, json, logging
from datetime import date

logger = logging.getLogger(__name__)

def get_s3_client():
    return boto3.client("s3")

def save_to_s3_raw(record: dict, bucket: str) -> str:
    s3 = get_s3_client()
    record_date = date.fromisoformat(record["date"])
    ticker = record["ticker"]
    key = (f"raw/stocks/year={record_date.year}/"
           f"month={str(record_date.month).zfill(2)}/"
           f"day={str(record_date.day).zfill(2)}/{ticker}.json")
    s3.put_object(Bucket=bucket, Key=key, Body=json.dumps(record, indent=2), ContentType="application/json")
    logger.info(f"Guardado en S3: s3://{bucket}/{key}")
    return key
```

**`ingestion/ingestion_lambda/handler.py`** — punto de entrada Lambda:
```python
import json, logging, os
from datetime import date
from extractors import extract_batch  # noqa
from utils import save_to_s3_raw     # noqa

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TICKERS = ["AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA","JPM","SPY","QQQ","IWM"]

def lambda_handler(event, context):
    logger.info("Iniciando extracción diaria de datos financieros")
    bucket = os.environ["S3_BUCKET_NAME"]
    target_date = date.today()
    records = extract_batch(TICKERS, target_date=target_date)
    if not records:
        return {"statusCode": 200, "body": json.dumps({"message": "Sin datos para hoy", "records": 0})}
    saved_keys = [save_to_s3_raw(record, bucket) for record in records]
    logger.info(f"Pipeline completado: {len(saved_keys)} archivos guardados en S3")
    return {"statusCode": 200, "body": json.dumps({"message": "Extracción completada", "date": str(target_date), "records": len(saved_keys), "keys": saved_keys})}
```

### Empaquetar y desplegar

```bash
# Instalar dependencias Linux (importante: no Windows)
mkdir lambda_package
pip install yfinance pandas boto3 `
  --target lambda_package `
  --platform manylinux2014_x86_64 `
  --implementation cp `
  --python-version 3.11 `
  --only-binary=:all:

# Copiar código
Copy-Item ingestion\ingestion_lambda\handler.py lambda_package\
Copy-Item ingestion\ingestion_lambda\extractors.py lambda_package\
Copy-Item ingestion\ingestion_lambda\utils.py lambda_package\

# Comprimir
cd lambda_package
Compress-Archive -Path * -DestinationPath ..\ingestion_lambda.zip -Force
cd ..

# Subir a S3 (el zip supera los 50MB, límite de subida directa a Lambda)
aws s3 cp ingestion_lambda.zip s3://financial-de-project-awsp1/scripts/ingestion_lambda.zip

# Crear función Lambda
$ACCOUNT = (aws sts get-caller-identity --query Account --output text)

aws lambda create-function `
  --function-name "de-project-ingestion" `
  --runtime python3.11 `
  --role "arn:aws:iam::${ACCOUNT}:role/de-project-lambda-role" `
  --handler handler.lambda_handler `
  --code S3Bucket=financial-de-project-awsp1,S3Key=scripts/ingestion_lambda.zip `
  --timeout 300 `
  --memory-size 256 `
  --environment "Variables={S3_BUCKET_NAME=financial-de-project-awsp1}" `
  --region us-east-1

# Verificar que está activa
aws lambda get-function --function-name "de-project-ingestion" --query "Configuration.State"
```

### Configurar trigger automático con EventBridge

```bash
# Crear regla — lunes a viernes a las 9pm UTC (4pm NY)
aws events put-rule `
  --name "de-project-daily-ingestion" `
  --schedule-expression "cron(0 21 ? * MON-FRI *)" `
  --state ENABLED `
  --region us-east-1

# Conectar con Lambda
$ACCOUNT = (aws sts get-caller-identity --query Account --output text)

aws events put-targets `
  --rule "de-project-daily-ingestion" `
  --targets "Id=de-project-ingestion-target,Arn=arn:aws:lambda:us-east-1:${ACCOUNT}:function:de-project-ingestion"

# Dar permiso a EventBridge para invocar Lambda
aws lambda add-permission `
  --function-name "de-project-ingestion" `
  --statement-id "EventBridgeInvoke" `
  --action "lambda:InvokeFunction" `
  --principal "events.amazonaws.com" `
  --source-arn "arn:aws:events:us-east-1:${ACCOUNT}:rule/de-project-daily-ingestion"
```

### Probar y verificar

```bash
# Invocar manualmente
aws lambda invoke `
  --function-name "de-project-ingestion" `
  --payload '{}' `
  --cli-binary-format raw-in-base64-out `
  response.json

type response.json

# Verificar archivos en S3
aws s3 ls s3://financial-de-project-awsp1/raw/stocks/ --recursive

# Ver contenido de un archivo
aws s3 cp s3://financial-de-project-awsp1/raw/stocks/year=2026/month=04/day=02/AAPL.json -

# Ver logs en CloudWatch
aws logs describe-log-streams `
  --log-group-name "/aws/lambda/de-project-ingestion" `
  --order-by LastEventTime --descending --max-items 1 `
  --query "logStreams[0].logStreamName" --output text
```

---

## FASE 3 — Transformaciones con Lambda + Pandas

### Archivos del código

**`transformations/lambda_jobs/transformer.py`** — pipeline de transformación completo con:
- `read_raw_from_s3()`: lee JSONs de raw/ y los convierte a DataFrame
- `transform_to_bronze()`: tipos correctos, sin duplicados
- `read_historical_silver()`: lee historial acumulado por ticker
- `calculate_metrics()`: calcula MA7, MA30, RSI14, retornos, volatilidad
- `save_csv_gz_to_s3()`: guarda DataFrame como CSV.gz en S3
- `run_transformation()`: orquesta raw → bronze → silver → gold

**`transformations/lambda_jobs/handler.py`** — punto de entrada Lambda:
```python
import json, logging, os
from datetime import date, timedelta
from transformer import run_transformation

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    bucket = os.environ["S3_BUCKET_NAME"]
    target_date = date.today() - timedelta(days=1)
    if event.get("target_date"):
        target_date = date.fromisoformat(event["target_date"])
    logger.info(f"Transformando datos de {target_date}")
    result = run_transformation(bucket, target_date)
    return {"statusCode": 200, "body": json.dumps({"message": "Transformación completada", "date": str(target_date), "records": result["records"]})}
```

**Nota importante**: Los imports en los handlers de Lambda son directos (`from transformer import`) sin prefijos de módulo, porque dentro de Lambda todos los archivos están en el mismo directorio raíz.

### Empaquetar y desplegar

```bash
# Solo boto3 y pandas (sin pyarrow — demasiado pesado para Lambda)
mkdir lambda_package_transform
pip install boto3 pandas `
  --target lambda_package_transform `
  --platform manylinux2014_x86_64 `
  --implementation cp `
  --python-version 3.11 `
  --only-binary=:all:

Copy-Item transformations\lambda_jobs\transformer.py lambda_package_transform\
Copy-Item transformations\lambda_jobs\handler.py lambda_package_transform\

cd lambda_package_transform
Compress-Archive -Path * -DestinationPath ..\transformation_lambda.zip -Force
cd ..

# Subir a S3
aws s3 cp transformation_lambda.zip s3://financial-de-project-awsp1/scripts/transformation_lambda.zip

# Crear función Lambda
$ACCOUNT = (aws sts get-caller-identity --query Account --output text)

aws lambda create-function `
  --function-name "de-project-transformation" `
  --runtime python3.11 `
  --role "arn:aws:iam::${ACCOUNT}:role/de-project-glue-role" `
  --handler handler.lambda_handler `
  --code S3Bucket=financial-de-project-awsp1,S3Key=scripts/transformation_lambda.zip `
  --timeout 300 `
  --memory-size 512 `
  --environment "Variables={S3_BUCKET_NAME=financial-de-project-awsp1}" `
  --region us-east-1

# Verificar
aws lambda get-function --function-name "de-project-transformation" --query "Configuration.State"
```

### Probar

```bash
# Invocar con fecha específica
aws lambda invoke `
  --function-name "de-project-transformation" `
  --payload '{\"target_date\": \"2026-04-02\"}' `
  --cli-binary-format raw-in-base64-out `
  response_transform.json

type response_transform.json

# Verificar capas en S3
aws s3 ls s3://financial-de-project-awsp1/bronze/stocks/ --recursive
aws s3 ls s3://financial-de-project-awsp1/silver/stocks/ --recursive
aws s3 ls s3://financial-de-project-awsp1/gold/stocks/ --recursive

# Ver contenido de gold
aws s3 cp s3://financial-de-project-awsp1/gold/stocks/ticker=AAPL/year=2026/data.csv.gz aapl_gold.csv.gz
python -c "import gzip; print(gzip.open('aapl_gold.csv.gz','rt').read())"
```

---

## FASE 4 — Step Functions + Glue Catalog + Athena

### Step Functions — orquestación del pipeline

```bash
# Rol para Step Functions
'{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"states.amazonaws.com"},"Action":"sts:AssumeRole"}]}' | Out-File -FilePath "$env:TEMP\sfn-trust.json" -Encoding ascii

aws iam create-role `
  --role-name "de-project-sfn-role" `
  --assume-role-policy-document file://$env:TEMP\sfn-trust.json

'{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["lambda:InvokeFunction"],"Resource":"*"}]}' | Out-File -FilePath "$env:TEMP\sfn-policy.json" -Encoding ascii

$ACCOUNT = (aws sts get-caller-identity --query Account --output text)

aws iam create-policy `
  --policy-name "de-project-sfn-policy" `
  --policy-document file://$env:TEMP\sfn-policy.json

aws iam attach-role-policy `
  --role-name "de-project-sfn-role" `
  --policy-arn "arn:aws:iam::${ACCOUNT}:policy/de-project-sfn-policy"

# Crear state machine
$sfn = '{"Comment":"Financial data pipeline","StartAt":"Ingestion","States":{"Ingestion":{"Type":"Task","Resource":"arn:aws:lambda:us-east-1:' + $ACCOUNT + ':function:de-project-ingestion","ResultPath":"$.ingestion_result","Next":"Transformation","Retry":[{"ErrorEquals":["States.ALL"],"IntervalSeconds":30,"MaxAttempts":2}]},"Transformation":{"Type":"Task","Resource":"arn:aws:lambda:us-east-1:' + $ACCOUNT + ':function:de-project-transformation","ResultPath":"$.transformation_result","End":true,"Retry":[{"ErrorEquals":["States.ALL"],"IntervalSeconds":30,"MaxAttempts":2}]}}}'

$sfn | Out-File -FilePath "$env:TEMP\pipeline.json" -Encoding ascii

aws stepfunctions create-state-machine `
  --name "de-project-pipeline" `
  --definition file://$env:TEMP\pipeline.json `
  --role-arn "arn:aws:iam::${ACCOUNT}:role/de-project-sfn-role" `
  --region us-east-1
```

### Actualizar EventBridge para disparar Step Functions

```bash
$ACCOUNT = (aws sts get-caller-identity --query Account --output text)

# Rol para EventBridge
'{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"events.amazonaws.com"},"Action":"sts:AssumeRole"}]}' | Out-File -FilePath "$env:TEMP\events-trust.json" -Encoding ascii

aws iam create-role `
  --role-name "de-project-events-role" `
  --assume-role-policy-document file://$env:TEMP\events-trust.json

'{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["states:StartExecution"],"Resource":"*"}]}' | Out-File -FilePath "$env:TEMP\events-sfn-policy.json" -Encoding ascii

aws iam create-policy `
  --policy-name "de-project-events-sfn-policy" `
  --policy-document file://$env:TEMP\events-sfn-policy.json

aws iam attach-role-policy `
  --role-name "de-project-events-role" `
  --policy-arn "arn:aws:iam::${ACCOUNT}:policy/de-project-events-sfn-policy"

# Actualizar target de EventBridge → Step Functions
aws events put-targets `
  --rule "de-project-daily-ingestion" `
  --targets "Id=de-project-sfn-target,Arn=arn:aws:states:us-east-1:${ACCOUNT}:stateMachine:de-project-pipeline,RoleArn=arn:aws:iam::${ACCOUNT}:role/de-project-events-role"
```

### Probar el pipeline completo

```bash
$ACCOUNT = (aws sts get-caller-identity --query Account --output text)

# Iniciar ejecución manual
aws stepfunctions start-execution `
  --state-machine-arn "arn:aws:states:us-east-1:${ACCOUNT}:stateMachine:de-project-pipeline" `
  --input '{}'

# Verificar resultado (usar el executionArn que devolvió el comando anterior)
aws stepfunctions describe-execution `
  --execution-arn "TU_EXECUTION_ARN" `
  --query "status"
# Debe devolver "SUCCEEDED"
```

### Glue Data Catalog

```bash
# Crear base de datos
'{"Name":"de_project_financial","Description":"Financial data pipeline database"}' | Out-File -FilePath "$env:TEMP\glue-db.json" -Encoding ascii

aws glue create-database `
  --database-input file://$env:TEMP\glue-db.json `
  --region us-east-1

# Crear tabla gold_stocks
$TABLE = '{"Name":"gold_stocks","StorageDescriptor":{"Columns":[{"Name":"ticker","Type":"string"},{"Name":"date","Type":"string"},{"Name":"open","Type":"double"},{"Name":"high","Type":"double"},{"Name":"low","Type":"double"},{"Name":"close","Type":"double"},{"Name":"volume","Type":"bigint"},{"Name":"ingested_at","Type":"string"},{"Name":"source","Type":"string"},{"Name":"extractor_version","Type":"string"},{"Name":"ma7","Type":"string"},{"Name":"ma30","Type":"string"},{"Name":"daily_return","Type":"string"},{"Name":"volatility_30","Type":"string"},{"Name":"rsi14","Type":"string"}],"Location":"s3://financial-de-project-awsp1/gold/stocks/","InputFormat":"org.apache.hadoop.mapred.TextInputFormat","OutputFormat":"org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat","SerdeInfo":{"SerializationLibrary":"org.apache.hadoop.hive.serde2.OpenCSVSerde","Parameters":{"separatorChar":",","quoteChar":"\"","skip.header.line.count":"1"}}},"TableType":"EXTERNAL_TABLE"}'

$TABLE | Out-File -FilePath "$env:TEMP\glue-table.json" -Encoding ascii

aws glue create-table `
  --database-name "de_project_financial" `
  --table-input file://$env:TEMP\glue-table.json `
  --region us-east-1
```

### Athena

```bash
# Crear workgroup con bucket de resultados
aws athena create-work-group `
  --name "de-project-workgroup" `
  --configuration "ResultConfiguration={OutputLocation=s3://financial-de-project-awsp1/logs/athena-results/}" `
  --region us-east-1

# Ejecutar query
aws athena start-query-execution `
  --query-string "SELECT ticker, date, close, ma7, ma30, rsi14 FROM gold_stocks ORDER BY ticker, date" `
  --work-group "de-project-workgroup" `
  --query-execution-context "Database=de_project_financial" `
  --region us-east-1

# Verificar estado (usar el QueryExecutionId devuelto)
aws athena get-query-execution `
  --query-execution-id "TU_QUERY_EXECUTION_ID" `
  --query "QueryExecution.Status.State"

# Ver resultados
aws athena get-query-results `
  --query-execution-id "TU_QUERY_EXECUTION_ID" `
  --query "ResultSet.Rows[*].Data[*].VarCharValue" `
  --output table
```

---

## FASE 5 — Terraform IaC + GitHub Actions CI/CD

### Instalar Terraform en Windows

1. Descargar desde `https://developer.hashicorp.com/terraform/install` (Windows AMD64)
2. Extraer `terraform.exe` en `C:\terraform`
3. Agregar al PATH: Variables de entorno del sistema → Path → Nuevo → `C:\terraform`
4. Abrir nueva PowerShell y verificar:

```bash
terraform --version
```

### Archivos Terraform (en `infra/terraform/`)

- `main.tf` — configuración del provider AWS
- `variables.tf` — variables del proyecto (región, bucket, email alertas)
- `s3.tf` — bucket S3 con versioning y acceso público bloqueado
- `iam.tf` — todos los roles y políticas IAM del proyecto
- `lambda.tf` — funciones Lambda, EventBridge y Step Functions
- `monitoring.tf` — alarmas CloudWatch y SNS para notificaciones

```bash
# Inicializar Terraform (descarga provider AWS)
cd infra\terraform
terraform init

# Ver qué crearía (sin aplicar cambios)
terraform plan
```

**Nota**: El código Terraform documenta la infraestructura. Como la infraestructura ya fue creada manualmente, no se aplica con `terraform apply` para evitar conflictos. En un proyecto nuevo desde cero se usaría `terraform apply` desde el inicio.

### GitHub Actions CI/CD

**Configurar secrets en GitHub:**
1. Repositorio → Settings → Secrets and variables → Actions
2. Crear `AWS_ACCESS_KEY_ID` con el Access Key ID del usuario IAM
3. Crear `AWS_SECRET_ACCESS_KEY` con el Secret Access Key

**Archivo `.github/workflows/deploy.yml`** — se dispara con cada push a `main`:
1. Empaqueta la Lambda de ingesta con dependencias Linux
2. Empaqueta la Lambda de transformación con dependencias Linux
3. Sube los zips a S3
4. Actualiza las funciones Lambda en AWS

---

## Comandos de gestión del pipeline

### Apagar el pipeline (dejar de extraer datos automáticamente)
```bash
aws events disable-rule --name "de-project-daily-ingestion" --region us-east-1
```

### Prender el pipeline
```bash
aws events enable-rule --name "de-project-daily-ingestion" --region us-east-1
```

### Verificar espacio usado en S3
```bash
aws s3 ls s3://financial-de-project-awsp1 --recursive --human-readable --summarize
```

### Actualizar código de una Lambda manualmente
```bash
# Después de modificar el código, reempaquetar y subir
aws s3 cp ingestion_lambda.zip s3://financial-de-project-awsp1/scripts/ingestion_lambda.zip

aws lambda update-function-code `
  --function-name "de-project-ingestion" `
  --s3-bucket financial-de-project-awsp1 `
  --s3-key scripts/ingestion_lambda.zip
```

### Ver logs de la última ejecución
```bash
# Obtener el log stream más reciente
$STREAM = aws logs describe-log-streams `
  --log-group-name "/aws/lambda/de-project-ingestion" `
  --order-by LastEventTime --descending --max-items 1 `
  --query "logStreams[0].logStreamName" --output text

# Ver los logs
aws logs get-log-events `
  --log-group-name "/aws/lambda/de-project-ingestion" `
  --log-stream-name $STREAM `
  --query "events[*].message" --output text
```
