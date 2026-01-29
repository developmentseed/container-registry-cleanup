# Container Registry Cleanup

A reusable GitHub Actions workflow for cleaning up old container images from container registries based on tag patterns and retention policies.

## Supported registries

* GitHub Container Registry (GHCR)
* Harbor

## Tags

We consider three tag patterns and associated retention days.
The defaults can be changed with arguments.

* **Version tags**: for releases
  * The default catches [semantic versioning](https://semver.org/) (like `0.8.1`), also with a `v` (like `v1.2.12`) and `latest`
  * Images will never be deleted
* **Test tags**: for release candidates, or pull-requests
  * The default catches `pr-123`)
  * Default: 30 days
* **Others**
  * Anything not matching version or test patterns, also untagged images
  * Default: 7 days

## Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `REGISTRY_TYPE` | Registry type: `harbor` or `ghcr` | Yes | - |
| `REPOSITORY_NAME` | Repository/package name | Yes | - |
| `DRY_RUN` | Enable dry-run mode | No | true |
| `VERSION_PATTERN` | Regex pattern for version tags (protected from deletion) | No | `^(v\d+\.\d+\.\d+.*\|latest)$` |
| `TEST_PATTERN` | Regex pattern for test/PR tags | No | `^pr-\d+$` |
| `TEST_RETENTION_DAYS` | Days to keep test-tagged images (0 = delete immediately) | No | 30 |
| `OTHERS_RETENTION_DAYS` | Days to keep all other images (0 = delete immediately) | No | 7 |

### GHCR

* `GITHUB_TOKEN`: GitHub token with `packages:write` permission (defaults to `github.token`)
* `GITHUB_REPO_OWNER`: GitHub organization or user name (automatically set to `github.repository_owner` in GitHub Actions)

### Harbor

* `HARBOR_URL`: Harbor registry URL
* `HARBOR_USERNAME`: Harbor username
* `HARBOR_PASSWORD`: Harbor password
* `HARBOR_PROJECT_NAME`: Harbor project name

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
      - uses: developmentseed/container-registry-cleanup@v0.0.1 # x-release-please-version
        env:
          REGISTRY_TYPE: ghcr
          REPOSITORY_NAME: my-package-name
          TEST_RETENTION_DAYS: 30
          OTHERS_RETENTION_DAYS: 7
          DRY_RUN: false
          # GITHUB_TOKEN and GITHUB_REPO_OWNER are automatically set by the action
```

#### Harbor example

```yaml
jobs:
  cleanup:
    runs-on: ubuntu-latest
    permissions:
      packages: write
      contents: read
    steps:
      - uses: developmentseed/container-registry-cleanup@0.0.1
        env:
          REGISTRY_TYPE: harbor
          REPOSITORY_NAME: data-pipeline
          HARBOR_URL: ${{ secrets.HARBOR_URL }}
          HARBOR_USERNAME: ${{ secrets.HARBOR_USERNAME }}
          HARBOR_PASSWORD: ${{ secrets.HARBOR_PASSWORD }}
          HARBOR_PROJECT_NAME: my-project
```

### Running locally

```bash
export GITHUB_TOKEN=your-token
export GITHUB_REPO_OWNER=repo-owner-or-org
export REGISTRY_TYPE=ghcr
export REPOSITORY_NAME=my-package-name
export TEST_RETENTION_DAYS=30
export OTHERS_RETENTION_DAYS=7

python -m container_registry_cleanup
```
