resource "aws_elasticache_subnet_group" "redis" {
  name       = "${var.project}-redis"
  subnet_ids = aws_subnet.private[*].id
}

# Single node: Redis is a queue + rate limiter here; the scheduler's
# stuck-upload sweep self-heals any in-flight jobs lost on restart.
resource "aws_elasticache_replication_group" "redis" {
  replication_group_id = "${var.project}-redis"
  description          = "Queue + rate limiting for ${var.project}"

  engine               = "redis"
  engine_version       = "7.1"
  node_type            = "cache.t4g.micro"
  num_cache_clusters   = 1
  parameter_group_name = "default.redis7"
  port                 = 6379

  subnet_group_name  = aws_elasticache_subnet_group.redis.name
  security_group_ids = [aws_security_group.redis.id]

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true

  automatic_failover_enabled = false
  apply_immediately          = true
}

locals {
  # ElastiCache certs chain to public Amazon CAs present in the runtime images.
  redis_url = "rediss://${aws_elasticache_replication_group.redis.primary_endpoint_address}:6379/0"
}
