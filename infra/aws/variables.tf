# I-carney-002 — Terraform variable declarations.
#
# Set values via `terraform.tfvars` (gitignored) — see
# `terraform.tfvars.example` for the canonical shape.

variable "aws_region" {
  description = "AWS region for the Carney demo. ca-central-1 (Montréal) for Canadian data residency."
  type        = string
  default     = "ca-central-1"
}

variable "tf_state_bucket" {
  description = "Pre-existing S3 bucket name for Terraform state. Must be in aws_region."
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for the demo VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "domain_name" {
  description = "Apex domain (e.g., example.ca). The deploy creates polaris.<domain_name>."
  type        = string
}

variable "route53_zone_name" {
  description = "Route 53 hosted zone name. Often equal to domain_name."
  type        = string
}

variable "polaris_subdomain" {
  description = "Subdomain hosting the Carney demo (full host = <polaris_subdomain>.<domain_name>)."
  type        = string
  default     = "polaris"
}

variable "ec2_instance_type" {
  description = "EC2 instance type. m7i-flex.4xlarge: 16 vCPU / 64 GB / 5 Gbps net."
  type        = string
  default     = "m7i-flex.4xlarge"
}

variable "root_volume_gb" {
  description = "Size of the EC2 root EBS volume (gp3)."
  type        = number
  default     = 200
}

variable "data_volume_gb" {
  description = "Size of the dedicated /var/lib/polaris data volume (gp3)."
  type        = number
  default     = 500
}

variable "polaris_repo_url" {
  description = "Git URL the EC2 cloud-init clones POLARIS from."
  type        = string
  default     = "https://github.com/aldrinor/polaris.git"
}

variable "polaris_repo_commit" {
  description = "Specific commit SHA the EC2 instance checks out — pinned for reproducibility."
  type        = string
}

variable "polaris_repo_branch" {
  description = "Branch to clone before checking out polaris_repo_commit (typically `polaris`)."
  type        = string
  default     = "polaris"
}

# Secrets — Terraform writes these to SSM Parameter Store as SecureString.
# Supply via `terraform.tfvars` (gitignored).

variable "openrouter_api_key" {
  description = "OpenRouter API key for pipeline-A LLM calls."
  type        = string
  sensitive   = true
}

variable "serper_api_key" {
  description = "Serper API key for live retrieval."
  type        = string
  sensitive   = true
}

variable "semantic_scholar_api_key" {
  description = "Optional Semantic Scholar API key."
  type        = string
  sensitive   = true
  default     = ""
}

variable "polaris_gpg_key_id" {
  description = "GPG fingerprint of the demo signing key (from bootstrap_gpg_demo_key.sh)."
  type        = string
  sensitive   = true
}

variable "polaris_gpg_pubkey" {
  description = "ASCII-armored public key body of the demo signing key (transparency endpoint)."
  type        = string
  sensitive   = false
}

variable "ebs_backup_retention_days" {
  description = "Daily EBS snapshot retention (days). 7 = Carney demo window."
  type        = number
  default     = 7
}
