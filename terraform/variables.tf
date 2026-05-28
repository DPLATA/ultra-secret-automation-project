variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region. Must match e2-micro region for free network egress."
  type        = string
  default     = "us-east1"
}

variable "zone" {
  description = "Primary zone within region. Single-zone (no HA) to halve cost."
  type        = string
  default     = "us-east1-b"
}

variable "instance_tier" {
  description = <<-EOT
    Cloud SQL Postgres tier. Cheapest available in 2026:
      db-perf-optimized-N-2 — ~$25/mo, 2 vCPU, 8GB RAM (Enterprise edition)
      db-custom-1-3840      — ~$30/mo, 1 vCPU, 3.75GB RAM (custom)
    If the chosen tier is unavailable in region, terraform apply will error and you can adjust.
  EOT
  type        = string
  default     = "db-custom-1-3840"
}

variable "disk_size_gb" {
  description = "Initial disk size. Auto-resize is enabled."
  type        = number
  default     = 10
}

variable "deletion_protection" {
  description = "Prevent accidental terraform destroy. Set false only when intentionally tearing down."
  type        = bool
  default     = true
}

variable "github_owner" {
  description = "GitHub username/org that owns the repo. Used by Cloud Build trigger."
  type        = string
  default     = "DPLATA"
}

variable "github_repo" {
  description = "GitHub repo name. Must already be connected to Cloud Build via console."
  type        = string
  default     = "ultra-secret-automation-project"
}
