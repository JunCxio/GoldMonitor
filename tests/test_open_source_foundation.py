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
