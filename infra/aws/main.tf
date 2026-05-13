# I-carney-002 — AWS Canada Central (ca-central-1) root Terraform module.
#
# Provisions the Carney production environment: VPC + EC2 + ALB + ACM +
# Route 53 + SSM Parameter Store + S3 audit bucket + EBS backups. The
# docker compose v6 stack from I-carney-005 runs on the EC2 instance.
#
# Tear down with `terraform destroy` after the Carney demo window.

terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
    # I-carney-004: random_password for the JWT secret in Secrets Manager.
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # S3 backend for state. Bootstrap the bucket separately (chicken-and-egg).
  # Bucket must exist BEFORE `terraform init`. See infra/aws/README.md.
  backend "s3" {
    # `bucket`, `region`, `key` set via terraform init -backend-config=...
    encrypt = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = "POLARIS"
      Issue     = "I-carney-002"
      Workload  = "carney-demo"
      ManagedBy = "terraform"
    }
  }
}

# Pull the AWS account ID + caller for resource naming + IAM policy doc.
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
