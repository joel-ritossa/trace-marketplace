variable "project" {
  description = "Name prefix for all resources."
  type        = string
  default     = "trace-marketplace"
}

variable "aws_region" {
  type    = string
  default = "us-west-2"
}

variable "domain_name" {
  description = "Apex domain registered in Route53 (registration creates the hosted zone this config looks up)."
  type        = string
}

variable "supabase_url" {
  description = "Hosted Supabase project URL, e.g. https://abcdefgh.supabase.co"
  type        = string
}

variable "github_repo" {
  description = "GitHub repo (owner/name) allowed to assume the deploy role."
  type        = string
  default     = "worktrial-joel-ritossa-dot/trace-marketplace"
}

variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

# Initial image tag only. CI registers new task-definition revisions with
# git-SHA tags; the ECS services ignore task_definition drift after that.
variable "image_tag" {
  type    = string
  default = "latest"
}
