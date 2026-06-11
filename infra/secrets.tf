# Secret values are set out-of-band after the first apply (see README):
#   aws ssm put-parameter --name /trace-marketplace/database-url \
#     --type SecureString --overwrite --value '<supabase pooler url>'
# Terraform only owns the parameter shells, never the values.

resource "aws_ssm_parameter" "database_url" {
  name  = "/${var.project}/database-url"
  type  = "SecureString"
  value = "REPLACE_ME"

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "supabase_service_role_key" {
  name  = "/${var.project}/supabase-service-role-key"
  type  = "SecureString"
  value = "REPLACE_ME"

  lifecycle {
    ignore_changes = [value]
  }
}

# LLM provider keys for the analysis judge/critics (worker). Same
# out-of-band value flow as above.
resource "aws_ssm_parameter" "llm_api_keys" {
  for_each = toset(["openai-api-key", "anthropic-api-key", "openrouter-api-key"])

  name  = "/${var.project}/${each.value}"
  type  = "SecureString"
  value = "REPLACE_ME"

  lifecycle {
    ignore_changes = [value]
  }
}

locals {
  secret_parameter_arns = concat(
    [
      aws_ssm_parameter.database_url.arn,
      aws_ssm_parameter.supabase_service_role_key.arn,
    ],
    [for p in aws_ssm_parameter.llm_api_keys : p.arn],
  )
}
