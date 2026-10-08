"""Verify that the shared check runner propagates early failures."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_check_runner_stops_after_pytest_failure(tmp_path: Path) -> None:
    """A pytest failure should stop the runner before it launches Ruff."""
    fake_python = tmp_path / "python"
    call_log = tmp_path / "calls.log"
    fake_python.write_text(
        "#!/usr/bin/env python3\n"
        "import os\n"
        "import sys\n"
        "with open(os.environ['CHECK_CALL_LOG'], 'a', encoding='utf-8') as log:\n"
        "    log.write('called\\n')\n"
        "if 'pytest' in sys.argv:\n"
        "    raise SystemExit(23)\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    environment = os.environ.copy()
    environment["PYTHON"] = str(fake_python)
    environment["CHECK_CALL_LOG"] = str(call_log)

    result = subprocess.run(
        [str(ROOT / "scripts" / "check.sh")],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 23
    assert call_log.read_text(encoding="utf-8").splitlines() == ["called"]
