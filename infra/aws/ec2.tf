# I-carney-002 — Single EC2 workload host.

# Latest Ubuntu 24.04 LTS AMI (Canonical's public publisher).
data "aws_ami" "ubuntu_2404" {
  most_recent = true
  owners      = ["099720109477"] # Canonical
  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }
  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# ----- IAM ----- #

data "aws_iam_policy_document" "ec2_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "polaris_ec2" {
  name               = "polaris-carney-ec2"
  assume_role_policy = data.aws_iam_policy_document.ec2_trust.json
}

# SSM Session Manager — Claude / operator SSH replacement.
resource "aws_iam_role_policy_attachment" "ssm_managed" {
  role       = aws_iam_role.polaris_ec2.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# Read POLARIS secrets from SSM Parameter Store.
data "aws_iam_policy_document" "ssm_read" {
  statement {
    actions = ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"]
    resources = [
      "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/polaris/v6/*",
    ]
  }
  statement {
    actions   = ["kms:Decrypt"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["ssm.${var.aws_region}.amazonaws.com"]
    }
  }
}

resource "aws_iam_policy" "ssm_read" {
  name   = "polaris-carney-ssm-read"
  policy = data.aws_iam_policy_document.ssm_read.json
}

resource "aws_iam_role_policy_attachment" "ssm_read" {
  role       = aws_iam_role.polaris_ec2.name
  policy_arn = aws_iam_policy.ssm_read.arn
}

# Write daily audit-bundle exports to the S3 bucket.
# Codex diff iter-1 P1-003: bucket is KMS-CMK encrypted, so PutObject requires
# kms:GenerateDataKey on the audit key. Without this, S3 PutObject fails with
# AccessDenied — the iam policy must grant both S3 actions AND the KMS data-key
# generation actions on aws_kms_key.audit.
data "aws_iam_policy_document" "s3_audit_write" {
  statement {
    actions   = ["s3:PutObject", "s3:GetObject", "s3:ListBucket"]
    resources = [aws_s3_bucket.audit.arn, "${aws_s3_bucket.audit.arn}/*"]
  }
  statement {
    actions   = ["kms:Encrypt", "kms:GenerateDataKey", "kms:Decrypt", "kms:DescribeKey"]
    resources = [aws_kms_key.audit.arn]
  }
}

resource "aws_iam_policy" "s3_audit_write" {
  name   = "polaris-carney-s3-audit-write"
  policy = data.aws_iam_policy_document.s3_audit_write.json
}

resource "aws_iam_role_policy_attachment" "s3_audit_write" {
  role       = aws_iam_role.polaris_ec2.name
  policy_arn = aws_iam_policy.s3_audit_write.arn
}

resource "aws_iam_instance_profile" "polaris_ec2" {
  name = "polaris-carney-ec2"
  role = aws_iam_role.polaris_ec2.name
}

# ----- Security group ----- #
# No inbound 22, no inbound 80/443 from internet — ALB is the only public surface.
# ALB's SG is permitted on 3000 + 8000; outbound 443 to anywhere (Docker pulls,
# LLM API egress).

resource "aws_security_group" "polaris_ec2" {
  name        = "polaris-carney-ec2"
  description = "POLARIS Carney workload — ALB-only inbound on 3000+8000"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description     = "webui from ALB"
    from_port       = 3000
    to_port         = 3000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  ingress {
    description     = "api from ALB (HTTP + SSE)"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    description = "all outbound (Docker pulls, LLM API calls)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ----- EC2 instance ----- #

resource "aws_instance" "polaris" {
  ami                    = data.aws_ami.ubuntu_2404.id
  instance_type          = var.ec2_instance_type
  iam_instance_profile   = aws_iam_instance_profile.polaris_ec2.name
  subnet_id              = module.vpc.private_subnets[0]
  vpc_security_group_ids = [aws_security_group.polaris_ec2.id]
  user_data              = templatefile("${path.module}/cloud-init.sh", {
    aws_region          = var.aws_region
    polaris_repo_url    = var.polaris_repo_url
    polaris_repo_branch = var.polaris_repo_branch
    polaris_repo_commit = var.polaris_repo_commit
    audit_bucket_name   = aws_s3_bucket.audit.id
  })

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.root_volume_gb
    delete_on_termination = false
    encrypted             = true
  }

  metadata_options {
    http_tokens               = "required"   # IMDSv2 only
    http_put_response_hop_limit = 2
  }

  monitoring = true

  tags = {
    Name = "polaris-carney"
  }

  # Codex diff iter-1 P1-002: cloud-init.sh runs `aws ssm get-parameter ...`
  # under `set -e`. If the instance launches before the SSM parameters exist
  # or before the SSM read IAM policy is attached to the role, the user-data
  # script fails and compose never starts. Explicit depends_on forces both
  # secrets-in-Parameter-Store + IAM permission to be in place at boot.
  depends_on = [
    aws_ssm_parameter.openrouter_api_key,
    aws_ssm_parameter.serper_api_key,
    aws_ssm_parameter.polaris_gpg_key_id,
    aws_ssm_parameter.polaris_gpg_pubkey,
    aws_iam_role_policy_attachment.ssm_managed,
    aws_iam_role_policy_attachment.ssm_read,
    aws_iam_role_policy_attachment.s3_audit_write,
  ]
}

# Dedicated data volume mounted at /var/lib/polaris on the EC2 host —
# survives instance replacement.
resource "aws_ebs_volume" "polaris_data" {
  availability_zone = "${var.aws_region}a"
  size              = var.data_volume_gb
  type              = "gp3"
  encrypted         = true

  tags = {
    Name = "polaris-carney-data"
  }
}

resource "aws_volume_attachment" "polaris_data" {
  device_name = "/dev/sdf"
  volume_id   = aws_ebs_volume.polaris_data.id
  instance_id = aws_instance.polaris.id
}

# ----- Daily EBS snapshots via AWS Backup ----- #

resource "aws_backup_vault" "polaris" {
  name = "polaris-carney"
}

resource "aws_backup_plan" "polaris_daily" {
  name = "polaris-carney-daily"

  rule {
    rule_name         = "daily-2am-utc"
    target_vault_name = aws_backup_vault.polaris.name
    schedule          = "cron(0 2 * * ? *)"

    lifecycle {
      delete_after = var.ebs_backup_retention_days
    }
  }
}

data "aws_iam_policy_document" "backup_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["backup.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "backup" {
  name               = "polaris-carney-backup"
  assume_role_policy = data.aws_iam_policy_document.backup_trust.json
}

resource "aws_iam_role_policy_attachment" "backup_managed" {
  role       = aws_iam_role.backup.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSBackupServiceRolePolicyForBackup"
}

resource "aws_backup_selection" "polaris_volumes" {
  iam_role_arn = aws_iam_role.backup.arn
  name         = "polaris-carney-volumes"
  plan_id      = aws_backup_plan.polaris_daily.id

  resources = [
    aws_instance.polaris.arn,
    aws_ebs_volume.polaris_data.arn,
  ]
}
