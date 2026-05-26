resource "google_project_service" "sqladmin" {
  service            = "sqladmin.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "iam" {
  service            = "iam.googleapis.com"
  disable_on_destroy = false
}

resource "random_password" "writer" {
  length  = 32
  special = false
}

resource "random_password" "reader" {
  length  = 32
  special = false
}

resource "google_sql_database_instance" "statcast" {
  name             = "mlbsims-statcast"
  database_version = "POSTGRES_15"
  region           = var.region

  deletion_protection = var.deletion_protection

  settings {
    tier              = var.instance_tier
    edition           = "ENTERPRISE"
    availability_type = "ZONAL"
    disk_type         = "PD_SSD"
    disk_size         = var.disk_size_gb
    disk_autoresize   = true

    backup_configuration {
      enabled                        = true
      start_time                     = "07:00"
      point_in_time_recovery_enabled = false
      transaction_log_retention_days = 1
      backup_retention_settings {
        retained_backups = 3
        retention_unit   = "COUNT"
      }
    }

    ip_configuration {
      ipv4_enabled = true
      ssl_mode     = "ENCRYPTED_ONLY"
    }

    location_preference {
      zone = var.zone
    }
  }

  depends_on = [google_project_service.sqladmin]
}

resource "google_sql_database" "statcast" {
  name     = "statcast"
  instance = google_sql_database_instance.statcast.name
}

resource "google_sql_user" "writer" {
  name     = "mlbsims_writer"
  instance = google_sql_database_instance.statcast.name
  password = random_password.writer.result
}

resource "google_sql_user" "reader" {
  name     = "mlbsims_reader"
  instance = google_sql_database_instance.statcast.name
  password = random_password.reader.result
}

data "google_project" "current" {
  project_id = var.project_id
}

# Grant cloudsql.client to the e2-micro's attached default compute SA.
# This avoids downloadable JSON keys (blocked by org policy) — Auth Proxy
# on the VM uses metadata-server credentials automatically.
resource "google_project_iam_member" "e2_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}
