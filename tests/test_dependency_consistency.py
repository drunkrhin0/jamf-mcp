"""Keep package metadata, pip manifests, and SDK compatibility docs aligned."""

from __future__ import annotations

import re
import shutil
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = (ROOT,)
MCP_REQUIREMENT_PATTERN = re.compile(r"`(mcp[^`]*)`", re.IGNORECASE)


def dependency_key(spec: str) -> tuple[str, tuple[str, ...], str, str | None, str | None]:
    """Normalize a PEP 508 requirement for declaration comparison.

    Args:
        spec: A requirement string from package metadata or a requirements file.

    Returns:
        A tuple of normalized name, extras, specifier, URL, and marker.
    """
    requirement = Requirement(spec)
    return (
        canonicalize_name(requirement.name),
        tuple(sorted(canonicalize_name(extra) for extra in requirement.extras)),
        str(requirement.specifier),
        requirement.url,
        str(requirement.marker) if requirement.marker else None,
    )


def dependency_specs(path: Path) -> list[str]:
    """Read install dependency specifications from project metadata or pip input.

    Args:
        path: A package's ``pyproject.toml`` or ``requirements.txt`` file.

    Returns:
        The package's runtime dependency specification strings.
    """
    if path.name == "pyproject.toml":
        project = tomllib.loads(path.read_text(encoding="utf-8"))["project"]
        return project["dependencies"]

    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def dependency_differences(
    project_specs: Iterable[str], requirements_specs: Iterable[str]
) -> list[str]:
    """Describe dependency entries that differ between the two declarations.

    Args:
        project_specs: Runtime requirements from ``pyproject.toml``.
        requirements_specs: Install requirements from ``requirements.txt``.

    Returns:
        Human-readable missing and unexpected dependency descriptions.
    """
    project = Counter(dependency_key(spec) for spec in project_specs)
    requirements = Counter(dependency_key(spec) for spec in requirements_specs)
    differences: list[str] = []

    missing = project - requirements
    unexpected = requirements - project
    if missing:
        differences.append(
            "requirements.txt omits project dependencies: "
            + ", ".join(sorted(format_dependency(key) for key in missing.elements()))
        )
    if unexpected:
        differences.append(
            "requirements.txt has dependencies absent from pyproject.toml: "
            + ", ".join(sorted(format_dependency(key) for key in unexpected.elements()))
        )
    return differences


def format_dependency(
    key: tuple[str, tuple[str, ...], str, str | None, str | None]
) -> str:
    """Render a normalized requirement tuple for mismatch messages.

    Args:
        key: A normalized dependency key returned by ``dependency_key``.

    Returns:
        A compact PEP 508-style requirement string.
    """
    name, extras, specifier, url, marker = key
    rendered = name
    if extras:
        rendered += f"[{','.join(extras)}]"
    rendered += specifier
    if url:
        rendered += f" @ {url}"
    if marker:
        rendered += f"; {marker}"
    return rendered


def assert_dependency_parity(pyproject_path: Path, requirements_path: Path) -> None:
    """Fail when package runtime metadata and pip requirements disagree.

    Args:
        pyproject_path: The package's project metadata file.
        requirements_path: The package's pip requirements file.

    Raises:
        AssertionError: If either declaration has missing or extra dependencies.
    """
    differences = dependency_differences(
        dependency_specs(pyproject_path), dependency_specs(requirements_path)
    )
    if differences:
        raise AssertionError(
            f"Dependency mismatch for {pyproject_path.parent}: " + "; ".join(differences)
        )


def assert_readme_mcp_requirement(readme_path: Path, project_specs: Iterable[str]) -> None:
    """Fail when the README's exact MCP SDK range differs from project metadata.

    Args:
        readme_path: The package README containing an inline SDK requirement.
        project_specs: Runtime requirements from the package's project metadata.

    Raises:
        AssertionError: If either source omits or disagrees on its MCP requirement.
    """
    documented = [
        match.group(1)
        for match in MCP_REQUIREMENT_PATTERN.finditer(readme_path.read_text(encoding="utf-8"))
    ]
    documented_mcp = [spec for spec in documented if dependency_key(spec)[0] == "mcp"]
    project_mcp = [spec for spec in project_specs if dependency_key(spec)[0] == "mcp"]

    assert len(documented_mcp) == 1, f"Expected one explicit MCP requirement in {readme_path}"
    assert len(project_mcp) == 1, (
        f"Expected one MCP dependency in {readme_path.parent}/pyproject.toml"
    )
    assert dependency_key(documented_mcp[0]) == dependency_key(project_mcp[0]), (
        f"MCP SDK compatibility claim in {readme_path} differs from project metadata"
    )


@pytest.mark.parametrize("package", PACKAGES, ids=("root",))
def test_requirements_match_project_dependencies(package: Path) -> None:
    pyproject_path = package / "pyproject.toml"
    requirements_path = package / "requirements.txt"
    assert_dependency_parity(pyproject_path, requirements_path)
    assert_readme_mcp_requirement(package / "README.md", dependency_specs(pyproject_path))


def test_dependency_check_reports_requirements_drift(tmp_path: Path) -> None:
    pyproject_path = tmp_path / "pyproject.toml"
    requirements_path = tmp_path / "requirements.txt"
    shutil.copyfile(ROOT / "pyproject.toml", pyproject_path)
    requirements_path.write_text(
        (ROOT / "requirements.txt").read_text(encoding="utf-8")
        + "\nretro-parity-drift-fixture>=1\n",
        encoding="utf-8",
    )

    with pytest.raises(AssertionError, match="retro-parity-drift-fixture"):
        assert_dependency_parity(pyproject_path, requirements_path)
