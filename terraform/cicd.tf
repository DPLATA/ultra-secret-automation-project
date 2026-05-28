# CI/CD infrastructure for the Go API service — Cloud Build flavor.
#
# Push to main with changes under api/** → Cloud Build trigger fires →
# reads api/cloudbuild.yaml → builds + pushes image → deploys to Cloud Run.
#
# The GitHub repo must already be connected to Cloud Build (one-time setup
# via console: Cloud Build → Triggers → Connect Repository → GitHub App).

# ---------- APIs ----------

resource "google_project_service" "artifactregistry" {
  service            = "artifactregistry.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "run" {
  service            = "run.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "secretmanager" {
  service            = "secretmanager.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "cloudbuild" {
  service            = "cloudbuild.googleapis.com"
  disable_on_destroy = false
}

# ---------- Artifact Registry ----------

resource "google_artifact_registry_repository" "mlbsims" {
  location      = var.region
  repository_id = "mlbsims"
  description   = "MLB Sims API container images"
  format        = "DOCKER"

  depends_on = [google_project_service.artifactregistry]
}

# ---------- Runtime service account ----------
# This is the identity the Cloud Run service runs as. It needs Cloud SQL
# client access and permission to read each secret.

resource "google_service_account" "api_runtime" {
  account_id   = "mlbsims-api"
  display_name = "MLB Sims API runtime"
  description  = "Cloud Run service identity — Cloud SQL client + Secret Manager reader"
}

resource "google_project_iam_member" "api_runtime_cloudsql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.api_runtime.email}"
}

# ---------- Cloud Build trigger service account ----------
# New GCP best practice (and now a UI requirement) — every Cloud Build trigger
# must specify an explicit, dedicated service account. The default Cloud Build
# SA (<project-number>@cloudbuild.gserviceaccount.com) is being phased out
# for new triggers.

resource "google_service_account" "cloudbuild_trigger" {
  account_id   = "mlbsims-cloudbuild"
  display_name = "MLB Sims Cloud Build trigger"
  description  = "Runs api/cloudbuild.yaml — builds image, pushes to AR, deploys Cloud Run"
}

# Roles needed by the trigger SA to run the build pipeline:
resource "google_project_iam_member" "cloudbuild_logwriter" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.cloudbuild_trigger.email}"
}

resource "google_project_iam_member" "cloudbuild_ar_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.cloudbuild_trigger.email}"
}

resource "google_project_iam_member" "cloudbuild_run_admin" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.cloudbuild_trigger.email}"
}

# Must be able to act-as the runtime SA during `gcloud run deploy`.
resource "google_service_account_iam_member" "cloudbuild_as_runtime" {
  service_account_id = google_service_account.api_runtime.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.cloudbuild_trigger.email}"
}

# ---------- Secret Manager ----------

resource "google_secret_manager_secret" "openrouter_api_key" {
  secret_id = "openrouter-api-key"
  replication {
    auto {}
  }
  depends_on = [google_project_service.secretmanager]
}

resource "google_secret_manager_secret" "ip_hash_secret" {
  secret_id = "ip-hash-secret"
  replication {
    auto {}
  }
  depends_on = [google_project_service.secretmanager]
}

resource "google_secret_manager_secret" "db_llm_password" {
  secret_id = "db-llm-password"
  replication {
    auto {}
  }
  depends_on = [google_project_service.secretmanager]
}

# Pre-populate the IP hash secret (random, server-only, never rotated)
resource "random_password" "ip_hash" {
  length  = 32
  special = false
}

resource "google_secret_manager_secret_version" "ip_hash" {
  secret      = google_secret_manager_secret.ip_hash_secret.id
  secret_data = random_password.ip_hash.result
}

# DB password — reuse the random_password.llm from main.tf
resource "google_secret_manager_secret_version" "db_llm_password" {
  secret      = google_secret_manager_secret.db_llm_password.id
  secret_data = random_password.llm.result
}

# Runtime SA reads each secret
resource "google_secret_manager_secret_iam_member" "openrouter_access" {
  secret_id = google_secret_manager_secret.openrouter_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api_runtime.email}"
}

resource "google_secret_manager_secret_iam_member" "ip_hash_access" {
  secret_id = google_secret_manager_secret.ip_hash_secret.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api_runtime.email}"
}

resource "google_secret_manager_secret_iam_member" "db_password_access" {
  secret_id = google_secret_manager_secret.db_llm_password.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api_runtime.email}"
}

# ---------- Cloud Run service shell ----------
# Image starts as a placeholder; Cloud Build overwrites it on every deploy.
# template.containers[0].image is in lifecycle.ignore_changes so terraform
# doesn't fight Cloud Build over it.

resource "google_cloud_run_v2_service" "api" {
  name     = "mlbsims-api"
  location = var.region

  template {
    service_account = google_service_account.api_runtime.email

    containers {
      image = "us-docker.pkg.dev/cloudrun/container/hello"

      ports {
        container_port = 8080
      }

      env {
        name  = "DB_INSTANCE"
        value = google_sql_database_instance.statcast.connection_name
      }
      env {
        name  = "DB_NAME"
        value = "statcast"
      }
      env {
        name  = "DB_USER"
        value = "mlbsims_llm"
      }
      env {
        name = "DB_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.db_llm_password.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "OPENROUTER_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.openrouter_api_key.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "IP_HASH_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.ip_hash_secret.secret_id
            version = "latest"
          }
        }
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }
    }

    scaling {
      min_instance_count = 0
      max_instance_count = 5
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
    ]
  }

  depends_on = [
    google_project_service.run,
    google_project_iam_member.api_runtime_cloudsql_client,
    google_secret_manager_secret_iam_member.openrouter_access,
    google_secret_manager_secret_iam_member.ip_hash_access,
    google_secret_manager_secret_iam_member.db_password_access,
  ]
}

# Public access — app-layer rate limit handles abuse, not IAM
resource "google_cloud_run_v2_service_iam_member" "public" {
  location = google_cloud_run_v2_service.api.location
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ---------- Cloud Build trigger ----------
# Fires on push to main with changes under api/**. Reads api/cloudbuild.yaml.

resource "google_cloudbuild_trigger" "api_deploy" {
  name        = "mlbsims-api-deploy"
  description = "Build + deploy mlbsims-api on push to main"
  location    = "global"

  # Dedicated SA — required by current Cloud Build trigger spec
  service_account = google_service_account.cloudbuild_trigger.id

  github {
    owner = var.github_owner
    name  = var.github_repo
    push {
      branch = "^main$"
    }
  }

  included_files = ["api/**"]
  filename       = "api/cloudbuild.yaml"

  depends_on = [
    google_project_service.cloudbuild,
    google_artifact_registry_repository.mlbsims,
    google_cloud_run_v2_service.api,
    google_project_iam_member.cloudbuild_logwriter,
    google_project_iam_member.cloudbuild_ar_writer,
    google_project_iam_member.cloudbuild_run_admin,
    google_service_account_iam_member.cloudbuild_as_runtime,
  ]
}
