#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import io
import os
import stat
import tarfile
import time
from pathlib import Path


PACKAGE = "tg-video-downloader"
VERSION = "0.1.0"


def tar_gz(files: list[tuple[str, bytes, int]]) -> bytes:
    raw = io.BytesIO()
    with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode="w") as tar:
            for name, data, mode in files:
                info = tarfile.TarInfo(name)
                info.size = len(data)
                info.mode = mode
                info.mtime = 0
                info.uid = 0
                info.gid = 0
                info.uname = "root"
                info.gname = "root"
                tar.addfile(info, io.BytesIO(data))
    return raw.getvalue()


def ar_member(name: str, data: bytes) -> bytes:
    if len(name) > 16:
        raise ValueError(f"ar member name too long: {name}")
    header = (
        f"{name:<16}"
        f"{int(time.time()):<12}"
        f"{0:<6}"
        f"{0:<6}"
        f"{0o100644:<8}"
        f"{len(data):<10}`\n"
    ).encode("ascii")
    body = data + (b"\n" if len(data) % 2 else b"")
    return header + body


def read_file(path: Path) -> bytes:
    return path.read_bytes()


def should_package_source(file: Path) -> bool:
    if "__pycache__" in file.parts:
        return False
    if file.suffix in {".pyc", ".pyo"}:
        return False
    if ".bak-" in file.name:
        return False
    return True


def collect_data_files(root: Path) -> list[tuple[str, bytes, int]]:
    app_files: list[tuple[str, bytes, int]] = []
    include = [
        "app",
        "requirements.txt",
        "README.md",
        "LICENSE",
        ".env.example",
    ]
    for item in include:
        path = root / item
        if path.is_dir():
            for file in sorted(path.rglob("*")):
                if file.is_file() and should_package_source(file):
                    rel = file.relative_to(root).as_posix()
                    app_files.append((f"./opt/{PACKAGE}/{rel}", read_file(file), 0o644))
        elif path.exists():
            app_files.append((f"./opt/{PACKAGE}/{item}", read_file(path), 0o644))

    openwrt = root / "packaging" / "openwrt"
    app_files.extend(
        [
            (
                f"./opt/{PACKAGE}/install_deps.sh",
                read_file(openwrt / "install_deps.sh"),
                0o755,
            ),
            (
                f"./etc/init.d/{PACKAGE}",
                read_file(openwrt / f"{PACKAGE}.init"),
                0o755,
            ),
            (
                f"./etc/{PACKAGE}.env",
                read_file(openwrt / f"{PACKAGE}.env"),
                0o600,
            ),
        ]
    )
    return app_files


def build(root: Path, output: Path, arch: str, version: str) -> Path:
    control = f"""Package: {PACKAGE}
Version: {version}
Architecture: {arch}
Maintainer: TG Resource Downloader contributors
Section: net
Priority: optional
Depends: python3, python3-pip
Description: Telegram resource downloader with FastAPI web UI
"""
    conffiles = f"/etc/{PACKAGE}.env\n"
    postinst = f"""#!/bin/sh
set -e
chmod +x /etc/init.d/{PACKAGE} /opt/{PACKAGE}/install_deps.sh
if /opt/{PACKAGE}/install_deps.sh /opt/{PACKAGE}; then
    echo "Dependencies installed."
else
    echo "Dependency installation failed. Check network access and run: /opt/{PACKAGE}/install_deps.sh" >&2
fi
/etc/init.d/{PACKAGE} enable || true
echo "Edit /etc/{PACKAGE}.env, then run: /etc/init.d/{PACKAGE} start"
exit 0
"""
    prerm = f"""#!/bin/sh
/etc/init.d/{PACKAGE} stop >/dev/null 2>&1 || true
/etc/init.d/{PACKAGE} disable >/dev/null 2>&1 || true
exit 0
"""

    control_tar = tar_gz(
        [
            ("./control", control.encode(), 0o644),
            ("./conffiles", conffiles.encode(), 0o644),
            ("./postinst", postinst.encode(), 0o755),
            ("./prerm", prerm.encode(), 0o755),
        ]
    )
    data_tar = tar_gz(collect_data_files(root))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(
        b"!<arch>\n"
        + ar_member("debian-binary", b"2.0\n")
        + ar_member("control.tar.gz", control_tar)
        + ar_member("data.tar.gz", data_tar)
    )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an OpenWrt .ipk package.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--arch", default="all")
    parser.add_argument("--version", default=VERSION)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output or root / "dist" / f"{PACKAGE}_{args.version}_{args.arch}.ipk"
    built = build(root, output, args.arch, args.version)
    print(built)


if __name__ == "__main__":
    main()
