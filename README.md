# AI Arcade

AI Arcade is an experimental framework for layered AI agents that can observe, reason about, and play classic games through emulators. The project is designed around a strict separation between **open-source software** and **privately owned game content**.

## Repository boundary

This repository is intended to contain only software, infrastructure definitions, documentation, tests, hashes/metadata, and synthetic fixtures created for AI Arcade.

It must **not** contain ROMs, BIOS images, CHDs, disk/tape images, game executables, save states containing copyrighted game data, or other copyrighted game assets.

Your own game library should remain outside the repository. A typical deployment is:

- Raspberry Pi 5 + flash drive: working EmulationStation/emulator library
- Windows PC: backup orchestrator
- Private Amazon S3 bucket: encrypted backup/archive
- GitHub: source code only

See [LEGAL.md](LEGAL.md) and [docs/BACKUP.md](docs/BACKUP.md).

## Backup architecture

The initial backup path is deliberately simple and safe:

1. The Windows PC connects to the Raspberry Pi over SSH/SFTP.
2. It inventories the configured library root on the Pi.
3. New or changed files are streamed through the Windows process to S3.
4. A SHA-256 manifest is written to S3 and locally.
5. The backup tool never deletes S3 objects unless a future explicit delete feature is enabled.

The ROMs never pass through GitHub.

## Quick start

### 1. Prerequisites

On Windows install:

- Python 3.11+
- AWS CLI v2
- OpenSSH client (Windows optional feature is fine)
- An AWS account/profile with permission to create the backup stack

Configure AWS credentials with your preferred AWS CLI profile.

### 2. Create the private S3 bucket

From PowerShell:

```powershell
./scripts/bootstrap_s3.ps1 -StackName ai-arcade-backup -Region us-west-2
```

The script deploys the CloudFormation stack in `infra/cloudformation/backup-bucket.yaml` and prints the bucket name.

The bucket is configured with:

- S3 Block Public Access enabled
- bucket-owner-enforced object ownership
- versioning enabled
- default server-side encryption (AES-256)
- TLS-only bucket policy
- incomplete multipart upload cleanup

### 3. Install Python dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### 4. Create your private config

```powershell
Copy-Item config\example.yaml config\local.yaml
```

Edit `config/local.yaml` with:

- Pi hostname/IP
- Pi username
- SSH private-key path
- remote game-library root
- S3 bucket name
- AWS profile and region

`config/local.yaml` is ignored by Git.

### 5. Test without changing anything

```powershell
python scripts\backup_pi_to_s3.py --config config\local.yaml --dry-run
```

### 6. Run the backup

```powershell
python scripts\backup_pi_to_s3.py --config config\local.yaml
```

### 7. Verify the archive

```powershell
python scripts\backup_pi_to_s3.py --config config\local.yaml --verify
```

## Safety principles

- No destructive remote deletion in the initial implementation.
- No AWS or SSH credentials in source control.
- No game content inside the repository.
- Exact ROM revisions may be identified by hashes without distributing ROM bytes.
- S3 is a backup/archive target, not the live EmulationStation filesystem.

## Repository layout

```text
.github/workflows/       CI and repository-hygiene checks
config/                  Example configuration only
docs/                    Design and operating documentation
infra/cloudformation/    Private S3 bucket infrastructure
scripts/                 Backup, inventory, and safety tools
tests/                   Unit tests
LEGAL.md                 Project legal/content policy
```

## Planned AI Arcade work

The first game adapter is expected to focus on Pac-Man, using a layered architecture:

- emulator adapter
- authoritative game-state adapter
- situation/risk interpretation
- fast constrained tactical controller
- slower strategic LLM supervisor
- observability and decision lineage

The backup tooling in this repository is intentionally independent of that intelligence framework.

## License

The AI Arcade source code can be licensed separately from any third-party emulator or game content. No license granted by this repository applies to ROMs, BIOSes, game assets, or other third-party copyrighted works.
