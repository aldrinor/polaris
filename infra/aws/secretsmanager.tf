# I-carney-004 — AWS Secrets Manager: JWT secret + static accounts + GPG
# private key. SSM Parameter Store still holds the LLM API keys (smaller
# secrets, lower rotation cadence); Secrets Manager carries the auth +
# bundle-signing substrate that requires automated rotation eligibility.

resource "aws_secretsmanager_secret" "jwt_secret" {
  name        = "polaris/v6/jwt_secret"
  description = "HS256 signing key for /auth/login JWTs"
  kms_key_id  = aws_kms_key.audit.arn  # reuse the audit CMK
}

# Auto-generated 64-byte URL-safe random value via Terraform's random_password.
resource "random_password" "jwt_secret" {
  length  = 64
  special = false # URL-safe
}

resource "aws_secretsmanager_secret_version" "jwt_secret" {
  secret_id     = aws_secretsmanager_secret.jwt_secret.id
  secret_string = random_password.jwt_secret.result
}

# ----- Static accounts YAML -----
resource "aws_secretsmanager_secret" "static_accounts" {
  name        = "polaris/v6/static_accounts_yaml"
  description = "POLARIS Carney demo reviewer + admin accounts (bcrypt hashed)"
  kms_key_id  = aws_kms_key.audit.arn
}

resource "aws_secretsmanager_secret_version" "static_accounts" {
  secret_id     = aws_secretsmanager_secret.static_accounts.id
  secret_string = var.static_accounts_yaml
}

# ----- GPG private key (armored ASCII) -----
resource "aws_secretsmanager_secret" "gpg_private_key" {
  name        = "polaris/v6/gpg_private_key_armored"
  description = "Armored ASCII secret key for Carney demo bundle signing"
  kms_key_id  = aws_kms_key.audit.arn
}

resource "aws_secretsmanager_secret_version" "gpg_private_key" {
  secret_id     = aws_secretsmanager_secret.gpg_private_key.id
  secret_string = var.gpg_private_key_armored
}

# Extends the EC2 IAM role from ec2.tf with Secrets Manager read on the
# specific secret ARNs (NOT Resource: "*").
data "aws_iam_policy_document" "secretsmanager_read" {
  statement {
    actions = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
    resources = [
      aws_secretsmanager_secret.jwt_secret.arn,
      aws_secretsmanager_secret.static_accounts.arn,
      aws_secretsmanager_secret.gpg_private_key.arn,
    ]
  }
  # KMS Decrypt for the CMK that wraps the secrets.
  statement {
    actions   = ["kms:Decrypt"]
    resources = [aws_kms_key.audit.arn]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["secretsmanager.${var.aws_region}.amazonaws.com"]
    }
  }
}

resource "aws_iam_policy" "secretsmanager_read" {
  name   = "polaris-carney-secretsmanager-read"
  policy = data.aws_iam_policy_document.secretsmanager_read.json
}

resource "aws_iam_role_policy_attachment" "secretsmanager_read" {
  role       = aws_iam_role.polaris_ec2.name
  policy_arn = aws_iam_policy.secretsmanager_read.arn
}
