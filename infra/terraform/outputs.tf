output "bucket_name" {
  value       = aws_s3_bucket.backup.bucket
  description = "Private S3 backup bucket name."
}

output "bucket_arn" {
  value       = aws_s3_bucket.backup.arn
  description = "Private S3 backup bucket ARN."
}
