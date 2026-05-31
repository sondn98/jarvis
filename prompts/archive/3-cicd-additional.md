# Release and Publishing Strategy

This project follows a tag-driven release process.

Container images must only be published when a Git tag is created.

Regular pushes to the `main` branch must never publish images.

The purpose of the `main` branch workflow is validation only.

Publishing is reserved for versioned releases.

---

# Workflow Triggers

The workflow should run on:

```yaml
on:
  pull_request:
    branches:
      - main

  push:
    branches:
      - main

    tags:
      - "v*"
```

Examples of valid release tags:

```text
v0.1.0
v0.2.0
v1.0.0
```

The implementation should not assume a specific versioning scheme beyond the `v*` pattern unless the repository already defines one.

---

# Workflow Behavior

## Pull Requests

Run:

* Linting
* Security Scanning
* Unit Tests
* Docker Build Validation

Do not publish images.

---

## Pushes to Main

Run:

* Linting
* Security Scanning
* Unit Tests
* Docker Build Validation

Do not publish images.

This branch is used to continuously validate the codebase.

---

## Release Tags

When a Git tag matching the release pattern is pushed:

Run:

* Linting
* Security Scanning
* Unit Tests
* Docker Build
* Docker Publish

Publishing must only occur after all validation jobs succeed.

---

# Docker Image Tagging Strategy

The Docker image version must be derived directly from the Git tag.

For example:

Git tag:

```text
v1.2.3
```

Docker images:

```text
sondn1/jarvis:v1.2.3
sondn1/jarvis:latest
```

Git tag:

```text
v0.5.0
```

Docker images:

```text
sondn1/jarvis:v0.5.0
sondn1/jarvis:latest
```

The workflow should automatically extract the Git tag from the GitHub Actions context.

Do not require manual version input.

---

# Latest Tag Behavior

Every successful release must update:

```text
sondn1/jarvis:latest
```

to point to the newest released image.

Example:

```text
Current release:
  sondn1/jarvis:v1.1.0
  sondn1/jarvis:latest -> v1.1.0

New release:
  sondn1/jarvis:v1.2.0
  sondn1/jarvis:latest -> v1.2.0
```

The `latest` tag should always represent the most recently published release.

---

# Build Verification Strategy

Docker image builds should still be validated on:

* Pull Requests
* Pushes to main

This ensures Dockerfile issues are detected before creating a release tag.

Only the image push operation should be restricted to release tags.

---

# Release Documentation

Update README and relevant documentation to explain:

## Creating a Release

Example:

```bash
git tag v1.0.0
git push origin v1.0.0
```

## Result

The workflow should publish:

```text
sondn1/jarvis:v1.0.0
sondn1/jarvis:latest
```

to Docker Hub automatically.

## Release Requirements

A release should only be published if:

* Linting passes
* Security checks pass
* Unit tests pass
* Docker build succeeds

Any failure must prevent image publication.
