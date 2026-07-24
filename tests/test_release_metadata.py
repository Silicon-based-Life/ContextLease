from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest
import zipfile

from scripts.prepare_dotnet_native_assets import PLATFORMS, VERSION, prepare_assets

ROOT = pathlib.Path(__file__).resolve().parents[1]


class ReleaseMetadataTests(unittest.TestCase):
    def test_versions_are_consistent(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts/verify_release_versions.py"), "--tag", "v0.3.0"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_native_packager_contains_headers_and_qualified_library(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = pathlib.Path(temp)
            fake_library = temp_path / "contextlease_native.dll"
            fake_library.write_bytes(b"native")
            output = temp_path / "dist"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/package_native.py"),
                    "--platform",
                    "windows-x86_64",
                    "--library",
                    str(fake_library),
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                check=True,
            )
            archive = output / "contextlease-native-windows-x86_64-v0.3.0.zip"
            self.assertTrue(archive.is_file())
            self.assertGreater(archive.stat().st_size, 0)

    def test_dotnet_native_assets_are_prepared_for_every_rid(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            artifacts = root / "artifacts"
            project = root / "project"
            artifacts.mkdir()
            for platform_name, (_, library_name) in PLATFORMS.items():
                archive = artifacts / f"contextlease-native-{platform_name}-v{VERSION}.zip"
                package_root = f"contextlease-native-{platform_name}-v{VERSION}"
                with zipfile.ZipFile(archive, "w") as output:
                    output.writestr(f"{package_root}/lib/{library_name}", b"native")
            written = prepare_assets(artifacts, project)
            self.assertEqual(len(PLATFORMS), len(written))
            self.assertTrue(all(path.read_bytes() == b"native" for path in written))


if __name__ == "__main__":
    unittest.main()
