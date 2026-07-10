import re
import subprocess
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


def test_windows_contract_checks_socket_token_in_frontend_asset():
    contract_checks = read_text("tests/contract_checks.ps1")

    assert (
        'Assert-Contains -Path "static\\app.js" -Pattern '
        "'auth:\\s*\\{\\s*token:\\s*SOCKET_ACCESS_TOKEN\\s*\\}'"
        in contract_checks
    )
    assert (
        'Assert-Contains -Path "templates\\index.html" -Pattern '
        "'auth:\\s*\\{\\s*token:\\s*SOCKET_ACCESS_TOKEN\\s*\\}'"
        not in contract_checks
    )


def test_powershell_contract_literal_assertions_match_their_target_files():
    assertion_pattern = re.compile(
        r'^(Assert-(?:Not)?Contains) -Path "([^"]+)" -Pattern '
        r"'((?:[^']|'')*)'"
    )
    failures = []

    for line_number, line in enumerate(
        read_text("tests/contract_checks.ps1").splitlines(),
        start=1,
    ):
        match = assertion_pattern.match(line)
        if not match:
            continue

        command, relative_path, pattern = match.groups()
        content = read_text(relative_path.replace("\\", "/"))
        pattern = pattern.replace("''", "'")
        matched = re.search(pattern, content, flags=re.IGNORECASE) is not None
        expected = command == "Assert-Contains"
        if matched != expected:
            failures.append(
                f"line {line_number}: {command} {relative_path} {pattern!r}"
            )

    assert failures == []


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
    assert "py -3.12 -m venv .venv" in contributing
    assert "python3.12 -m venv .venv" in contributing
    assert r".\.venv\Scripts\python.exe app.py --web" in contributing
    assert ".venv/bin/python app.py --web" in contributing
    assert "Conventional Commits" in contributing
    assert "API Key" in contributing
    assert "SMTP 授权码" in contributing
    assert "Webhook URL" in contributing
    assert (
        "https://github.com/JunCxio/GoldMonitor/security/advisories/new" in security
    )
    assert "公开 Issue" in security
    assert "吊销或轮换" in security
    assert "重新协商" in security
    assert "Contributor Covenant 2.1" in conduct
    assert "行为准则举报" in conduct
    assert (
        "https://github.com/JunCxio/GoldMonitor/security/advisories/new" in conduct
    )


def test_issue_and_pull_request_templates_route_reports_safely():
    bug = read_text(".github/ISSUE_TEMPLATE/bug_report.yml")
    feature = read_text(".github/ISSUE_TEMPLATE/feature_request.yml")
    config = read_text(".github/ISSUE_TEMPLATE/config.yml")
    pull_request = read_text(".github/pull_request_template.md")
    privacy_markers = (
        "API Key",
        "SMTP 授权码",
        "Webhook URL",
        "本地路径",
        "完整诊断数据",
    )

    for template in (bug, feature, pull_request):
        for marker in privacy_markers:
            assert marker in template

    assert "blank_issues_enabled: false" in config
    assert (
        "https://github.com/JunCxio/GoldMonitor/security/advisories/new" in config
    )
    assert "本地路径" in config
    assert "完整诊断数据" in config
    assert "复现步骤" in bug
    assert "用户问题" in feature
    assert "验证结果" in pull_request
    assert "隐私" in pull_request


def test_readme_uses_canonical_contribution_and_security_entries():
    readme = read_text("README.md")

    assert "python scripts/run_checks.py" in readme
    assert "[贡献指南](CONTRIBUTING.md)" in readme
    assert "[安全策略](SECURITY.md)" in readme
    assert "[MIT License](LICENSE)" in readme
    assert "py -3.12 -m venv .venv" in readme
    assert "python3.12 -m venv .venv" in readme
    assert "tests\\gold_cache_check.py" not in readme
    assert "tests/gold_cache_check.py" not in readme


def test_workflows_use_node_24_action_versions():
    for relative_path in (
        ".github/workflows/ci.yml",
        ".github/workflows/release.yml",
    ):
        workflow = read_text(relative_path)
        checkout_versions = re.findall(
            r"actions/checkout@([A-Za-z0-9._-]+)",
            workflow,
        )
        setup_python_versions = re.findall(
            r"actions/setup-python@([A-Za-z0-9._-]+)",
            workflow,
        )

        assert checkout_versions
        assert setup_python_versions
        assert set(checkout_versions) == {"v5"}
        assert set(setup_python_versions) == {"v6"}


def test_docs_directory_is_not_ignored_by_repository_rules():
    ignore_result = subprocess.run(
        [
            "git",
            "-c",
            "core.excludesFile=/dev/null",
            "check-ignore",
            "--no-index",
            "docs/.contract-probe",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    ignore_rules = {
        line.strip()
        for line in read_text(".gitignore").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert ignore_result.returncode == 1, (
        "docs/.contract-probe is ignored by repository rules:\n"
        f"stdout: {ignore_result.stdout}\n"
        f"stderr: {ignore_result.stderr}"
    )
    assert ".DS_Store" in ignore_rules
