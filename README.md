# BCData-Auto

Self-updating collection of game data for **The Battle Cats** (en / jp / kr / tw),
usable with [BCSFE-Python](https://codeberg.org/fieryhenry/BCSFE-Python).

Unlike a static mirror, this repo updates **itself**: a scheduled GitHub
Actions workflow checks APKPure for new game versions every day, and when a
new version appears it downloads the APK, decrypts the game data, commits it,
and publishes a release with the compressed archives — fully automatically.

## How it works

Pipeline (per region, only when a new version is detected):

1. [`apkdown`](https://codeberg.org/fieryhenry/apkdown) — get latest version + download the APK from APKPure
2. [APKEditor](https://github.com/REAndroid/APKEditor) — merge split APKs into one APK
3. [`tbctk-cli`](https://codeberg.org/fieryhenry/tbctk) — extract/decrypt `DataLocal` + `resLocal` packs into `game_data/<cc>/<version>/`
4. `tar.xz` — compress into `<cc>-<version>.tar.xz`
5. commit + tag `v<version>-<regions>` + GitHub release with the archives
6. update [`metadata.json`](metadata.json) (points at this repo's releases)

`metadata.json` starts at the latest version — old versions are not backfilled.

## Using with BCSFE

Set the game data URL in the BCSFE config to:

```
https://raw.githubusercontent.com/SploeCyber/BCData-Auto/main/metadata.json
```

The archives have the standard structure (`DataLocal/`, `resLocal/`, and
`resLocal_<lang>/` for en).

## Running manually

```sh
bash scripts/setup_tools.sh        # installs apkdown, tbctk-cli (cargo), APKEditor.jar, needs java
python3 update.py --dry-run        # show latest versions only
python3 update.py --regions en     # process only en
python3 update.py --skip-git       # build data locally without commit/tag/release
python3 update.py                  # full run (needs gh auth + git push access)
```

Trigger the cloud workflow: **Actions → Update game data → Run workflow**
(or `gh workflow run update.yml`).

## Layout

| Path | Purpose |
|---|---|
| `game_data/<cc>/<ver>/` | decrypted game data per region/version |
| `metadata.json` | version → release-asset map for BCSFE |
| `regions.json` | region → package name + packs config |
| `update.py` | the updater orchestrator |
| `scripts/setup_tools.sh` | tool installer (local + CI) |
| `.github/workflows/update.yml` | daily scheduled auto-update |

## Credits

- [fieryhenry](https://codeberg.org/fieryhenry) — apkdown, tbctk, and the original
  [BCData](https://git.battlecatsmodding.org/fieryhenry/BCData) pipeline this repo automates
- [REAndroid](https://github.com/REAndroid) — APKEditor
- Data is © PONOS Corporation; this repo is for modding/save-editing interoperability.
