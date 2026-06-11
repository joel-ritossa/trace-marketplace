resource "aws_ecs_cluster" "main" {
  name = var.project

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_cloudwatch_log_group" "services" {
  for_each = toset(["api", "worker", "scheduler", "web"])

  name              = "/ecs/${var.project}/${each.value}"
  retention_in_days = 30
}

locals {
  api_image = "${aws_ecr_repository.repos["api"].repository_url}:${var.image_tag}"
  web_image = "${aws_ecr_repository.repos["web"].repository_url}:${var.image_tag}"

  # Mirrors x-backend-env in docker-compose.yml. DEV_ROUTES stays unset:
  # the safe default is false.
  backend_env = [
    { name = "REDIS_URL", value = local.redis_url },
    { name = "SUPABASE_URL", value = var.supabase_url },
  ]

  backend_secrets = [
    { name = "DATABASE_URL", valueFrom = aws_ssm_parameter.database_url.arn },
    { name = "SUPABASE_SERVICE_ROLE_KEY", valueFrom = aws_ssm_parameter.supabase_service_role_key.arn },
  ]
}

# --- Task definitions -------------------------------------------------------
# CI registers new revisions with git-SHA image tags; these are the initial
# shapes. Services below ignore task_definition drift so the two don't fight.

resource "aws_ecs_task_definition" "api" {
  family                   = "${var.project}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([{
    name         = "api"
    image        = local.api_image
    essential    = true
    portMappings = [{ containerPort = 8000, protocol = "tcp" }]
    environment = concat(local.backend_env, [
      { name = "WEB_ORIGIN", value = "https://${var.domain_name}" },
    ])
    secrets = local.backend_secrets
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.services["api"].name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "api"
      }
    }
  }])
}

resource "aws_ecs_task_definition" "worker" {
  family                   = "${var.project}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 1024
  memory                   = 2048
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([{
    name        = "worker"
    image       = local.api_image
    essential   = true
    command     = ["taskiq", "worker", "app.worker:broker", "--max-async-tasks", "4"]
    environment = local.backend_env
    secrets     = local.backend_secrets
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.services["worker"].name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "worker"
      }
    }
  }])
}

resource "aws_ecs_task_definition" "scheduler" {
  family                   = "${var.project}-scheduler"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([{
    name        = "scheduler"
    image       = local.api_image
    essential   = true
    command     = ["taskiq", "scheduler", "app.worker.scheduler:scheduler"]
    environment = local.backend_env
    secrets     = local.backend_secrets
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.services["scheduler"].name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "scheduler"
      }
    }
  }])
}

resource "aws_ecs_task_definition" "web" {
  family                   = "${var.project}-web"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([{
    name         = "web"
    image        = local.web_image
    essential    = true
    portMappings = [{ containerPort = 3000, protocol = "tcp" }]
    # NEXT_PUBLIC_* values are baked in at image build time (CI build args);
    # server-side code falls back to the public Supabase URL, so no
    # SUPABASE_INTERNAL_URL is needed against hosted Supabase.
    environment = []
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.services["web"].name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "web"
      }
    }
  }])
}

# --- Services ----------------------------------------------------------------

resource "aws_ecs_service" "api" {
  name            = "api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  health_check_grace_period_seconds = 60

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.api.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  lifecycle {
    ignore_changes = [task_definition]
  }

  depends_on = [aws_lb_listener.https]
}

resource "aws_ecs_service" "worker" {
  name            = "worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.backend.id]
    assign_public_ip = false
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  lifecycle {
    ignore_changes = [task_definition]
  }
}

resource "aws_ecs_service" "scheduler" {
  name            = "scheduler"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.scheduler.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.backend.id]
    assign_public_ip = false
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  lifecycle {
    ignore_changes = [task_definition]
  }
}

resource "aws_ecs_service" "web" {
  name            = "web"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.web.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  health_check_grace_period_seconds = 60

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.web.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.web.arn
    container_name   = "web"
    container_port   = 3000
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  lifecycle {
    ignore_changes = [task_definition]
  }

  depends_on = [aws_lb_listener.https]
}
