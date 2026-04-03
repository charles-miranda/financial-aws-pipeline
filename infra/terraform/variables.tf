variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "aws_profile" {
  description = "AWS CLI profile"
  type        = string
  default     = "de-project"
}

variable "bucket_name" {
  description = "S3 bucket name for the data lake"
  type        = string
  default     = "financial-de-project-awsp1"
}

variable "project_name" {
  description = "Project name used as prefix for all resources"
  type        = string
  default     = "de-project"
}

variable "alert_email" {
  description = "Email para recibir alertas del pipeline"
  type        = string
  default     = "tu-email@example.com"
}