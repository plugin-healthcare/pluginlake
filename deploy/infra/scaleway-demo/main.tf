terraform {
  required_providers {
    scaleway = {
      source  = "scaleway/scaleway"
      version = "~> 2.77.0"
    }
  }

  # Scaleway Object Storage speaks S3 but has no AWS account, STS or metadata APIs.
  # The bucket is passed at init time from TOFU_STATE_BUCKET in .env.
  backend "s3" {
    key                         = "scaleway-demo/terraform.tfstate"
    region                      = "fr-par"
    endpoints                   = { s3 = "https://s3.fr-par.scw.cloud" }
    use_lockfile                = true
    skip_credentials_validation = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    skip_metadata_api_check     = true
    skip_s3_checksum            = true
  }

  encryption {
    key_provider "pbkdf2" "state" {
      passphrase = var.state_passphrase
    }
    method "aes_gcm" "state" {
      keys = key_provider.pbkdf2.state
    }
    state {
      method   = method.aes_gcm.state
      enforced = true
    }
    plan {
      method   = method.aes_gcm.state
      enforced = true
    }
  }
}

provider "scaleway" {
  zone   = "fr-par-1"
  region = "fr-par"
}

variable "ssh_public_key" {
  description = "Public SSH key for the demo administrator."
  type        = string
}

variable "console_password_hash" {
  description = "SHA-512 crypt hash for serial-console enrollment and recovery."
  type        = string
  sensitive   = true
  validation {
    condition     = startswith(var.console_password_hash, "$6$")
    error_message = "Supply the hash produced by openssl passwd -6, never the password."
  }
}

variable "state_passphrase" {
  description = "Passphrase that encrypts the state and plans in Object Storage; without it the state is unrecoverable."
  type        = string
  sensitive   = true
  validation {
    condition     = length(var.state_passphrase) >= 16
    error_message = "Use a passphrase of at least 16 characters."
  }
}

resource "scaleway_instance_ip" "egress" {}

resource "scaleway_instance_security_group" "private" {
  name                    = "pluginlake-demo-no-public-ingress"
  stateful                = true
  inbound_default_policy  = "drop"
  outbound_default_policy = "accept"
}

resource "scaleway_instance_server" "demo" {
  name              = "pluginlake-demo"
  type              = "DEV1-L"
  image             = "ubuntu_noble"
  ip_id             = scaleway_instance_ip.egress.id
  security_group_id = scaleway_instance_security_group.private.id

  root_volume {
    volume_type = "sbs_volume"
    size_in_gb  = 50
  }

  user_data = {
    cloud-init = templatefile("${path.module}/cloud-init.yaml.tftpl", {
      ssh_key       = var.ssh_public_key
      password_hash = var.console_password_hash
    })
  }

  lifecycle {
    # Day-to-day start/stop is managed by the presenter, outside OpenTofu.
    ignore_changes = [state]
  }
}

output "instance_id" {
  value = split("/", scaleway_instance_server.demo.id)[1]
}
