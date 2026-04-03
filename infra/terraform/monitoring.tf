# Alarma si la Lambda de ingesta falla
resource "aws_cloudwatch_metric_alarm" "ingestion_errors" {
  alarm_name          = "${var.project_name}-ingestion-errors"
  alarm_description   = "Lambda de ingesta tuvo errores"
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"

  dimensions = {
    FunctionName = "${var.project_name}-ingestion"
  }

  alarm_actions = [aws_sns_topic.pipeline_alerts.arn]
}

# Alarma si la Lambda de transformación falla
resource "aws_cloudwatch_metric_alarm" "transformation_errors" {
  alarm_name          = "${var.project_name}-transformation-errors"
  alarm_description   = "Lambda de transformación tuvo errores"
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"

  dimensions = {
    FunctionName = "${var.project_name}-transformation"
  }

  alarm_actions = [aws_sns_topic.pipeline_alerts.arn]
}

# SNS topic para notificaciones por email
resource "aws_sns_topic" "pipeline_alerts" {
  name = "${var.project_name}-pipeline-alerts"
}

resource "aws_sns_topic_subscription" "email_alert" {
  topic_arn = aws_sns_topic.pipeline_alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}