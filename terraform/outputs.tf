output "instance_connection_name" {
  description = "Pass to cloud-sql-proxy on e2-micro: cloud-sql-proxy <this-value>"
  value       = google_sql_database_instance.statcast.connection_name
}

output "instance_public_ip" {
  description = "Public IP of the Cloud SQL instance (for reference; clients should use Auth Proxy)."
  value       = google_sql_database_instance.statcast.public_ip_address
}

output "writer_password" {
  description = "Password for mlbsims_writer role. Retrieve with: terraform output -raw writer_password"
  value       = random_password.writer.result
  sensitive   = true
}

output "reader_password" {
  description = "Password for mlbsims_reader role. Retrieve with: terraform output -raw reader_password"
  value       = random_password.reader.result
  sensitive   = true
}

output "llm_password" {
  description = "Password for mlbsims_llm role (used by Cloud Run API). Retrieve with: terraform output -raw llm_password"
  value       = random_password.llm.result
  sensitive   = true
}

output "e2_service_account_email" {
  description = "e2-micro's attached compute SA, granted cloudsql.client. Auth Proxy uses this automatically via metadata server — no key file needed."
  value       = "${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}
