# Pi-to-S3 Backup

## Data flow

```text
Raspberry Pi flash drive
        |
        | SSH/SFTP (read-only usage by the script)
        v
Windows backup process
        |
        | HTTPS / AWS SDK
        v
Private encrypted S3 bucket
```

No game-content bytes are sent to GitHub.

## Why the Windows PC orchestrates the backup

The Pi remains focused on EmulationStation/emulation. The Windows machine already has access to your AWS credentials and can act as the controlled bridge between the private Pi library and private S3 storage.

The backup script uses SFTP so a normal SSH account is sufficient. It does not require the Pi to run a GitHub runner or contain AWS credentials.

## SSH host-key safety

The scripts deliberately reject unknown SSH host keys. Before using them, connect to the Pi once from Windows using the normal `ssh` command and verify/accept the Pi's host key. This prevents the backup process from silently trusting an unexpected host.

## Incremental behavior

The latest S3 manifest stores relative path, file size, source modification time, and SHA-256.

Normal runs reuse the prior SHA-256 when size and modification time are unchanged. Changed files are hashed, then uploaded only if their content differs from the prior manifest.

`--full-hash` forces every source file to be re-read and hashed.

## Safety

The initial implementation intentionally has no S3 deletion operation. If a ROM or image disappears from the Pi, the existing S3 object remains in the archive.

S3 versioning provides another recovery layer for objects that are replaced.

The CloudFormation stack has `DeletionPolicy: Retain`, so deleting the stack does not automatically delete the bucket.

## Dry run

Always use this first:

```powershell
python scripts\backup_pi_to_s3.py --config config\local.yaml --dry-run
```

## Initial inventory

For a quick inventory without hashing every file:

```powershell
python scripts\inventory_pi.py --config config\local.yaml
```

For a full SHA-256 inventory:

```powershell
python scripts\inventory_pi.py --config config\local.yaml --hash
```

The generated `.manifests/` files are private operational data and are ignored by Git.

## Verification

`--verify` checks the objects referenced by the latest S3 manifest for presence, content length, and the SHA-256 metadata recorded at upload time.

This is a fast archive-integrity check. A future enhancement could optionally download and re-hash S3 objects for full end-to-end verification.

## Windows Task Scheduler

Once manual runs are stable, create a Task Scheduler job that activates the virtual environment and runs the backup script. Do not schedule automation until the first dry run, full run, and verify run have all completed successfully.
