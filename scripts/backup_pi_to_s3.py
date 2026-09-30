#!/usr/bin/env python3
"""Safely back up a Raspberry Pi game library to a private S3 bucket.

Design goals:
- Source is read-only over SFTP.
- No S3 object deletion.
- Changed files are hashed with SHA-256 and streamed to S3.
- A versioned manifest is stored locally and in S3.
- Dry-run and verify modes are supported.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import sys
from typing import Iterable

import boto3
from botocore.exceptions import ClientError
import paramiko
import yaml

from backup_common import excluded, s3_key

CHUNK = 1024 * 1024


@dataclass(frozen=True)
class RemoteFile:
    path: str
    size: int
    mtime: int


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if cfg.get("backup", {}).get("delete_remote_objects"):
        raise ValueError("Destructive deletion is intentionally unsupported in this version.")
    return cfg


def connect_pi(pi: dict) -> tuple[paramiko.SSHClient, paramiko.SFTPClient]:
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


def walk_remote(sftp: paramiko.SFTPClient, root: PurePosixPath) -> Iterable[RemoteFile]:
    stack = [root]
    while stack:
        current = stack.pop()
        for entry in sftp.listdir_attr(str(current)):
            p = current / entry.filename
            if stat.S_ISDIR(entry.st_mode):
                stack.append(p)
            elif stat.S_ISREG(entry.st_mode):
                rel = p.relative_to(root).as_posix()
                yield RemoteFile(rel, int(entry.st_size), int(entry.st_mtime))


def hash_remote(sftp: paramiko.SFTPClient, absolute_path: PurePosixPath) -> str:
    h = hashlib.sha256()
    with sftp.open(str(absolute_path), "rb") as f:
        while True:
            chunk = f.read(CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def load_s3_manifest(s3, bucket: str, key: str) -> dict[str, dict]:
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
        doc = json.loads(response["Body"].read().decode("utf-8"))
        return {x["path"]: x for x in doc.get("files", [])}
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in {"NoSuchKey", "404"}:
            return {}
        raise


def upload_one(s3, bucket: str, key: str, sftp: paramiko.SFTPClient,
               absolute_path: PurePosixPath, sha256: str, remote: RemoteFile) -> None:
    with sftp.open(str(absolute_path), "rb") as f:
        s3.upload_fileobj(
            f,
            bucket,
            key,
            ExtraArgs={
                "ServerSideEncryption": "AES256",
                "Metadata": {
                    "sha256": sha256,
                    "source-mtime": str(remote.mtime),
                    "source-size": str(remote.size),
                },
            },
        )


def write_manifest(s3, bucket: str, key: str, local_dir: Path, doc: dict) -> Path:
    local_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    local_path = local_dir / f"manifest-{timestamp}.json"
    payload = json.dumps(doc, indent=2, sort_keys=True).encode("utf-8")
    local_path.write_bytes(payload)
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=payload,
        ContentType="application/json",
        ServerSideEncryption="AES256",
    )
    return local_path


def verify(s3, bucket: str, prefix: str, manifest: dict[str, dict]) -> int:
    problems = 0
    for rel, item in sorted(manifest.items()):
        key = s3_key(prefix, rel)
        try:
            head = s3.head_object(Bucket=bucket, Key=key)
        except ClientError as e:
            print(f"MISSING  {rel}: {e}")
            problems += 1
            continue
        if int(head.get("ContentLength", -1)) != int(item["size"]):
            print(f"SIZE     {rel}: S3={head.get('ContentLength')} manifest={item['size']}")
            problems += 1
        remote_hash = head.get("Metadata", {}).get("sha256")
        expected_hash = item.get("sha256")
        if expected_hash and remote_hash != expected_hash:
            print(f"HASHMETA {rel}: S3={remote_hash} manifest={expected_hash}")
            problems += 1
    if problems == 0:
        print(f"Verified {len(manifest)} S3 objects against manifest metadata.")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="Back up a Pi library to a private S3 bucket.")
    ap.add_argument("--config", default="config/local.yaml")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verify", action="store_true", help="Verify S3 objects against the latest manifest.")
    ap.add_argument("--full-hash", action="store_true", help="Hash all source files even when size/mtime are unchanged.")
    args = ap.parse_args()

    cfg = load_config(Path(args.config))
    pi = cfg["pi"]
    aws = cfg["aws"]
    bcfg = cfg.get("backup", {})

    session = boto3.Session(profile_name=aws.get("profile") or None, region_name=aws.get("region"))
    s3 = session.client("s3")
    bucket = aws["bucket"]
    prefix = aws.get("prefix", "")
    manifest_key = bcfg.get("s3_manifest_key", "_manifests/latest.json")
    local_manifest_dir = Path(bcfg.get("local_manifest_dir", ".manifests"))

    prior = load_s3_manifest(s3, bucket, manifest_key)

    if args.verify:
        if not prior:
            print("No S3 manifest found; nothing to verify.", file=sys.stderr)
            return 2
        return 1 if verify(s3, bucket, prefix, prior) else 0

    ssh, sftp = connect_pi(pi)
    root = PurePosixPath(pi["remote_root"])
    excludes = list(bcfg.get("exclude", []))

    uploaded = skipped = planned = failed = 0
    planned_bytes = 0
    manifest_items: list[dict] = []

    try:
        for remote in sorted(walk_remote(sftp, root), key=lambda x: x.path):
            if excluded(remote.path, excludes):
                continue

            previous = prior.get(remote.path)
            metadata_unchanged = (
                previous
                and int(previous.get("size", -1)) == remote.size
                and int(previous.get("mtime", -1)) == remote.mtime
                and previous.get("sha256")
            )

            sha256 = previous.get("sha256") if metadata_unchanged and not args.full_hash else None
            changed = not metadata_unchanged

            # IMPORTANT: dry-run is metadata-only.  Do not stream/hash remote files
            # merely to decide what would be uploaded.  This keeps a dry-run fast
            # even when the Pi contains large port assets or thousands of files.
            if args.dry_run:
                item = {
                    "path": remote.path,
                    "size": remote.size,
                    "mtime": remote.mtime,
                    "sha256": sha256,
                }
                manifest_items.append(item)

                if not changed:
                    skipped += 1
                    continue

                key = s3_key(prefix, remote.path)
                planned += 1
                planned_bytes += remote.size
                print(f"PLAN     {remote.path} -> s3://{bucket}/{key}")
                continue

            # Real backups hash changed/new files before upload.  --full-hash also
            # re-hashes metadata-unchanged files for a deeper integrity check.
            if args.full_hash or changed:
                try:
                    sha256 = hash_remote(sftp, root / remote.path)
                except Exception as exc:
                    print(f"ERROR hash {remote.path}: {exc}", file=sys.stderr)
                    failed += 1
                    continue

                # Metadata may have changed without content changing.
                if previous and previous.get("sha256") == sha256 and previous.get("size") == remote.size:
                    changed = False

            item = {
                "path": remote.path,
                "size": remote.size,
                "mtime": remote.mtime,
                "sha256": sha256,
            }
            manifest_items.append(item)

            if not changed:
                skipped += 1
                continue

            key = s3_key(prefix, remote.path)

            try:
                print(f"UPLOAD   {remote.path}")
                upload_one(s3, bucket, key, sftp, root / remote.path, sha256 or "", remote)
                uploaded += 1
            except Exception as exc:
                print(f"ERROR upload {remote.path}: {exc}", file=sys.stderr)
                failed += 1

        doc = {
            "format": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_host": pi["host"],
            "source_root": str(root),
            "bucket": bucket,
            "prefix": prefix,
            "files": manifest_items,
        }

        if args.dry_run:
            def human_bytes(n: int) -> str:
                value = float(n)
                for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
                    if value < 1024 or unit == "TiB":
                        return f"{value:.1f} {unit}"
                    value /= 1024
                return f"{n} B"

            print(
                f"\nDry run complete: {planned} upload(s) planned "
                f"({human_bytes(planned_bytes)}), {skipped} unchanged, {failed} error(s)."
            )
            print("Dry-run used metadata only; no remote file contents were hashed or uploaded.")
        elif failed == 0:
            local_path = write_manifest(s3, bucket, manifest_key, local_manifest_dir, doc)
            print(f"\nBackup complete: {uploaded} uploaded, {skipped} unchanged.")
            print(f"Manifest: {local_path} and s3://{bucket}/{manifest_key}")
        else:
            print(f"\nBackup finished with {failed} error(s). Manifest was NOT advanced.", file=sys.stderr)

        return 1 if failed else 0
    finally:
        sftp.close()
        ssh.close()


if __name__ == "__main__":
    raise SystemExit(main())
