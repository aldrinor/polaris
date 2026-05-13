# I-carney-002 — Terraform outputs for operator hand-off.

output "alb_dns_name" {
  description = "Internal AWS DNS name of the ALB (for CNAME debugging)."
  value       = aws_lb.polaris.dns_name
}

output "polaris_fqdn" {
  description = "Public hostname for the Carney demo."
  value       = local.polaris_fqdn
}

output "polaris_url" {
  description = "Public URL for the Carney demo."
  value       = "https://${local.polaris_fqdn}/"
}

output "ec2_instance_id" {
  description = "Instance ID for SSM Session Manager access."
  value       = aws_instance.polaris.id
}

output "ssm_start_session_command" {
  description = "Command to SSM into the EC2 host from operator workstation."
  value       = "aws ssm start-session --target ${aws_instance.polaris.id} --region ${var.aws_region}"
}

output "audit_bucket" {
  description = "S3 bucket holding daily exported audit bundles."
  value       = aws_s3_bucket.audit.id
}
