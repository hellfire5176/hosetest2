# Fire Hose Manager (Upgraded Batch Build)

Mobile-first hose inventory and multi-hose batch test history application for a fire department. Hose records get unique scan tokens suitable for encoding in NFC tags and QR codes.

## Features
- Multi-line batch layouts for simultaneous pump-testing
- Built-in front-end NFPA 1962 5-minute pressure hold timer countdown
- Unique non-sequential secure scan tokens per line
- Live tracking states (`In Service`, `Failed`, `In Test Layout`)
- Auto initial admin provisioning setup hook
- SQLite persistent storage engine

## Setup & Deployment
Refer to original repository guides for details on setting up persistent folders (`/mnt/tank/apps/fire-hose-manager/data`), building the workflow via GitHub Actions into GHCR, and installing via the Custom App YAML option on TrueNAS SCALE.
