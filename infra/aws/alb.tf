# I-carney-002 — ALB + target groups + listener rules + WAF.

# ALB security group: 443 + 80 from anywhere.
resource "aws_security_group" "alb" {
  name        = "polaris-carney-alb"
  description = "POLARIS Carney ALB — public 80+443"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTP → 301 to HTTPS"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "ALB → EC2 webui:3000 + api:8000"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ----- ALB ----- #

resource "aws_lb" "polaris" {
  name                       = "polaris-carney"
  internal                   = false
  load_balancer_type         = "application"
  security_groups            = [aws_security_group.alb.id]
  subnets                    = module.vpc.public_subnets
  enable_deletion_protection = false # demo
  # Codex diff iter-2 P1: dualstack requires VPC + public subnet IPv6 CIDRs;
  # not enabled in this demo VPC. Default ipv4 is fine — Carney demo doesn't
  # require IPv6 reachability. IPv6 + dualstack are a Phase-2 follow-up.
  ip_address_type = "ipv4"

  # SSE keepalive: ALB closes idle conns after this many seconds. Pipeline-A
  # runs can take several minutes; SSE keepalive frames are emitted every 5s
  # by stream.py, so 300s comfortably covers the gap.
  idle_timeout = 300

  access_logs {
    bucket  = aws_s3_bucket.alb_logs.id
    prefix  = "alb"
    enabled = true
  }

  # Codex diff iter-1 P1-004: explicit ordering so the bucket policy is in
  # place BEFORE ELB enables access logging (otherwise apply fails with
  # AccessDenied trying to validate write access during ALB creation).
  depends_on = [aws_s3_bucket_policy.alb_logs]
}

# ----- Target groups ----- #

resource "aws_lb_target_group" "webui" {
  name        = "polaris-carney-webui"
  port        = 3000
  protocol    = "HTTP"
  vpc_id      = module.vpc.vpc_id
  target_type = "instance"

  health_check {
    path                = "/"
    matcher             = "200-399"
    interval            = 30
    timeout             = 10
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}

resource "aws_lb_target_group_attachment" "webui" {
  target_group_arn = aws_lb_target_group.webui.arn
  target_id        = aws_instance.polaris.id
  port             = 3000
}

resource "aws_lb_target_group" "api" {
  name        = "polaris-carney-api"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = module.vpc.vpc_id
  target_type = "instance"

  health_check {
    path                = "/health"
    matcher             = "200"
    interval            = 30
    timeout             = 10
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}

resource "aws_lb_target_group_attachment" "api" {
  target_group_arn = aws_lb_target_group.api.arn
  target_id        = aws_instance.polaris.id
  port             = 8000
}

# ----- HTTPS listener ----- #

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.polaris.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate_validation.polaris.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.webui.arn
  }
}

# Codex diff iter-1 P1-001: I-carney-005 has the frontend call /api/v6/*
# (browser-relative) which Next.js then REWRITES server-side to api:8000/*
# (the FastAPI surface does NOT serve /api/v6 prefix). Routing /api/v6/*
# directly at the ALB to FastAPI would 404 because FastAPI sees /api/v6/runs
# not /runs. So the only listener rule we need at the ALB is sending
# EVERYTHING to webui; Next.js handles the rewrite + SSE pass-through.
#
# Operator /health probe goes direct to the api target group (skipping
# Next.js) for clean liveness signals.
resource "aws_lb_listener_rule" "health" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 10

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }

  condition {
    path_pattern {
      values = ["/health"]
    }
  }
}

# ----- HTTP → 301 HTTPS redirect ----- #

resource "aws_lb_listener" "http_redirect" {
  load_balancer_arn = aws_lb.polaris.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"
    redirect {
      protocol    = "HTTPS"
      port        = "443"
      status_code = "HTTP_301"
    }
  }
}

# ----- WAF v2 ----- #

resource "aws_wafv2_web_acl" "polaris" {
  name  = "polaris-carney"
  scope = "REGIONAL"

  default_action {
    allow {}
  }

  rule {
    name     = "AWSManagedRulesCommonRuleSet"
    priority = 1
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "common-rule-set"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "AWSManagedRulesKnownBadInputsRuleSet"
    priority = 2
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
        vendor_name = "AWS"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "known-bad-inputs"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "polaris-carney-acl"
    sampled_requests_enabled   = true
  }
}

resource "aws_wafv2_web_acl_association" "polaris" {
  resource_arn = aws_lb.polaris.arn
  web_acl_arn  = aws_wafv2_web_acl.polaris.arn
}

# ----- ALB access log bucket ----- #

resource "aws_s3_bucket" "alb_logs" {
  bucket = "polaris-carney-alb-logs-${data.aws_caller_identity.current.account_id}"
  # Demo-window only; let terraform destroy clean up.
  force_destroy = true
}

resource "aws_s3_bucket_lifecycle_configuration" "alb_logs" {
  bucket = aws_s3_bucket.alb_logs.id

  rule {
    id     = "expire-30d"
    status = "Enabled"
    filter {} # empty filter = match all objects
    expiration {
      days = 30
    }
  }
}

# Allow the regional AWS Elastic Load Balancing service account to write logs.
# ca-central-1 ELB log delivery account: 985666609251 (per AWS docs as of 2026).
data "aws_iam_policy_document" "alb_logs_bucket" {
  statement {
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.alb_logs.arn}/alb/AWSLogs/${data.aws_caller_identity.current.account_id}/*"]

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::985666609251:root"]
    }
  }

  statement {
    actions   = ["s3:GetBucketAcl"]
    resources = [aws_s3_bucket.alb_logs.arn]
    principals {
      type        = "Service"
      identifiers = ["delivery.logs.amazonaws.com"]
    }
  }
}

resource "aws_s3_bucket_policy" "alb_logs" {
  bucket = aws_s3_bucket.alb_logs.id
  policy = data.aws_iam_policy_document.alb_logs_bucket.json
}
