# VPC endpoints so image pulls, log shipping, and secret fetches stay off the
# public internet (and off the NAT path).

resource "aws_security_group" "vpc_endpoints" {
  name_prefix = "${var.project}-vpce-"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTPS from inside the VPC"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  lifecycle {
    create_before_destroy = true
  }
}

locals {
  interface_endpoints = ["ecr.api", "ecr.dkr", "logs", "ssm"]
}

resource "aws_vpc_endpoint" "interface" {
  for_each = toset(local.interface_endpoints)

  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.aws_region}.${each.value}"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true

  tags = { Name = "${var.project}-${each.value}" }
}

# ECR image layers are served from S3.
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = aws_route_table.private[*].id

  tags = { Name = "${var.project}-s3" }
}
