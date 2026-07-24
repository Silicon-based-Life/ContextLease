from __future__ import annotations

import argparse
import pathlib
import subprocess
import tempfile

PROJECT = """\
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net8.0</TargetFramework>
    <ImplicitUsings>enable</ImplicitUsings>
    <Nullable>enable</Nullable>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="ContextLease.Managed" Version="{version}" />
  </ItemGroup>
</Project>
"""

PROGRAM = """\
using ContextLease;

if (ContextLeaseArena.AbiVersion != ContextLeaseArena.SupportedAbiVersion)
    throw new InvalidOperationException("Installed NuGet native ABI mismatch.");
Console.WriteLine($"ContextLease NuGet consumer passed: ABI={ContextLeaseArena.AbiVersion}");
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute an isolated NuGet consumer.")
    parser.add_argument("--source", default="dist", type=pathlib.Path)
    parser.add_argument("--version", default="0.3.0")
    args = parser.parse_args()
    source = args.source.resolve()
    with tempfile.TemporaryDirectory(prefix="contextlease-nuget-") as temp:
        root = pathlib.Path(temp)
        (root / "Consumer.csproj").write_text(
            PROJECT.format(version=args.version),
            encoding="utf-8",
        )
        (root / "Program.cs").write_text(PROGRAM, encoding="utf-8")
        subprocess.run(
            [
                "dotnet",
                "restore",
                str(root / "Consumer.csproj"),
                "--source",
                str(source),
            ],
            check=True,
        )
        subprocess.run(
            [
                "dotnet",
                "run",
                "--project",
                str(root / "Consumer.csproj"),
                "--configuration",
                "Release",
                "--no-restore",
            ],
            check=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
