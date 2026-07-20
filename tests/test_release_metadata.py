from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class ReleaseMetadataTests(unittest.TestCase):
    def test_versions_are_consistent(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts/verify_release_versions.py"), "--tag", "v0.2.0"],
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
            archive = output / "contextlease-native-windows-x86_64-v0.2.0.zip"
            self.assertTrue(archive.is_file())
            self.assertGreater(archive.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
