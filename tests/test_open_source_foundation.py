import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_text(relative_path):
    return (ROOT / relative_path).read_text(encoding="utf-8")


def requirement_lines(relative_path):
    return [
        line.strip()
        for line in read_text(relative_path).splitlines()
        if line.strip()
        and not line.lstrip().startswith("#")
    ]


def canonical_requirement_name(line):
    name = line.split("==", maxsplit=1)[0].split("[", maxsplit=1)[0]
    return re.sub(r"[-_.]+", "-", name).lower()


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
    assert "Build Windows test installer" in workflow
    assert "needs: checks" in workflow
    assert "pyinstaller --clean --noconfirm GoldMonitor.spec" in workflow
    assert "actions/upload-artifact@v7" in workflow
    assert "windows-pr-${{ github.event.pull_request.number }}" in workflow
    assert "retention-days: 7" in workflow
    assert "softprops/action-gh-release" not in workflow


def test_windows_contract_checks_socket_token_in_frontend_asset():
    contract_checks = read_text("tests/contract_checks.ps1")

    assert (
        'Assert-Contains -Path "static\\app-state.js" -Pattern '
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
    def action_versions(workflow, action):
        pattern = re.compile(
            rf"^[ \t]*(?:-[ \t]+)?uses:[ \t]*(?P<quote>[\"']?)"
            rf"{re.escape(action)}@(?P<version>[^\"'\s#]+)"
            r"(?P=quote)[ \t]*(?:#.*)?$",
            flags=re.MULTILINE,
        )
        return [
            match.group("version")
            for match in pattern.finditer(workflow)
        ]

    workflow = "\n".join(
        read_text(relative_path)
        for relative_path in (
            ".github/workflows/ci.yml",
            ".github/workflows/release.yml",
        )
    )
    expected_versions = {
        "actions/checkout": "v7",
        "actions/setup-python": "v6",
        "actions/upload-artifact": "v7",
        "actions/download-artifact": "v8",
        "softprops/action-gh-release": "v3",
    }

    for action, expected_version in expected_versions.items():
        versions = action_versions(workflow, action)

        assert versions
        assert set(versions) == {expected_version}


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


def test_dependabot_updates_python_and_actions_weekly():
    config = read_text('.github/dependabot.yml')
    expected = '''version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
    target-branch: "main"
    open-pull-requests-limit: 5
    groups:
      python-dependencies:
        applies-to: "version-updates"
        patterns:
          - "*"
    commit-message:
      prefix: "chore"
      include: "scope"

  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
    target-branch: "main"
    open-pull-requests-limit: 5
    groups:
      github-actions:
        applies-to: "version-updates"
        patterns:
          - "*"
    commit-message:
      prefix: "chore"
      include: "scope"
'''

    assert config == expected


def test_python_dependencies_are_locked_per_supported_platform():
    assert requirement_lines("requirements-build.txt") == ["pyinstaller>=6.0,<7.0"]
    pinned_requirement = re.compile(
        r"^[A-Za-z0-9_.-]+(?:\[[^\]]+\])?==[^ ;]+(?:\s*;\s*.+)?$"
    )
    windows_lines = requirement_lines("constraints/windows-py312.txt")
    macos_lines = requirement_lines("constraints/macos-py312.txt")

    assert all(pinned_requirement.fullmatch(line) for line in windows_lines)
    assert all(pinned_requirement.fullmatch(line) for line in macos_lines)

    windows_names = {
        canonical_requirement_name(line)
        for line in windows_lines
    }
    macos_names = {
        canonical_requirement_name(line)
        for line in macos_lines
    }

    expected_windows_names = {
        "altgraph",
        "bidict",
        "blinker",
        "bottle",
        "certifi",
        "cffi",
        "charset-normalizer",
        "click",
        "clr-loader",
        "colorama",
        "flask",
        "flask-socketio",
        "h11",
        "idna",
        "iniconfig",
        "itsdangerous",
        "jinja2",
        "markupsafe",
        "packaging",
        "pefile",
        "pillow",
        "pluggy",
        "proxy-tools",
        "pycparser",
        "pygments",
        "pyinstaller",
        "pyinstaller-hooks-contrib",
        "pystray",
        "pytest",
        "python-engineio",
        "python-socketio",
        "pythonnet",
        "pywebview",
        "pywin32-ctypes",
        "requests",
        "setuptools",
        "simple-websocket",
        "six",
        "typing-extensions",
        "urllib3",
        "werkzeug",
        "win11toast",
        "winrt-runtime",
        "winrt-windows-data-xml-dom",
        "winrt-windows-foundation",
        "winrt-windows-foundation-collections",
        "winrt-windows-globalization",
        "winrt-windows-graphics-imaging",
        "winrt-windows-media-core",
        "winrt-windows-media-ocr",
        "winrt-windows-media-playback",
        "winrt-windows-media-speechsynthesis",
        "winrt-windows-storage",
        "winrt-windows-storage-streams",
        "winrt-windows-ui-notifications",
        "wsproto",
    }
    expected_macos_names = {
        "altgraph",
        "bidict",
        "blinker",
        "bottle",
        "certifi",
        "charset-normalizer",
        "click",
        "flask",
        "flask-socketio",
        "h11",
        "idna",
        "iniconfig",
        "itsdangerous",
        "jinja2",
        "macholib",
        "markupsafe",
        "packaging",
        "pluggy",
        "proxy-tools",
        "pygments",
        "pyinstaller",
        "pyinstaller-hooks-contrib",
        "pyobjc-core",
        "pyobjc-framework-cocoa",
        "pyobjc-framework-quartz",
        "pyobjc-framework-security",
        "pyobjc-framework-uniformtypeidentifiers",
        "pyobjc-framework-webkit",
        "pytest",
        "python-engineio",
        "python-socketio",
        "pywebview",
        "requests",
        "setuptools",
        "simple-websocket",
        "typing-extensions",
        "urllib3",
        "werkzeug",
        "wsproto",
    }

    assert windows_names == expected_windows_names
    assert macos_names == expected_macos_names


def test_ci_and_release_use_platform_constraints():
    ci = read_text(".github/workflows/ci.yml")
    release = read_text(".github/workflows/release.yml")
    assert "constraints/windows-py312.txt" in ci
    assert "constraints/macos-py312.txt" in ci
    assert re.search(
        r"(?m)^[ \t]*- os: windows-latest\r?\n"
        r"[ \t]+constraints: constraints/windows-py312\.txt$",
        ci,
    )
    assert re.search(
        r"(?m)^[ \t]*- os: macos-latest\r?\n"
        r"[ \t]+constraints: constraints/macos-py312\.txt$",
        ci,
    )
    assert "pip install -r requirements.txt -c ${{ matrix.constraints }}" in ci
    assert (
        "pip install -r requirements.txt -r requirements-build.txt "
        "-c constraints/windows-py312.txt"
    ) in release
    assert (
        "pip install -r requirements.txt -r requirements-build.txt "
        "-c constraints/macos-py312.txt"
    ) in release
    assert "pip install -r requirements.txt pyinstaller" not in release


def test_dependency_docs_use_reproducible_install_commands():
    contributing = read_text("CONTRIBUTING.md")
    readme = read_text("README.md")
    windows_install = (
        r".\.venv\Scripts\pip.exe install -r requirements.txt "
        r"-r requirements-build.txt -c constraints\windows-py312.txt"
    )
    macos_install = (
        ".venv/bin/pip install -r requirements.txt "
        "-r requirements-build.txt -c constraints/macos-py312.txt"
    )
    windows_compile = (
        "uv pip compile requirements.txt requirements-build.txt "
        "--python-version 3.12 --python-platform windows "
        "--output-file constraints/windows-py312.txt"
    )
    macos_compile = (
        "uv pip compile requirements.txt requirements-build.txt "
        "--python-version 3.12 --python-platform macos "
        "--output-file constraints/macos-py312.txt"
    )
    for document in (contributing, readme):
        assert windows_install in document
        assert macos_install in document
        assert "install -r requirements.txt pyinstaller" not in document
    assert "uv 0.11.21" in contributing
    assert windows_compile in contributing
    assert macos_compile in contributing
    assert "增加 `--upgrade`" in contributing
    assert "--upgrade-package <包名>" in contributing
    assert "记录 `uv --version` 的输出" in contributing
    assert "Windows 和 macOS 的 CI 均通过" in contributing
    assert "确保本地与 CI/Release 的依赖版本一致" in readme
    assert (
        "依赖锁定更新规则参见 [贡献指南]"
        "(CONTRIBUTING.md#更新依赖锁定)"
    ) in readme
