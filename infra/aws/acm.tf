# I-carney-002 — ACM cert with Route 53 DNS validation.

data "aws_route53_zone" "polaris" {
  name         = var.route53_zone_name
  private_zone = false
}

locals {
  polaris_fqdn = "${var.polaris_subdomain}.${var.domain_name}"
}

resource "aws_acm_certificate" "polaris" {
  domain_name               = local.polaris_fqdn
  subject_alternative_names = ["*.${local.polaris_fqdn}"]
  validation_method         = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "acm_validation" {
  for_each = {
    for dvo in aws_acm_certificate.polaris.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  }

  allow_overwrite = true
  name            = each.value.name
  records         = [each.value.record]
  ttl             = 60
  type            = each.value.type
  zone_id         = data.aws_route53_zone.polaris.zone_id
}

resource "aws_acm_certificate_validation" "polaris" {
  certificate_arn         = aws_acm_certificate.polaris.arn
  validation_record_fqdns = [for r in aws_route53_record.acm_validation : r.fqdn]
}
