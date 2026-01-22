# Container Image Cleanup

A reusable GitHub Actions workflow for cleaning up old container images from container registries based on tag patterns and retention policies.

## Supported registries

* GitHub Container Registry (GHCR)

## Tags

We consider three tag patterns and associated retention days.
The defaults can be changed with arguments.

* **Version tags**: for releases
  * `version_pattern`; the default catches [semantic versioning](https://semver.org/) (like `0.8.1`), also with a `v` (like `v1.2.12`) and `latest`
  * Images will never be deleted
* **Test tags**: for release candidates, or pull-requests
  * `test_pattern`; the default catches `pr-123`)
  * `test_retention_days` (default: 30 days)
* **Dev tags** or untagged: for all other images (default: )
  * All other tagged or untagged images.
  * `dev_retention_days` (default: 7 days)

## Input arguments and secrets

| Input | Description | Required | Default |
|-------|-------------|----------|---------|
| `registry_type` | Registry type: `ghcr` | Yes | - |
| `repository_name` | Repository/package name | Yes | - |
| `test_retention_days` | Days to keep test-tagged images (0 = delete immediately) | No | 30 |
| `dev_retention_days` | Days to keep all other images (0 = delete immediately) | No | 7 |
| `dry_run` | Enable dry-run mode | No | true |

### GHCR

| Input | Description | Required | Default |
|-------|-------------|----------|---------|
| `repository_name` | Repository/package name | Yes | - |
| `org_name` | GitHub organization name (GHCR) | GHCR only | Repository owner |

* `GITHUB_TOKEN`: GitHub token with `packages:write` permission (defaults to `github.token`)

## Usage

### As a Step Action

#### GHCR example

```yaml
on:
  workflow_dispatch:
  schedule:
    - cron: "5 * * * *"

jobs:
  clean:
    runs-on: ubuntu-latest
    permissions:
      packages: write
      contents: read
    steps:
      - uses: developmentseed/container-registry-cleanup@0.0.1
        with:
          registry_type: ghcr
          repository_name: my-package-name
          test_retention_days: 30
          dev_retention_days: 7
          untagged_retention_days: 7
          dry_run: true
```

### Running locally

```bash
export GITHUB_TOKEN=your-token
export GITHUB_REPO_OWNER=repo-owner-or-org
export REGISTRY_TYPE=ghcr
export REPOSITORY_NAME=my-package-name
export TEST_RETENTION_DAYS=30
export DEV_RETENTION_DAYS=7

python -m container_registry_cleanup
```
