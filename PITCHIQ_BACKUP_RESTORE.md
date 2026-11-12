# PITCH IQ — Portable Backup and Future Ownership

## Purpose

PITCH IQ must always have an owner-controlled, portable backup independent of the live GitHub Pages website. This backup is for personal safekeeping, disaster recovery, future development handover, and possible company-level due diligence if the project is commercialised later. It does **not** mean the project is being sold now.

## What the backup contains

The automated archive packages the tracked project files from the current `main` commit, including the website, visual assets, Python services and model code, tests, GitHub Actions workflows, fixture and prediction snapshots, international data, odds snapshots, and project documentation.

The archive includes a `BACKUP_INFO.txt` file listing its source commit and included files. A SHA-256 checksum is supplied separately so the downloaded archive can be checked for corruption.

## What it deliberately excludes

- GitHub Actions secrets and environment variables.
- Local `.env` files and common private credential/key files.
- Git's internal `.git` directory and full commit history.

The GitHub repository remains the authoritative source for commit history. To preserve that history on a computer, use:

```bash
git clone https://github.com/Spencer-Pessy/pitchiq.git
```

Never commit secrets to the repository or store live API keys and bot tokens in an unsecured flash-drive archive.

## How to get the flash-drive copy

1. Open the repository on GitHub and select **Actions**.
2. Open the latest successful **Build PITCH IQ portable backup** run.
3. Under **Artifacts**, download **PITCHIQ-Portable-Backup**.
4. Extract the ZIP and copy the extracted folder to the flash drive.
5. Keep a second copy somewhere secure. Do not rely on one flash drive as the only backup.
6. Keep the accompanying `backup-sha256.txt` file and use it to verify the ZIP if needed.

The workflow creates a fresh archive on every push to `main`, once weekly, and when manually run. GitHub retains each workflow artifact for 90 days, so download important snapshots before they expire.

## Restoration and handover

1. Extract the archive into a working folder.
2. Install Python 3.12 or later.
3. Read `README.md` and the workflow files before running services.
4. Restore required credentials in GitHub repository **Settings → Secrets and variables → Actions**. Use the existing variable `ODDS_FREE_TIER_CONFIRMED=true` only if the connected odds provider's free-tier terms are still confirmed.
5. Run the offline test suite before deploying changes.
6. Reconnect GitHub Pages and scheduled workflows only after reviewing permissions, API limits, and destination IDs.

A future company handover should additionally include an inventory of third-party API terms, domains, hosting, accounts, ownership assignments, trademarks, licenses, and data-source rights. A code backup alone does not transfer those rights or accounts.

## Backup policy

- Create a backup after every change pushed to `main`.
- Create a weekly backup even if no code changes are made.
- Download milestone backups to at least two owner-controlled locations.
- Before any future sale or transfer, make a separate release snapshot, review all licenses and third-party terms, rotate credentials, and prepare an explicit asset/account transfer checklist.
