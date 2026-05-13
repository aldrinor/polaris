# I-carney-002 — S3 audit bundle bucket with KMS-CMK encryption + TLS-only policy.

resource "aws_kms_key" "audit" {
  description             = "POLARIS Carney audit bundle encryption key"
  deletion_window_in_days = 7
  enable_key_rotation     = true
}

resource "aws_kms_alias" "audit" {
  name          = "alias/polaris-carney-audit"
  target_key_id = aws_kms_key.audit.key_id
}

resource "aws_s3_bucket" "audit" {
  bucket = "polaris-carney-audit-${data.aws_caller_identity.current.account_id}"
  # Codex diff iter-1 P2: force_destroy lets `terraform destroy` empty the
  # bucket before deletion. The demo-window stack is meant to be torn down
  # after the meeting; recover the bundles to local storage BEFORE destroy.
  force_destroy = true
}

resource "aws_s3_bucket_versioning" "audit" {
  bucket = aws_s3_bucket.audit.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "audit" {
  bucket = aws_s3_bucket.audit.id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.audit.arn
      sse_algorithm     = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "audit" {
  bucket                  = aws_s3_bucket.audit.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "audit" {
  bucket = aws_s3_bucket.audit.id

  rule {
    id     = "glacier-after-30d-expire-1y"
    status = "Enabled"
    filter {}

    transition {
      days          = 30
      storage_class = "GLACIER_IR"
    }

    expiration {
      days = 365
    }
  }
}

# TLS-only bucket policy: deny any GetObject/PutObject not via aws:SecureTransport.
data "aws_iam_policy_document" "audit_tls_only" {
  statement {
    sid     = "DenyNonTlsAccess"
    effect  = "Deny"
    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.audit.arn,
      "${aws_s3_bucket.audit.arn}/*",
    ]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "audit" {
  bucket = aws_s3_bucket.audit.id
  policy = data.aws_iam_policy_document.audit_tls_only.json
}
