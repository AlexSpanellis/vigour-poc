terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
  backend "gcs" {
    bucket = "vigour-poc-tfstate"
    prefix = "terraform/state"
  }
}

provider "google" {
  project = var.gcp_project
  region  = var.region
}

# ------------------------------------------------------------------ #
#  Variables                                                           #
# ------------------------------------------------------------------ #
variable "gcp_project" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "europe-west4"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "poc"
}

# ------------------------------------------------------------------ #
#  Cloud Storage — raw footage, annotated output                       #
# ------------------------------------------------------------------ #
resource "google_storage_bucket" "vigour_poc" {
  name          = "${var.gcp_project}-vigour-poc"
  location      = "EU"
  storage_class = "STANDARD"
  force_destroy = true   # POC only — remove for production

  lifecycle_rule {
    condition { age = 30 }
    action    { type = "Delete" }
  }
}

# ------------------------------------------------------------------ #
#  Cloud SQL (PostgreSQL 15) — results store                           #
# ------------------------------------------------------------------ #
resource "google_sql_database_instance" "vigour_poc" {
  name             = "vigour-poc-postgres"
  database_version = "POSTGRES_15"
  region           = var.region

  settings {
    tier = "db-f1-micro"   # smallest, cheapest for POC

    ip_configuration {
      authorized_networks {
        value = "0.0.0.0/0"   # restrict in production
        name  = "all-poc"
      }
    }
  }

  deletion_protection = false   # POC only
}

resource "google_sql_database" "vigour" {
  name     = "vigour"
  instance = google_sql_database_instance.vigour_poc.name
}

# ------------------------------------------------------------------ #
#  Memorystore (Redis) — Celery broker + result backend               #
# ------------------------------------------------------------------ #
resource "google_redis_instance" "vigour_poc" {
  name           = "vigour-poc-redis"
  tier           = "BASIC"
  memory_size_gb = 1
  region         = var.region
}

# ------------------------------------------------------------------ #
#  Compute — L4 GPU VM for Celery worker                               #
# ------------------------------------------------------------------ #
resource "google_compute_instance" "vigour_worker" {
  name         = "vigour-poc-worker"
  machine_type = "g2-standard-4"   # 1× L4 GPU
  zone         = "${var.region}-b"

  boot_disk {
    initialize_params {
      image = "projects/ml-images/global/images/c2-deeplearning-pytorch-2-1-cu121-v20240111-debian-11"
      size  = 100  # GB
    }
  }

  guest_accelerator {
    type  = "nvidia-l4"
    count = 1
  }

  scheduling {
    on_host_maintenance = "TERMINATE"  # required for GPU VMs
  }

  network_interface {
    network = "default"
    access_config {}   # ephemeral public IP for POC
  }

  metadata = {
    startup-script = <<-EOT
      #!/bin/bash
      # Install NVIDIA drivers + Docker
      /opt/deeplearning/install-driver.sh
      apt-get install -y docker.io
      systemctl enable --now docker
    EOT
  }

  tags = ["vigour-worker", "http-server", "https-server"]
}

# ------------------------------------------------------------------ #
#  Outputs                                                             #
# ------------------------------------------------------------------ #
output "gcs_bucket_name" {
  value = google_storage_bucket.vigour_poc.name
}

output "redis_host" {
  value = google_redis_instance.vigour_poc.host
}

output "worker_external_ip" {
  value = google_compute_instance.vigour_worker.network_interface[0].access_config[0].nat_ip
}
