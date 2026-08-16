import re
from pathlib import Path

import yaml

POSTPROVISION_MODULES = [
    "lifecycle_ops.provisioning.knowledge_bases",
    "lifecycle_ops.provisioning.toolboxes",
]
POSTDEPLOY_MODULES = [
    "lifecycle_ops.provisioning.rbac",
    "lifecycle_ops.provisioning.continuous_eval",
]


def _invoked_modules(path: Path) -> list[str]:
    return re.findall(
        r"python -m ([a-zA-Z0-9_.]+)",
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
        assert "artifacts/continuous-evaluation.json" in source


def test_azure_yaml_declares_existing_platform_hooks() -> None:
    config = yaml.safe_load(Path("azure.yaml").read_text(encoding="utf-8"))

    assert config["infra"]["path"] == "deploy/infra"
    for event in ("postprovision", "postdeploy"):
        for platform in ("posix", "windows"):
            hook = config["hooks"][event][platform]
            assert hook["shell"] in {"sh", "pwsh"}
            assert Path(hook["run"]).is_file()
