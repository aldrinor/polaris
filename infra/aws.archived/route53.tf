# I-carney-002 — Route 53 A-alias to the ALB.
#
# Codex diff iter-2 P1: AAAA dropped because dualstack ALB needs VPC IPv6
# (not enabled in demo VPC). IPv6 reachability is a Phase-2 follow-up.

resource "aws_route53_record" "polaris" {
  zone_id = data.aws_route53_zone.polaris.zone_id
  name    = local.polaris_fqdn
  type    = "A"

  alias {
    name                   = aws_lb.polaris.dns_name
    zone_id                = aws_lb.polaris.zone_id
    evaluate_target_health = true
  }
}
