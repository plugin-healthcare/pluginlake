# Nightly stop of the demo VM, so a forgotten VM does not keep running.
# A serverless job runs the scw CLI with an API key that may only stop servers in this project.

resource "scaleway_iam_application" "shutdown" {
  name = "pluginlake-demo-shutdown"
}

resource "scaleway_iam_policy" "shutdown" {
  name           = "pluginlake-demo-stop-only"
  application_id = scaleway_iam_application.shutdown.id
  rule {
    project_ids          = [scaleway_instance_server.demo.project_id]
    permission_set_names = ["InstancesServerStop"]
  }
}

resource "scaleway_iam_api_key" "shutdown" {
  application_id     = scaleway_iam_application.shutdown.id
  default_project_id = scaleway_instance_server.demo.project_id
}

resource "scaleway_secret" "shutdown" {
  name = "pluginlake-demo-shutdown-key"
}

resource "scaleway_secret_version" "shutdown" {
  secret_id = scaleway_secret.shutdown.id
  data      = scaleway_iam_api_key.shutdown.secret_key
}

resource "scaleway_job_definition" "shutdown" {
  name                   = "pluginlake-demo-nightly-stop"
  cpu_limit              = 140
  memory_limit           = 256
  local_storage_capacity = 1024
  image_uri              = "docker.io/scaleway/cli@sha256:62199b326f46121227892521856207c3b9c40e19a84830bf4f2b15f90ca8c4e8"
  timeout                = "3m"
  args                   = ["instance", "server", "stop", split("/", scaleway_instance_server.demo.id)[1], "zone=fr-par-1"]

  env = {
    SCW_ACCESS_KEY              = scaleway_iam_api_key.shutdown.access_key
    SCW_DEFAULT_ORGANIZATION_ID = scaleway_iam_application.shutdown.organization_id
    SCW_DEFAULT_PROJECT_ID      = scaleway_instance_server.demo.project_id
    SCW_DEFAULT_REGION          = "fr-par"
    SCW_DEFAULT_ZONE            = "fr-par-1"
  }

  secret_reference {
    secret_id      = split("/", scaleway_secret.shutdown.id)[1]
    secret_version = scaleway_secret_version.shutdown.revision
    environment    = "SCW_SECRET_KEY"
  }

  cron {
    schedule = "0 18 * * *"
    timezone = "Europe/Amsterdam"
  }
}
