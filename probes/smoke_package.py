"""Build and import the local wheel from an isolated source copy."""

import os
import shutil
import subprocess
import sys
import uuid
import zipfile
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    home = root / "probes" / ".probe-state" / ("package-" + uuid.uuid4().hex[:8])
    source = home / "source"
    source.mkdir(parents=True)
    shutil.copy2(root / "pyproject.toml", source / "pyproject.toml")
    shutil.copy2(root / "README.md", source / "README.md")
    shutil.copy2(root / "README.zh-CN.md", source / "README.zh-CN.md")
    shutil.copy2(root / "LICENSE", source / "LICENSE")
    shutil.copy2(root / "NOTICE", source / "NOTICE")
    shutil.copytree(root / "agentrunner", source / "agentrunner",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    temporary = home / "tmp"
    temporary.mkdir()
    (source / "dist").mkdir()
    env = os.environ.copy()
    env.update({"TMP": str(temporary), "TEMP": str(temporary), "TMPDIR": str(temporary)})
    built = subprocess.run([sys.executable, "-c", "import setuptools.build_meta as backend; backend.build_wheel('dist')"],
                           cwd=source, env=env, capture_output=True, text=True, timeout=60)
    assert built.returncode == 0, built.stderr + built.stdout
    wheels = list((source / "dist").glob("*.whl"))
    assert len(wheels) == 1, wheels
    with zipfile.ZipFile(wheels[0]) as archive:
        names = set(archive.namelist())
    required = {"agentrunner/ui.html", "agentrunner/contract.md", "agentrunner/README.md",
                "agentrunner/structure.md", "agentrunner/cli.py"}
    assert required <= names, required - names
    site = home / "site"
    installed = subprocess.run([sys.executable, "-m", "pip", "install", "--no-cache-dir", "--no-deps", "--target", str(site),
                                str(wheels[0])], cwd=source, env=env, capture_output=True, text=True, timeout=60)
    assert installed.returncode == 0, installed.stderr + installed.stdout
    env["PYTHONPATH"] = str(site)
    invoked = subprocess.run([sys.executable, "-m", "agentrunner", "--help"], cwd=home, env=env,
                             capture_output=True, text=True, timeout=10)
    assert invoked.returncode == 0 and "submit" in invoked.stdout and "UNKNOWN_SUBMISSION" in invoked.stdout
    print({"wheel": wheels[0].name, "package_data": "complete", "installed_cli": "ok"})


if __name__ == "__main__":
    main()
