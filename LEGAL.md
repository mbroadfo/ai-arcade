# Legal and Content Policy

## Purpose

AI Arcade is software for research, experimentation, emulator integration, backup automation, and AI-agent development. It does not provide, distribute, bundle, or authorize the distribution of copyrighted game content.

## No game content in this repository

Do not commit or publish:

- arcade ROM sets
- console ROMs
- BIOS/firmware images
- CHD images
- disk, cassette, cartridge, or optical-media images
- proprietary game executables
- commercial game data files
- copyrighted artwork, soundtracks, manuals, or asset packs unless redistribution is clearly authorized
- save states or snapshots that embed substantial copyrighted game data

The repository may contain original source code, public technical documentation references, hashes/checksums, independently created metadata, configuration templates, and synthetic test data.

## User responsibility

Users are responsible for determining whether they have the legal right to possess, copy, back up, emulate, or otherwise use any game content in their jurisdiction. Ownership of physical media does not automatically resolve every copyright question, and applicable law can vary.

Nothing in this project is legal advice.

## Private backups

The included backup tooling is designed to copy files from storage controlled by the user to a private S3 bucket controlled by the same user. The tools do not make those files public and do not upload them to GitHub.

A private backup does not itself establish that a user has the legal right to possess or copy the underlying content. Users remain responsible for the source material they choose to back up.

## Emulator projects

MAME, RetroArch, FBNeo, EmulationStation, console emulators, and other third-party projects have their own licenses and policies. AI Arcade is not affiliated with or endorsed by those projects unless explicitly stated.

## Trademarks

Game titles, platform names, emulator names, publisher names, and trademarks belong to their respective owners. Their use in documentation is descriptive and does not imply endorsement.

## Clean-repository rule

The public repository should be reproducible without requiring copyrighted game files. Tests should use synthetic fixtures or user-supplied local content outside the repository.

The CI workflow includes a repository-hygiene check intended to catch common ROM/BIOS/archive formats before they are accidentally published. This is a safety aid, not a guarantee.
