"""Package shared Jamf skills with a remote or registered OpenAI connection."""

import argparse
import json
import re
import shutil
from pathlib import Path
from urllib.parse import urlsplit

from jamf_mcp.remote import validate_remote_resource_url

PLUGIN_ROOT = Path(__file__).resolve().parents[1] / "plugins" / "jamf-read-only"


def package_plugin(output: Path, *, url: str | None = None, app_id: str | None = None) -> Path:
    """Create a new package without changing the local plugin or copying secrets."""
    if (url is None) == (app_id is None):
        raise ValueError("Supply exactly one of url or app_id")
    if url is not None:
        validate_remote_resource_url(url)
        host = urlsplit(url).hostname
        if not urlsplit(url).path or host in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Use the reachable hosted MCP endpoint, including its path")
    if app_id is not None and not re.fullmatch(r"plugin_asdk_app_[A-Za-z0-9_-]+", app_id):
        raise ValueError("Use the exact plugin_asdk_app ID from the registered ChatGPT connection")
    manifest = json.loads((PLUGIN_ROOT / "plugin.json").read_text())
    extension = manifest["extensions"]["com.openai"]
    extension["interface"]["longDescription"] = (
        "Read-only Jamf workflows for ChatGPT and Codex using a remote connection. "
        "Tenant reads require separately configured server credentials."
    )
    if app_id is not None:
        extension["apps"] = "./.app.json"
        connection_name = ".app.json"
        connection = {"apps": {"jamf": {"id": app_id, "required": True}}}
    else:
        connection_name = "mcp.json"
        connection = {
            "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
            "mcpServers": {"jamf": {"type": "streamable-http", "url": url}},
        }
    # Refuse existing outputs, including the source package and installed caches.
    output.mkdir(parents=True, exist_ok=False)
    (output / "plugin.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (output / connection_name).write_text(json.dumps(connection, indent=2) + "\n")
    shutil.copytree(PLUGIN_ROOT / "skills", output / "skills")
    return output


def main() -> None:
    """Prepare an artifact; registration, deployment and installation are separate."""
    parser = argparse.ArgumentParser(description=__doc__)
    connection = parser.add_mutually_exclusive_group(required=True)
    connection.add_argument("--url", help="Actual hosted HTTPS MCP URL, including its path")
    connection.add_argument("--app-id", help="Exact registered ChatGPT plugin_asdk_app ID")
    parser.add_argument("--output", type=Path, required=True, help="New package directory")
    args = parser.parse_args()
    try:
        output = package_plugin(args.output, url=args.url, app_id=args.app_id)
    except (ValueError, OSError) as error:
        parser.exit(1, f"Packaging failed: {error}\n")
    print(f"Created {output}. Live connection and host acceptance remain unverified.")


if __name__ == "__main__":
    main()
