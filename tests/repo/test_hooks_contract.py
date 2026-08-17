import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

POSTPROVISION_MODULES = [
    # Observability first: the agents read APPLICATIONINSIGHTS_CONNECTION_STRING at
    # deploy time, so the resource and the project connection must exist before then.
    "lifecycle_ops.provisioning.observability",
    "lifecycle_ops.provisioning.knowledge_bases",
    "lifecycle_ops.provisioning.toolboxes",
]
POSTDEPLOY_MODULES = [
    "lifecycle_ops.provisioning.rbac",
]


def _invoked_modules(path: Path) -> list[str]:
    return re.findall(
        r"(?:python|run_python|Invoke-Python)\s+['\"]?-m['\"]?\s+['\"]?([a-zA-Z0-9_.]+)",
        path.read_text(encoding="utf-8"),
    )


def test_hook_platform_variants_have_identical_order() -> None:
    assert _invoked_modules(Path("deploy/hooks/postprovision.sh")) == POSTPROVISION_MODULES
    assert _invoked_modules(Path("deploy/hooks/postprovision.ps1")) == POSTPROVISION_MODULES
    assert _invoked_modules(Path("deploy/hooks/postdeploy.sh")) == POSTDEPLOY_MODULES
    assert _invoked_modules(Path("deploy/hooks/postdeploy.ps1")) == POSTDEPLOY_MODULES


def test_postprovision_does_not_require_deployed_agents() -> None:
    modules = _invoked_modules(Path("deploy/hooks/postprovision.sh"))

    assert "lifecycle_ops.provisioning.rbac" not in modules
    assert "lifecycle_ops.provisioning.continuous_eval" not in modules


def test_postdeploy_does_not_enable_operate_controls_before_evaluation() -> None:
    for path in (
        Path("deploy/hooks/postdeploy.sh"),
        Path("deploy/hooks/postdeploy.ps1"),
    ):
        assert "lifecycle_ops.provisioning.continuous_eval" not in _invoked_modules(path)


def test_hooks_preserve_deployment_artifacts_on_both_platforms() -> None:
    for path in (
        Path("deploy/hooks/postprovision.sh"),
        Path("deploy/hooks/postprovision.ps1"),
    ):
        source = path.read_text(encoding="utf-8")
        assert "artifacts/knowledge-bases.json" in source

    for path in (
        Path("deploy/hooks/postdeploy.sh"),
        Path("deploy/hooks/postdeploy.ps1"),
    ):
        source = path.read_text(encoding="utf-8")
        assert "artifacts/rbac.json" in source


def test_windows_hooks_stop_after_each_failed_native_command() -> None:
    for path, expected_checks in (
        (Path("deploy/hooks/postprovision.ps1"), 3),
        (Path("deploy/hooks/postdeploy.ps1"), 1),
    ):
        source = path.read_text(encoding="utf-8")
        assert source.count("$LASTEXITCODE -ne 0") == expected_checks
        assert source.count("exit $LASTEXITCODE") == expected_checks


def test_posix_hooks_fall_back_to_uv_when_python_is_unavailable(tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip("POSIX hooks require /bin/sh")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    uv_log = tmp_path / "uv.log"
    uv = bin_dir / "uv"
    uv.write_text(
        '#!/bin/sh\nprintf "%s\\n" "$*" >> "$UV_LOG"\n',
        encoding="utf-8",
    )
    uv.chmod(0o755)
    mkdir = bin_dir / "mkdir"
    mkdir.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    mkdir.chmod(0o755)
    env = {
        **os.environ,
        "PATH": str(bin_dir),
        "UV_LOG": str(uv_log),
    }

    for hook, expected_invocations in (
        (Path("deploy/hooks/postprovision.sh"), 3),
        (Path("deploy/hooks/postdeploy.sh"), 1),
    ):
        uv_log.unlink(missing_ok=True)
        completed = subprocess.run(
            ["/bin/sh", str(hook)],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

        assert completed.returncode == 0, completed.stderr
        invocations = uv_log.read_text(encoding="utf-8").splitlines()
        assert len(invocations) == expected_invocations
        assert all(
            invocation.startswith(
                "run --no-project --python 3.13 --prerelease=allow "
                "--with-requirements requirements-ops.txt python -m "
            )
            for invocation in invocations
        )


def test_windows_hooks_fall_back_to_uv_when_python_is_unavailable(tmp_path: Path) -> None:
    pwsh = shutil.which("pwsh")
    if pwsh is None:
        pytest.skip("PowerShell is not installed")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    uv_log = tmp_path / "uv.log"
    if os.name == "nt":
        # PowerShell on Windows cannot execute a shebang script, so the stand-in has
        # to be a batch shim for `Get-Command uv` to resolve and run it.
        uv = bin_dir / "uv.cmd"
        uv.write_text('@echo off\r\n>>"%UV_LOG%" echo %*\r\n', encoding="utf-8")
    else:
        uv = bin_dir / "uv"
        uv.write_text(
            '#!/bin/sh\nprintf "%s\\n" "$*" >> "$UV_LOG"\n',
            encoding="utf-8",
        )
        uv.chmod(0o755)
    env = {
        **os.environ,
        "PATH": str(bin_dir),
        "UV_LOG": str(uv_log),
    }

    for hook, expected_invocations in (
        (Path("deploy/hooks/postprovision.ps1"), 3),
        (Path("deploy/hooks/postdeploy.ps1"), 1),
    ):
        uv_log.unlink(missing_ok=True)
        completed = subprocess.run(
            [pwsh, "-NoProfile", "-File", str(hook)],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

        assert completed.returncode == 0, completed.stderr
        invocations = uv_log.read_text(encoding="utf-8").splitlines()
        assert len(invocations) == expected_invocations
        assert all(
            invocation.startswith(
                "run --no-project --python 3.13 --prerelease=allow "
                "--with-requirements requirements-ops.txt python -m "
            )
            for invocation in invocations
        )


def test_azure_yaml_declares_existing_platform_hooks() -> None:
    config = yaml.safe_load(Path("azure.yaml").read_text(encoding="utf-8"))

    assert config["infra"]["path"] == "deploy/infra"
    for event in ("postprovision", "postdeploy"):
        for platform in ("posix", "windows"):
            hook = config["hooks"][event][platform]
            assert hook["shell"] in {"sh", "pwsh"}
            assert Path(hook["run"]).is_file()
