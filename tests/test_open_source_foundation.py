from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_text(relative_path):
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_repository_uses_confirmed_mit_license():
    license_path = ROOT / "LICENSE"

    assert license_path.exists()
    text = license_path.read_text(encoding="utf-8")
    assert text.startswith("MIT License")
    assert "Copyright (c) 2026 JunCxio" in text
    assert "Permission is hereby granted, free of charge" in text
    assert 'THE SOFTWARE IS PROVIDED "AS IS"' in text


def test_readme_declares_mit_license():
    readme = read_text("README.md")

    assert "## 许可证" in readme
    assert "[MIT License](LICENSE)" in readme


def test_pull_request_ci_runs_supported_platform_checks():
    workflow = read_text(".github/workflows/ci.yml")

    assert "pull_request:" in workflow
    assert 'branches: ["main"]' in workflow
    assert "contents: read" in workflow
    assert "fail-fast: false" in workflow
    assert "windows-latest" in workflow
    assert "macos-latest" in workflow
    assert 'python-version: "3.12"' in workflow
    assert "python scripts/run_checks.py" in workflow
    assert "cancel-in-progress: true" in workflow
    assert "upload-artifact" not in workflow
    assert "softprops/action-gh-release" not in workflow


def test_release_workflow_reuses_unified_check_entry():
    workflow = read_text(".github/workflows/release.yml")

    assert workflow.count("python scripts/run_checks.py") == 2
    assert "python -m py_compile app.py" not in workflow
    assert "python tests/risk_contract_check.py" not in workflow
    assert "python tests/frontend_asset_check.py" not in workflow
    assert "pyinstaller --clean --noconfirm GoldMonitor.spec" in workflow
    assert "PYTHON_BIN=python scripts/build_macos_dmg.sh" in workflow


def test_community_docs_define_contribution_and_private_reporting():
    contributing = read_text("CONTRIBUTING.md")
    security = read_text("SECURITY.md")
    conduct = read_text("CODE_OF_CONDUCT.md")

    assert "python scripts/run_checks.py" in contributing
    assert "Conventional Commits" in contributing
    assert "API Key" in contributing
    assert "SMTP 授权码" in contributing
    assert "Webhook URL" in contributing
    assert "security/advisories/new" in security
    assert "公开 Issue" in security
    assert "Contributor Covenant 2.1" in conduct
    assert "行为准则举报" in conduct
    assert "security/advisories/new" in conduct
