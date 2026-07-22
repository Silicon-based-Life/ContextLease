from __future__ import annotations

import platform
import shutil
import subprocess
from pathlib import Path

from setuptools import setup
from setuptools.command.bdist_wheel import bdist_wheel as _bdist_wheel
from setuptools.command.build_py import build_py as _build_py


ROOT = Path(__file__).parent.resolve()


def native_name() -> str:
    if platform.system() == "Windows":
        return "contextlease_native.dll"
    if platform.system() == "Darwin":
        return "libcontextlease_native.dylib"
    return "libcontextlease_native.so"


class build_py(_build_py):
    def run(self) -> None:
        subprocess.run(
            ["cargo", "build", "--release", "-p", "contextlease-ffi"],
            cwd=ROOT,
            check=True,
        )
        super().run()
        source = ROOT / "target" / "release" / native_name()
        target = Path(self.build_lib) / "contextlease" / "native" / native_name()
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


class bdist_wheel(_bdist_wheel):
    def finalize_options(self) -> None:
        super().finalize_options()
        self.root_is_pure = False

    def get_tag(self) -> tuple[str, str, str]:
        _, _, platform_tag = super().get_tag()
        return "py3", "none", platform_tag


setup(cmdclass={"build_py": build_py, "bdist_wheel": bdist_wheel})
