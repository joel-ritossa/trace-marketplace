# State bucket must exist before `terraform init` (see infra/README.md):
#   aws s3 mb s3://<bucket> && aws s3api put-bucket-versioning \
#     --bucket <bucket> --versioning-configuration Status=Enabled
# Backend blocks cannot use variables; edit the bucket name here.
# No state locking: single-operator project. If that changes, add
# `use_lockfile = true` (Terraform >= 1.10).
terraform {
  backend "s3" {
    bucket  = "trace-marketplace-tfstate"
    key     = "trace-marketplace/terraform.tfstate"
    region  = "us-west-2"
    encrypt = true
  }
}
