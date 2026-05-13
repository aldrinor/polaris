# I-carney-002 — SSM Parameter Store entries for POLARIS secrets.
#
# EC2 cloud-init pulls these with `aws ssm get-parameter --with-decryption`
# and writes them to /opt/polaris/.env at boot.

resource "aws_ssm_parameter" "openrouter_api_key" {
  name        = "/polaris/v6/openrouter_api_key"
  type        = "SecureString"
  value       = var.openrouter_api_key
  description = "OpenRouter API key for pipeline-A LLM calls"
}

resource "aws_ssm_parameter" "serper_api_key" {
  name        = "/polaris/v6/serper_api_key"
  type        = "SecureString"
  value       = var.serper_api_key
  description = "Serper API key for live retrieval"
}

resource "aws_ssm_parameter" "semantic_scholar_api_key" {
  count       = var.semantic_scholar_api_key == "" ? 0 : 1
  name        = "/polaris/v6/semantic_scholar_api_key"
  type        = "SecureString"
  value       = var.semantic_scholar_api_key
  description = "Optional Semantic Scholar API key"
}

resource "aws_ssm_parameter" "polaris_gpg_key_id" {
  name        = "/polaris/v6/polaris_gpg_key_id"
  type        = "SecureString"
  value       = var.polaris_gpg_key_id
  description = "GPG fingerprint of the Carney demo signing key"
}

# Public key body — fetched by the transparency endpoint (I-carney-003).
resource "aws_ssm_parameter" "polaris_gpg_pubkey" {
  name        = "/polaris/v6/polaris_gpg_pubkey"
  type        = "String"
  value       = var.polaris_gpg_pubkey
  description = "ASCII-armored public key for transparency.md"
}
