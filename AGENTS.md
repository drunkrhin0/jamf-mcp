# Repository guide

## Read by task

- Installation or credentials: [README](README.md) and [Installation](docs/INSTALLATION.md).
- Docker, TLS or 1Password mounts: [Docker setup](docs/DOCKER.md).
- Tool names or Jamf privileges: [Tools](docs/TOOLS.md).
- Blueprints, benchmarks or Platform DDM: [Platform setup](docs/PLATFORM_SETUP.md)
  and [API contracts](docs/PLATFORM_API_RESEARCH.md).
- Registration, results or authorization: [Architecture](docs/ARCHITECTURE.md).
- Code, dependencies, tests or releases: [Development](docs/DEVELOPMENT.md).
- Plugin packaging or skills: [Plugin setup](docs/OPENAI_PLUGIN.md).
- Container base or backports: [Security patches](docker/SECURITY_PATCHES.md).
- Hosted OAuth or gateway deployment: [Remote validation](docs/REMOTE_VALIDATION.md).

## Verify changes

Use Conventional Commit messages for new commits. Release rules are in Development.

Run `uv sync --extra dev`, then `./scripts/check.sh`. Follow Development for
catalogue and documentation updates. For live reads, follow Docker setup or
Remote validation and record each product separately in [Validation](docs/VALIDATION.md).
Configuration status alone does not verify upstream access. Only read-only
workflows have live validation; test proposed writes on an agreed disposable tenant.

## Jamf operation safety

Clarify computers, mobile devices or users when a request is ambiguous.
Before a broad deployment, read each record's detailed scope, explain the affected
population, get explicit confirmation and prefer a phased rollout. Lists may
contain scope IDs without the population details.
