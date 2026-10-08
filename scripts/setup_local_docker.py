"""Create local Docker test credentials and TLS files without printing secrets."""

import os
import secrets
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    tls = ROOT / ".docker-local"
    tls.mkdir(mode=0o700, exist_ok=True)
    # Optional public corporate CA bundle, used only while downloading packages.
    (tls / "build-ca.pem").touch(exist_ok=True)
    key = tls / "server.key"
    cert = tls / "server.crt"
    if not key.exists() or not cert.exists():
        config = tls / "openssl.cnf"
        config.write_text(
            "[req]\ndistinguished_name=dn\nx509_extensions=ext\nprompt=no\n"
            "[dn]\nCN=localhost\n[ext]\nsubjectAltName=DNS:localhost,IP:127.0.0.1\n"
            "basicConstraints=critical,CA:TRUE\n"
            "keyUsage=critical,digitalSignature,keyEncipherment,keyCertSign\n"
            "extendedKeyUsage=serverAuth\n"
        )
        subprocess.run(
            [
                "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                "-days", "30", "-config", str(config), "-keyout", str(key),
                "-out", str(cert),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # The parent directory is private; the container runs as this host UID.
        key.chmod(0o600)
        cert.chmod(0o644)
        config.unlink()
    env = ROOT / ".env.local"
    if not env.exists():
        with open(env, "x", opener=lambda path, flags: os.open(path, flags, 0o600)) as file:
            file.write(
                "# Add a Jamf Pro API client with read-only privileges below.\n"
                "JAMF_PRO_URL=\nJAMF_PRO_CLIENT_ID=\nJAMF_PRO_CLIENT_SECRET=\n"
                f"JAMF_MCP_LOCAL_TOKEN={secrets.token_urlsafe(32)}\n"
                f"JAMF_LOCAL_UID={os.getuid()}\nJAMF_LOCAL_GID={os.getgid()}\n"
            )
        print("Created .env.local. Fill in the three JAMF_PRO values for live reads.")
    else:
        print("Preserved existing .env.local. Ensure it contains JAMF_MCP_LOCAL_TOKEN.")
    print("Local TLS files ready. No system trust settings were changed.")


if __name__ == "__main__":
    main()
