data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# Execution role: pulls images, ships logs, resolves SSM secrets at task start.
resource "aws_iam_role" "execution" {
  name               = "${var.project}-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "execution_secrets" {
  statement {
    actions   = ["ssm:GetParameters"]
    resources = local.secret_parameter_arns
  }

  # SecureString parameters use the AWS-managed aws/ssm key.
  statement {
    actions   = ["kms:Decrypt"]
    resources = ["arn:aws:kms:${var.aws_region}:${data.aws_caller_identity.current.account_id}:key/*"]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["ssm.${var.aws_region}.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "execution_secrets" {
  name   = "read-ssm-secrets"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution_secrets.json
}

# Task role: the app talks only to Supabase and Redis, so it needs no AWS
# permissions. It exists so containers never inherit the execution role.
resource "aws_iam_role" "task" {
  name               = "${var.project}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}
