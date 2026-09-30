#!/usr/bin/env python3
"""Create a private inventory of files on the Pi library via SFTP."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import PurePosixPath, Path
import stat
from datetime import datetime, timezone

import paramiko
import yaml


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def connect(pi: dict) -> tuple[paramiko.SSHClient, paramiko.SFTPClient]:
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.connect(
        hostname=pi["host"],
        port=int(pi.get("port", 22)),
        username=pi["username"],
        key_filename=pi["ssh_key_path"],
        look_for_keys=True,
        allow_agent=True,
    )
    return client, client.open_sftp()


def walk(sftp: paramiko.SFTPClient, root: str):
    stack = [PurePosixPath(root)]
    while stack:
        current = stack.pop()
        for entry in sftp.listdir_attr(str(current)):
            p = current / entry.filename
            if stat.S_ISDIR(entry.st_mode):
                stack.append(p)
            elif stat.S_ISREG(entry.st_mode):
                yield p, entry


def sha256_remote(sftp: paramiko.SFTPClient, path: PurePosixPath) -> str:
    h = hashlib.sha256()
    with sftp.open(str(path), "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/local.yaml")
    ap.add_argument("--hash", action="store_true", help="Compute SHA-256 for every file (slower).")
    ap.add_argument("--output", default=".manifests/pi-inventory.json")
    args = ap.parse_args()

    cfg = load_config(Path(args.config))
    root = PurePosixPath(cfg["pi"]["remote_root"])
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    ssh, sftp = connect(cfg["pi"])
    try:
        files = []
        for remote, attr in walk(sftp, str(root)):
            rel = remote.relative_to(root).as_posix()
            item = {
                "path": rel,
                "size": attr.st_size,
                "mtime": int(attr.st_mtime),
            }
            if args.hash:
                item["sha256"] = sha256_remote(sftp, remote)
            files.append(item)
            print(rel)

        doc = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_host": cfg["pi"]["host"],
            "source_root": str(root),
            "files": sorted(files, key=lambda x: x["path"]),
        }
        out.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        print(f"\nWrote {len(files)} entries to {out}")
        return 0
    finally:
        sftp.close()
        ssh.close()


if __name__ == "__main__":
    raise SystemExit(main())
