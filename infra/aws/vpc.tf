# I-carney-002 — VPC + subnets + NAT.

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.13"

  name = "polaris-carney"
  cidr = var.vpc_cidr
  azs  = ["${var.aws_region}a", "${var.aws_region}b"]

  # Public subnets host the ALB (one per AZ).
  public_subnets = [
    cidrsubnet(var.vpc_cidr, 8, 0),  # 10.0.0.0/24
    cidrsubnet(var.vpc_cidr, 8, 1),  # 10.0.1.0/24
  ]

  # Private subnets host the EC2 workload (one per AZ; demo uses one EC2 in az a).
  private_subnets = [
    cidrsubnet(var.vpc_cidr, 8, 10), # 10.0.10.0/24
    cidrsubnet(var.vpc_cidr, 8, 11), # 10.0.11.0/24
  ]

  enable_nat_gateway     = true
  single_nat_gateway     = true # demo cost optimization; HA-NAT is a Phase-2 follow-up
  enable_vpn_gateway     = false
  enable_dns_hostnames   = true
  enable_dns_support     = true

  # Flow logs to CloudWatch with 30-day retention.
  enable_flow_log                                 = true
  create_flow_log_cloudwatch_log_group            = true
  create_flow_log_cloudwatch_iam_role             = true
  flow_log_cloudwatch_log_group_retention_in_days = 30
  flow_log_traffic_type                           = "ALL"
}
