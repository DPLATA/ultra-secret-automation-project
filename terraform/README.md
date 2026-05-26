# Terraform — Cloud SQL Statcast

Provisions a Postgres instance to hold pybaseball Statcast data, plus the IAM
plumbing for the e2-micro cron to connect via Cloud SQL Auth Proxy.

## One-time bootstrap (run from this directory)

```bash
# 1. Create the GCS bucket that holds Terraform state.
gcloud storage buckets create gs://mlbsims-tfstate \
    --project="$(gcloud config get-value project)" \
    --location=us-east1 \
    --uniform-bucket-level-access \
    --public-access-prevention

# Enable versioning so we can recover from a bad apply.
gcloud storage buckets update gs://mlbsims-tfstate --versioning

# 2. Enable required APIs (terraform also does this, but enabling up front
#    avoids a chicken-and-egg on the first apply).
gcloud services enable sqladmin.googleapis.com iam.googleapis.com

# 3. Copy and edit the tfvars file.
cp terraform.tfvars.example terraform.tfvars
# (defaults are already populated; edit if you want a different tier)

# 4. Init + plan + apply.
terraform init
terraform plan
terraform apply
```

Apply takes ~10-15 minutes — Cloud SQL instance provisioning is slow.

## After apply — grab outputs for Phase 2

```bash
# Connection name for the Auth Proxy
terraform output -raw instance_connection_name

# Service account JSON key (decode to a file)
terraform output -raw cron_service_account_key | base64 -d > ../secrets/cloudsql_sa.json
chmod 600 ../secrets/cloudsql_sa.json

# DB passwords (write to a local .env, do not commit)
terraform output -raw writer_password
terraform output -raw reader_password
```

## Cost

Expected ~$28-33/month for the configured tier:
- `db-custom-1-3840` instance: ~$25/mo
- 10 GB SSD: ~$1.70/mo
- Public IPv4 (in use): ~$3/mo
- Backups (3 retained, ~1 GB): <$1/mo
- PITR: disabled to save ~$3/mo of binary log storage

## Tear-down

`deletion_protection = true` by default. To destroy: set false, apply, then destroy.
