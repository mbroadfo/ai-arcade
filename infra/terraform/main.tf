provider "aws" {
  region = var.aws_region
}

resource "aws_s3_bucket" "backup" {
  bucket        = var.bucket_name
  force_destroy = var.force_destroy

  tags = {
    Project = "ai-arcade"
    Purpose = "private-game-library-backup"
  }
}

resource "aws_s3_bucket_public_access_block" "backup" {
  bucket = aws_s3_bucket.backup.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "backup" {
  bucket = aws_s3_bucket.backup.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "backup" {
  bucket = aws_s3_bucket.backup.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "backup" {
  bucket = aws_s3_bucket.backup.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }

  }
}

resource "aws_s3_bucket_lifecycle_configuration" "backup" {
  count  = var.noncurrent_version_expiration_days > 0 ? 1 : 0
  bucket = aws_s3_bucket.backup.id

  depends_on = [aws_s3_bucket_versioning.backup]

  rule {
    id     = "expire-noncurrent-versions"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = var.noncurrent_version_expiration_days
    }
  }
}
