output "app_url" {
  value = "https://${var.domain_name}"
}

output "alb_dns_name" {
  value = aws_lb.main.dns_name
}

output "ecr_api_repository_url" {
  value = aws_ecr_repository.repos["api"].repository_url
}

output "ecr_web_repository_url" {
  value = aws_ecr_repository.repos["web"].repository_url
}

output "github_deploy_role_arn" {
  description = "Set as the AWS_DEPLOY_ROLE_ARN GitHub Actions variable."
  value       = aws_iam_role.github_deploy.arn
}

output "redis_endpoint" {
  value = aws_elasticache_replication_group.redis.primary_endpoint_address
}
