# Repository guide

## Read by task

- Setup, transports and configuration: [README.md](README.md) and
  [Installation](docs/INSTALLATION.md).
- Tool catalogue and Jamf API conventions: [Tools](docs/TOOLS.md).
- Local Docker, 1Password mounts and tenant reads:
  [Local Docker](docs/LOCAL_DOCKER.md).
- Blueprints, benchmarks, DDM and compliance permissions:
  [Platform setup](docs/PLATFORM_SETUP.md) and
  [API research](docs/PLATFORM_API_RESEARCH.md).
- Remote authentication and deployment checks:
  [Remote validation](docs/REMOTE_VALIDATION.md).
- Registration, result contracts and authorization boundaries:
  [Architecture](docs/ARCHITECTURE.md).
- Tool changes, dependencies and testing: [Development](docs/DEVELOPMENT.md).

## Verify changes

Install development dependencies with `uv sync --extra dev`, then run
`./scripts/check.sh`. Follow Development for catalogue and documentation updates.
For live checks, follow Local Docker or Remote validation and report each tested
product separately. Configuration status alone does not verify upstream access.

## Jamf operation safety

Clarify whether an ambiguous request concerns computers, mobile devices or users
before acting. For broad deployments, inspect each deployment's detailed scope,
explain the affected population, get explicit confirmation and prefer a phased
rollout. Deployment lists may contain IDs without scope; read the individual
records before describing impact.
