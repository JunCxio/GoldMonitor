import os
import tempfile


os.environ.setdefault(
    "APPDATA",
    tempfile.mkdtemp(prefix="goldmonitor-pytest-appdata-"),
)
