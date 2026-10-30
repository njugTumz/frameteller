"""rotate_token.sh against a fake `gh` and a throwaway HOME: never the real token files, never the real repo."""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[2] / "scripts" / "rotate_token.sh"
FAKE_GH = """#!/usr/bin/env bash
echo "$*" >> "$GH_LOG"
if [[ "$1 $2" == "secret set" ]]; then cat > "$GH_SECRET"; fi
if [[ "$1 $2" == "release view" ]]; then echo v1.1.0; fi
"""

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash is not installed")


def rotate(tmp_path: Path, *args: str) -> tuple[subprocess.CompletedProcess[str], Path]:
    home, bin_ = tmp_path / "home", tmp_path / "bin"
    bin_.mkdir(exist_ok=True)
    gh = bin_ / "gh"
    gh.write_text(FAKE_GH)
    gh.chmod(0o755)
    env = {
        "HOME": str(home),
        "PATH": f"{bin_}{os.pathsep}{os.environ['PATH']}",
        "GH_LOG": str(tmp_path / "gh.log"),
        "GH_SECRET": str(tmp_path / "secret"),
        "FRAMETELLER_REPO": "example/repo",
    }
    result = subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, env=env, check=False)
    return result, home / ".config" / "frameteller"


def test_a_judge_token_for_production_is_new_private_set_from_the_file_and_never_printed(tmp_path: Path) -> None:
    folder = tmp_path / "home" / ".config" / "frameteller"
    folder.mkdir(parents=True)
    (folder / "judge-production.token").write_text("the-old-token")

    result, folder = rotate(tmp_path, "judge", "production")

    assert result.returncode == 0, result.stderr
    new = (folder / "judge-production.token").read_text()
    assert len(new) >= 40
    assert new != "the-old-token"
    assert (folder / "judge-production.token.old").read_text() == "the-old-token"
    assert stat.S_IMODE((folder / "judge-production.token").stat().st_mode) == 0o600
    assert (tmp_path / "secret").read_text() == new  # gh read the secret from the file, on stdin
    calls = (tmp_path / "gh.log").read_text().splitlines()
    assert calls[0] == "secret set JUDGE_TOKEN --env production -R example/repo"
    assert "workflow run deploy-production.yml -R example/repo --ref v1.1.0" in calls  # the release, never main
    assert new not in result.stdout + result.stderr
    assert new not in (tmp_path / "gh.log").read_text()


def test_an_admin_token_for_staging_deploys_main(tmp_path: Path) -> None:
    result, folder = rotate(tmp_path, "admin", "staging")

    assert result.returncode == 0, result.stderr
    assert not (folder / "admin-staging.token.old").exists()  # nothing to keep the first time
    calls = (tmp_path / "gh.log").read_text().splitlines()
    assert calls == [
        "secret set ADMIN_TOKEN --env staging -R example/repo",
        "workflow run deploy-staging.yml -R example/repo --ref main",
    ]
    assert (folder / "admin-staging.token").read_text() not in result.stdout


@pytest.mark.parametrize("args", [(), ("judge",), ("visitor", "staging"), ("judge", "prod")])
def test_anything_else_is_refused_before_touching_a_file(tmp_path: Path, args: tuple[str, ...]) -> None:
    result, folder = rotate(tmp_path, *args)
    assert result.returncode == 2
    assert "usage" in result.stderr
    assert not folder.exists()
    assert not (tmp_path / "gh.log").exists()
