variable "aws_region" {
  description = "AWS region for the private backup bucket."
  type        = string
}

variable "bucket_name" {
  description = "Globally unique S3 bucket name."
  type        = string
}

variable "noncurrent_version_expiration_days" {
  description = "Days to retain noncurrent object versions. Set to 0 to keep indefinitely."
  type        = number
  default     = 90
}

variable "force_destroy" {
  description = "Allow Terraform to delete a non-empty bucket. Keep false for backup safety."
  type        = bool
  default     = false
}
