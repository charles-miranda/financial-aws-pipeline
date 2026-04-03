# Lambda de ingesta
resource "aws_lambda_function" "ingestion" {
  function_name = "${var.project_name}-ingestion"
  role          = aws_iam_role.lambda_role.arn
  handler       = "handler.lambda_handler"
  runtime       = "python3.11"
  timeout       = 300
  memory_size   = 256

  s3_bucket = var.bucket_name
  s3_key    = "scripts/ingestion_lambda.zip"

  environment {
    variables = {
      S3_BUCKET_NAME = var.bucket_name
    }
  }

  tags = {
    Project     = var.project_name
    Environment = "dev"
  }
}

# Lambda de transformación
resource "aws_lambda_function" "transformation" {
  function_name = "${var.project_name}-transformation"
  role          = aws_iam_role.transformation_role.arn
  handler       = "handler.lambda_handler"
  runtime       = "python3.11"
  timeout       = 300
  memory_size   = 512

  s3_bucket = var.bucket_name
  s3_key    = "scripts/transformation_lambda.zip"

  environment {
    variables = {
      S3_BUCKET_NAME = var.bucket_name
    }
  }

  tags = {
    Project     = var.project_name
    Environment = "dev"
  }
}

# EventBridge rule
resource "aws_cloudwatch_event_rule" "daily_pipeline" {
  name                = "${var.project_name}-daily-ingestion"
  schedule_expression = "cron(0 21 ? * MON-FRI *)"
  state               = "ENABLED"
}

# Step Functions state machine
resource "aws_sfn_state_machine" "pipeline" {
  name     = "${var.project_name}-pipeline"
  role_arn = aws_iam_role.sfn_role.arn

  definition = jsonencode({
    Comment = "Financial data pipeline"
    StartAt = "Ingestion"
    States = {
      Ingestion = {
        Type     = "Task"
        Resource = aws_lambda_function.ingestion.arn
        ResultPath = "$.ingestion_result"
        Next     = "Transformation"
        Retry = [{
          ErrorEquals    = ["States.ALL"]
          IntervalSeconds = 30
          MaxAttempts    = 2
        }]
      }
      Transformation = {
        Type     = "Task"
        Resource = aws_lambda_function.transformation.arn
        ResultPath = "$.transformation_result"
        End      = true
        Retry = [{
          ErrorEquals    = ["States.ALL"]
          IntervalSeconds = 30
          MaxAttempts    = 2
        }]
      }
    }
  })

  tags = {
    Project     = var.project_name
    Environment = "dev"
  }
}

# EventBridge target apuntando a Step Functions
resource "aws_cloudwatch_event_target" "sfn_target" {
  rule     = aws_cloudwatch_event_rule.daily_pipeline.name
  arn      = aws_sfn_state_machine.pipeline.arn
  role_arn = aws_iam_role.events_role.arn
}