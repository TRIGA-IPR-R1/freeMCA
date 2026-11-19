#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Copyright (C) 2026 Daniel Batista, Thalles Campagnani
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Download the current freeMCA FPGA toolchain into this directory.

Place-and-route comes from **openXC7/nextpnr** (himbaechel / Xilinx
micro-architecture), not from the archived openXC7/nextpnr-xilinx 0.9.8
line and not from the snap.

The upstream tarball still ships the binary as `nextpnr-xilinx` so old
Makefiles keep working. After extract this script also installs
`nextpnr-himbaechel` as the same engine.

Sources (GitHub release tarballs, no snap, no Nix):

* openXC7 toolchain: cavearr/toolchain-openxc7-releases, matched to
  HEAD of https://github.com/openXC7/nextpnr
* Yosys / iverilog / openFPGALoader: YosysHQ/oss-cad-suite-build

    python3 tools/download_toolchain.py
    source tools/env.sh
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import ssl
import sys
import tarfile
import urllib.error
import urllib.request
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
OPENXC7_API = (
    "https://api.github.com/repos/cavearr/toolchain-openxc7-releases/releases"
)
NEXTPNR_HEAD_API = "https://api.github.com/repos/openXC7/nextpnr/commits/main"
OSS_CAD_API = (
    "https://api.github.com/repos/YosysHQ/oss-cad-suite-build/releases/tags/{tag}"
)
ARCHIVED_NEXTPNR_XILINX_PREFIXES = ("0eae9fbb", "cbabb65")  # 0.9.7 / 0.9.8 line
USER_AGENT = "freeMCA-toolchain-downloader"


def host_platforms() -> tuple[str, str]:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "linux" and machine in ("x86_64", "amd64"):
        return "linux-x86-64", "linux-x64"
    if system == "linux" and machine in ("aarch64", "arm64"):
        return "linux-arm64", "linux-arm64"
    if system == "darwin" and machine in ("arm64", "aarch64"):
        return "darwin-arm64", "darwin-arm64"
    if system == "darwin" and machine in ("x86_64", "amd64"):
        return "darwin-x64", "darwin-x64"
    if system == "windows" and machine in ("x86_64", "amd64"):
        return "windows-amd64", "windows-x64"
    raise SystemExit(f"unsupported host: {system} {machine}")


def opener() -> urllib.request.OpenerDirector:
    ctx = ssl.create_default_context()
    handlers = [urllib.request.HTTPSHandler(context=ctx)]
    op = urllib.request.build_opener(*handlers)
    op.addheaders = [("User-Agent", USER_AGENT)]
    return op


def api_json(op: urllib.request.OpenerDirector, url: str) -> object:
    try:
        with op.open(url) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"GitHub API failed ({exc.code}): {url}") from exc


def github_head_sha(op: urllib.request.OpenerDirector) -> str:
    payload = api_json(op, NEXTPNR_HEAD_API)
    if not isinstance(payload, dict) or not payload.get("sha"):
        raise SystemExit("could not read HEAD of openXC7/nextpnr")
    return str(payload["sha"])


def release_build_info(op: urllib.request.OpenerDirector, release: dict) -> dict:
    for asset in release.get("assets") or []:
        if asset.get("name") == "BUILD-INFO.json":
            data = api_json(op, asset["browser_download_url"])
            return data if isinstance(data, dict) else {}
    return {}


def pick_openxc7_release(
    op: urllib.request.OpenerDirector,
    releases: list[dict],
    tag: str | None,
    engine_sha: str,
) -> tuple[dict, dict]:
    if tag:
        for rel in releases:
            if rel["tag_name"] == tag:
                info = release_build_info(op, rel)
                return rel, info
        raise SystemExit(f"openXC7 release tag not found: {tag}")

    engine_prefix = engine_sha[:12]
    fallback: tuple[dict, dict] | None = None
    for rel in releases:
        if rel.get("draft"):
            continue
        info = release_build_info(op, rel)
        rev = str(info.get("nextpnr-xilinx-revision") or "")
        if any(rev.startswith(p) for p in ARCHIVED_NEXTPNR_XILINX_PREFIXES):
            print(f"skip {rel['tag_name']}: archived nextpnr-xilinx {rev[:12]}")
            continue
        if not fallback:
            fallback = (rel, info)
        if rev.startswith(engine_prefix) or engine_sha.startswith(rev[:12] or "never"):
            return rel, info
    if fallback:
        rel, info = fallback
        print(
            f"warning: no package pinned to openXC7/nextpnr {engine_prefix}; "
            f"using {rel['tag_name']} ({(info.get('nextpnr-xilinx-revision') or '?')[:12]})"
        )
        return rel, info
    raise SystemExit("no openXC7 toolchain tarball found")


def find_asset(release: dict, *needles: str) -> dict:
    assets = release.get("assets") or []
    for needle in needles:
        for asset in assets:
            name = asset["name"]
            if needle in name and not name.endswith(".snap"):
                return asset
    names = ", ".join(a["name"] for a in assets) or "(none)"
    raise SystemExit(f"no matching asset in {release.get('tag_name')}: {names}")


def download(
    op: urllib.request.OpenerDirector, url: str, dest: Path, expected_sha: str | None
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading {url}")
    hasher = hashlib.sha256()
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        with op.open(url) as resp, tmp.open("wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                hasher.update(chunk)
                done += len(chunk)
                if total:
                    pct = 100.0 * done / total
                    print(f"\r  {done / 1e6:.1f}/{total / 1e6:.1f} MB ({pct:.0f}%)", end="")
                else:
                    print(f"\r  {done / 1e6:.1f} MB", end="")
        print()
        digest = hasher.hexdigest()
        if expected_sha and digest != expected_sha.lower():
            tmp.unlink(missing_ok=True)
            raise SystemExit(f"sha256 mismatch for {dest.name}: {digest} != {expected_sha}")
        tmp.replace(dest)
    except urllib.error.HTTPError as exc:
        tmp.unlink(missing_ok=True)
        raise SystemExit(f"download failed ({exc.code}): {url}") from exc


def parse_sha256sums(text: str) -> dict[str, str]:
    sums: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, _, name = line.partition(" ")
        name = name.lstrip(" *")
        if digest and name:
            sums[Path(name).name] = digest.lower()
    return sums


def extract_tarball(archive: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    print(f"extracting {archive.name} -> {dest}")
    with tarfile.open(archive, "r:*") as tar:
        try:
            tar.extractall(dest, filter="data")
        except TypeError:
            tar.extractall(dest)
    # OSS CAD Suite unpacks as dest/oss-cad-suite/{bin,...}
    nested = dest / "oss-cad-suite"
    if nested.is_dir() and not (dest / "bin").exists():
        for child in nested.iterdir():
            shutil.move(str(child), dest / child.name)
        nested.rmdir()


def install_himbaechel_name(prefix: Path) -> None:
    """Expose the engine under its current name; the tarball still says nextpnr-xilinx."""
    src = prefix / "bin" / "nextpnr-xilinx"
    dst = prefix / "bin" / "nextpnr-himbaechel"
    if not src.is_file():
        raise SystemExit(f"missing {src}")
    shutil.copy2(src, dst)
    print(f"installed {dst.name} -> same himbaechel engine as {src.name}")


def write_env_sh(openxc7: Path, oss: Path) -> None:
    path = TOOLS_DIR / "env.sh"
    path.write_text(
        "#!/bin/sh\n"
        "# Generated by download_toolchain.py — source this file.\n"
        'if [ -n "${BASH_SOURCE:-}" ]; then\n'
        '  ROOT="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"\n'
        "else\n"
        '  ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"\n'
        "fi\n"
        f'export PATH="$ROOT/{openxc7.name}/bin:$ROOT/{oss.name}/bin:$PATH"\n'
        f'if [ -f "$ROOT/{oss.name}/environment" ]; then\n'
        f'  # keep openXC7 ahead of oss-cad-suite after their env script\n'
        f'  _OPENXC7="$ROOT/{openxc7.name}/bin"\n'
        f'  . "$ROOT/{oss.name}/environment"\n'
        '  export PATH="$_OPENXC7:$PATH"\n'
        "  unset _OPENXC7\n"
        "fi\n"
        'echo "yosys:              $(command -v yosys 2>/dev/null || echo missing)"\n'
        'echo "nextpnr-himbaechel: $(command -v nextpnr-himbaechel 2>/dev/null || echo missing)"\n'
        'echo "openFPGALoader:     $(command -v openFPGALoader 2>/dev/null || echo missing)"\n'
    )
    path.chmod(0o755)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download openXC7/nextpnr (himbaechel) + OSS CAD Suite into tools/"
    )
    parser.add_argument(
        "--tag",
        help="openXC7 release tag (default: package that matches openXC7/nextpnr HEAD)",
    )
    parser.add_argument(
        "--skip-oss-cad-suite",
        action="store_true",
        help="only download openXC7 (no Yosys tarball)",
    )
    parser.add_argument(
        "--keep-archives",
        action="store_true",
        help="keep the downloaded .tgz files in tools/downloads/",
    )
    args = parser.parse_args()

    xc7_plat, oss_plat = host_platforms()
    op = opener()
    downloads = TOOLS_DIR / "downloads"
    downloads.mkdir(exist_ok=True)

    print("querying openXC7/nextpnr HEAD")
    engine_sha = github_head_sha(op)
    print(f"openXC7/nextpnr HEAD: {engine_sha[:12]}  (archived nextpnr-xilinx 0.9.8 is not used)")

    print("querying cavearr/toolchain-openxc7-releases")
    releases = api_json(op, OPENXC7_API + "?per_page=20")
    if not isinstance(releases, list):
        raise SystemExit("unexpected GitHub API payload for openXC7 releases")
    rel, info_preview = pick_openxc7_release(op, releases, args.tag, engine_sha)
    tag = rel["tag_name"]
    print(
        f"openXC7 package: {tag}  engine "
        f"{(info_preview.get('nextpnr-xilinx-revision') or '?')[:12]}"
    )

    sums_asset = find_asset(rel, "SHA256SUMS")
    tarball_asset = find_asset(rel, f"openxc7-toolchain-{xc7_plat}-")
    sums_path = downloads / "SHA256SUMS"
    download(op, sums_asset["browser_download_url"], sums_path, None)
    sums = parse_sha256sums(sums_path.read_text())

    tgz = downloads / tarball_asset["name"]
    download(
        op,
        tarball_asset["browser_download_url"],
        tgz,
        sums.get(tarball_asset["name"]),
    )
    extract_tarball(tgz, TOOLS_DIR / "openxc7")
    install_himbaechel_name(TOOLS_DIR / "openxc7")

    yosys_tag = None
    info_path = TOOLS_DIR / "openxc7" / "BUILD-INFO.json"
    if not info_path.is_file():
        nested = list((TOOLS_DIR / "openxc7").rglob("BUILD-INFO.json"))
        info_path = nested[0] if nested else info_path
    if info_path.is_file():
        info = json.loads(info_path.read_text())
        yosys_tag = info.get("yosys-release-tag")
        print(
            "openXC7 BUILD-INFO: "
            f"nextpnr={info.get('nextpnr-xilinx-revision', '?')[:12]} "
            f"yosys-release-tag={yosys_tag}"
        )

    if not args.skip_oss_cad_suite:
        if not yosys_tag:
            raise SystemExit("BUILD-INFO.json has no yosys-release-tag")
        print(f"querying YosysHQ/oss-cad-suite-build tag {yosys_tag}")
        oss_rel = api_json(op, OSS_CAD_API.format(tag=yosys_tag))
        if not isinstance(oss_rel, dict):
            raise SystemExit("unexpected GitHub API payload for OSS CAD Suite")
        oss_asset = find_asset(
            oss_rel,
            f"oss-cad-suite-{oss_plat}-{yosys_tag.replace('-', '')}.tgz",
            f"oss-cad-suite-{oss_plat}-",
        )
        oss_tgz = downloads / oss_asset["name"]
        download(op, oss_asset["browser_download_url"], oss_tgz, None)
        extract_tarball(oss_tgz, TOOLS_DIR / "oss-cad-suite")

    write_env_sh(TOOLS_DIR / "openxc7", TOOLS_DIR / "oss-cad-suite")

    if not args.keep_archives:
        shutil.rmtree(downloads, ignore_errors=True)

    print()
    print("done. activate with:")
    print(f"  source {TOOLS_DIR / 'env.sh'}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
