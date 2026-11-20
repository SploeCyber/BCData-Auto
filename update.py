#!/usr/bin/env python3
"""BCData-Auto updater.

Checks APKPure (via apkdown) for the latest Battle Cats version of each
region, and for every new version:
  1. downloads the (split) APK with apkdown
  2. merges it into a single APK with APKEditor
  3. extracts/decrypts game data with tbctk-cli into game_data/<cc>/<ver>/
  4. packs it into out/<cc>-<ver>.tar.xz
  5. commits game_data + metadata.json, tags, and creates a GitHub release
     with the tar.xz assets (via gh)

metadata.json starts at the latest version; old versions are never
backfilled. Regions whose latest version is already recorded are skipped,
so scheduled runs are cheap.

Usage:
  python3 update.py                     # all regions, full run
  python3 update.py --regions en        # only en
  python3 update.py --dry-run           # only report latest versions
  python3 update.py --skip-git          # build data locally, no commit/tag/release
  python3 update.py --force             # reprocess even if already in metadata
"""

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
REGIONS_FILE = ROOT / "regions.json"
METADATA_FILE = ROOT / "metadata.json"
APKS_DIR = ROOT / "apks"
OUT_DIR = ROOT / "out"
DATA_DIR = ROOT / "game_data"
APKEDITOR_JAR = ROOT / "lib" / "APKEditor.jar"

# tag region order matches upstream BCData convention (e.g. v15.6.1-en-kr-tw)
TAG_ORDER = ["en", "kr", "tw", "jp"]


def run(cmd, **kwargs):
    print("+ " + " ".join(str(c) for c in cmd), flush=True)
    return subprocess.run([str(c) for c in cmd], check=True, **kwargs)


def run_out(cmd):
    res = run(cmd, capture_output=True, text=True)
    return res.stdout.strip()


def git_remote_repo():
    """owner/name from git remote origin, or None."""
    try:
        url = run_out(["git", "-C", ROOT, "remote", "get-url", "origin"])
    except subprocess.CalledProcessError:
        return None
    url = url.removesuffix(".git")
    if "github.com" not in url:
        return None
    return url.split("github.com")[-1].lstrip(":/")


def load_metadata(repo):
    if METADATA_FILE.exists():
        meta = json.loads(METADATA_FILE.read_text())
    else:
        meta = {}
    meta.setdefault("versions", {})
    meta["base_url"] = f"https://github.com/{repo}/releases/download/"
    return meta


def save_metadata(meta):
    # keep region keys in TAG_ORDER, versions sorted oldest->newest
    ordered = {
        cc: dict(sorted(meta["versions"].get(cc, {}).items(),
                        key=lambda kv: [int(x) for x in kv[0].split(".")]))
        for cc in TAG_ORDER if cc in meta["versions"]
    }
    meta["versions"] = ordered
    METADATA_FILE.write_text(json.dumps(meta, indent=2) + "\n")


def latest_version(pkg):
    out = run_out(["apkdown", "get-latest", "-p", pkg])
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    if not lines:
        raise RuntimeError(f"apkdown get-latest returned nothing for {pkg}")
    return lines[-1]


def release_exists(tag):
    res = subprocess.run(["gh", "release", "view", tag],
                         capture_output=True, text=True)
    return res.returncode == 0


def download_apk(pkg, ver):
    apk = APKS_DIR / pkg / f"{ver}.apk"
    apk.parent.mkdir(parents=True, exist_ok=True)
    run(["apkdown", "download", "--package-name", pkg, "--version", ver,
         "--output-path", apk, "--skip-if-exists"])
    if not apk.exists():
        raise RuntimeError(f"download produced no file: {apk}")
    return apk


def merge_apk(pkg, ver, apk):
    merged = APKS_DIR / pkg / f"{ver}-merged.apk"
    if merged.exists():
        print(f"merge skipped, exists: {merged}")
        return merged
    run(["java", "-jar", APKEDITOR_JAR, "m", "-i", apk, "-o", merged,
         "-extractNativeLibs", "true", "-f"])
    if not merged.exists():
        raise RuntimeError(f"merge produced no file: {merged}")
    return merged


def extract_data(cc, ver, merged, packs):
    dest = DATA_DIR / cc / ver
    if dest.exists() and any(dest.iterdir()):
        print(f"extract skipped, exists: {dest}")
        return dest
    dest.mkdir(parents=True, exist_ok=True)
    cmd = ["tbctk-cli", "extract", "pkg", "-c", cc, "-g", ver,
           "-o", dest, "-p", merged, "-f", "--packs", *packs,
           "--ignore-no-exist"]
    run(cmd)
    if not any(dest.iterdir()):
        raise RuntimeError(f"extract produced no files in {dest}")
    return dest


def pack_tar(cc, ver, dest):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tar = OUT_DIR / f"{cc}-{ver}.tar.xz"
    if tar.exists():
        print(f"tar skipped, exists: {tar}")
        return tar
    run(["tar", "-I", "xz -9", "-cf", tar, "-C", dest, "."])
    return tar


def tag_for(ver, ccs):
    ordered = [c for c in TAG_ORDER if c in ccs]
    return "v" + ver + "-" + "-".join(ordered)


def git_commit_push(message):
    run(["git", "-C", ROOT, "add", "game_data", "metadata.json"])
    status = run_out(["git", "-C", ROOT, "status", "--porcelain"])
    if not status:
        print("nothing to commit")
        return False
    run(["git", "-C", ROOT, "commit", "-m", message])
    run(["git", "-C", ROOT, "push"])
    return True


def make_release(tag, assets, ver, ccs):
    if not release_exists(tag):
        run(["gh", "release", "create", tag, *assets,
             "--title", tag,
             "--notes", f"Battle Cats {ver} game data for: {', '.join(sorted(ccs))}.\n\n"
                        "Generated automatically by BCData-Auto "
                        "(apkdown + APKEditor + tbctk)."])
    else:
        run(["gh", "release", "upload", tag, *assets, "--clobber"])


def push_tag(tag):
    exists_local = subprocess.run(
        ["git", "-C", ROOT, "rev-parse", "-q", "--verify", f"refs/tags/{tag}"],
        capture_output=True).returncode == 0
    if not exists_local:
        run(["git", "-C", ROOT, "tag", tag])
    remote = run_out(["git", "-C", ROOT, "ls-remote", "--tags", "origin", tag])
    if not remote:
        run(["git", "-C", ROOT, "push", "origin", tag])


def verify_urls(meta, entries):
    for cc, ver, path in entries:
        url = meta["base_url"] + path
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=60) as resp:
            if resp.status != 200:
                raise RuntimeError(f"verify failed ({resp.status}): {url}")
        print(f"verified: {url}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--regions", default=",".join(TAG_ORDER))
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-git", action="store_true")
    args = ap.parse_args()

    regions = json.loads(REGIONS_FILE.read_text())
    wanted = [c.strip() for c in args.regions.split(",") if c.strip()]
    for c in wanted:
        if c not in regions:
            sys.exit(f"unknown region: {c}")

    repo = git_remote_repo()
    if not repo and not args.skip_git:
        sys.exit("cannot determine GitHub repo from git remote origin")
    repo = repo or "SploeCyber/BCData-Auto"

    meta = load_metadata(repo)

    # 1. find latest versions
    latest = {}
    for cc in wanted:
        latest[cc] = latest_version(regions[cc]["package_name"])
        known = meta["versions"].get(cc, {})
        state = "NEW" if latest[cc] not in known or args.force else "up to date"
        print(f"{cc}: latest={latest[cc]} ({state})")

    if args.dry_run:
        return

    todo = {cc: ver for cc, ver in latest.items()
            if ver not in meta["versions"].get(cc, {}) or args.force}
    if not todo:
        print("All regions up to date.")
        save_metadata(meta)  # normalizes base_url/order
        if not args.skip_git:
            git_commit_push("Update metadata.json")
        return

    if not APKEDITOR_JAR.exists():
        sys.exit("lib/APKEditor.jar missing; run scripts/setup_tools.sh first")

    # 2. build data + archives for each new version
    tars = {}  # (ver, cc) -> tar path
    for cc, ver in todo.items():
        r = regions[cc]
        apk = download_apk(r["package_name"], ver)
        merged = merge_apk(r["package_name"], ver, apk)
        dest = extract_data(cc, ver, merged, r["packs"])
        tars[(ver, cc)] = pack_tar(cc, ver, dest)

    # 3. group by version -> one tag/release per distinct version
    groups = {}
    for (ver, cc), tar in tars.items():
        groups.setdefault(ver, {})[cc] = tar

    new_entries = []
    for ver, ccs in groups.items():
        tag = tag_for(ver, ccs.keys())
        for cc in ccs:
            path = f"{tag}/{cc}-{ver}.tar.xz"
            meta["versions"].setdefault(cc, {})[ver] = path
            new_entries.append((cc, ver, path))

    save_metadata(meta)

    if args.skip_git:
        print("--skip-git: built archives, metadata updated locally:")
        for cc, ver, path in new_entries:
            print(f"  {cc} {ver} -> {path}")
        return

    # 4. commit data + metadata, then tag + release
    desc = ", ".join(f"{cc} {ver}" for cc, ver in sorted(todo.items()))
    git_commit_push(f"Add game data: {desc}")
    for ver, ccs in groups.items():
        tag = tag_for(ver, ccs.keys())
        push_tag(tag)
        make_release(tag, [str(t) for t in ccs.values()], ver, ccs.keys())

    # 5. verify the published URLs resolve
    verify_urls(meta, new_entries)
    print("Done.")


if __name__ == "__main__":
    main()
