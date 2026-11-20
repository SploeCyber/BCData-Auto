#!/usr/bin/env bash
# Install the tools needed by update.py:
#   - apkdown   (Rust CLI, downloads APKs from APKPure)
#   - tbctk-cli (Rust CLI, extracts/decrypts Battle Cats game data)
#   - APKEditor.jar (merges split APKs into a single APK)
# Requires: cargo/rustc, git, curl, java (JRE 17+).
#
# NOTE: upstream tbctk has path deps pointing OUTSIDE the repo
# (tbctk-mod -> ../../bccsv and ../../../packages/mlua), so a plain
# `cargo install --git .../tbctk tbctk-cli` cannot work. We clone a pinned
# rev and substitute:
#   bccsv -> the public Codeberg git dep already used by the workspace
#   mlua  -> the crates.io release of the same version (has lua55 feature)
# Bump the pinned revs deliberately after re-verifying a build.
set -euo pipefail

APKDOWN_REV="32d32ebac89635f7d2c6c6b168c11dcfaefb1a21"
TBCTK_REV="c21e94c4e51243f50dade44d137cd644c7b57e6d"
MLUA_VERSION="0.12.0-rc.1"
APKEDITOR_VERSION="V1.4.9"
APKEDITOR_URL="https://github.com/REAndroid/APKEditor/releases/download/${APKEDITOR_VERSION}/APKEditor-${APKEDITOR_VERSION#V}.jar"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PATH="$HOME/.cargo/bin:$PATH"

if ! command -v cargo >/dev/null 2>&1; then
  echo "cargo not found; installing rustup..."
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable --profile minimal
  export PATH="$HOME/.cargo/bin:$PATH"
fi

# openssl-sys (via reqwest/native-tls) needs OpenSSL headers + pkg-config.
if command -v apt-get >/dev/null 2>&1 && ! pkg-config --exists openssl 2>/dev/null; then
  echo "Installing libssl-dev + pkg-config..."
  sudo apt-get update -qq
  sudo apt-get install -y -qq libssl-dev pkg-config
fi

if ! command -v apkdown >/dev/null 2>&1; then
  echo "Installing apkdown @ ${APKDOWN_REV:0:8}..."
  cargo install --git https://codeberg.org/fieryhenry/apkdown --rev "$APKDOWN_REV" --locked \
    || cargo install --git https://codeberg.org/fieryhenry/apkdown --rev "$APKDOWN_REV"
fi

if ! command -v tbctk-cli >/dev/null 2>&1; then
  echo "Installing tbctk-cli @ ${TBCTK_REV:0:8} (patched path deps)..."
  BUILD_DIR="$(mktemp -d "${TMPDIR:-/tmp}/tbctk-build-XXXXXX")"
  trap 'rm -rf "$BUILD_DIR"' EXIT
  git clone --quiet https://codeberg.org/fieryhenry/tbctk.git "$BUILD_DIR/tbctk"
  git -C "$BUILD_DIR/tbctk" checkout --quiet "$TBCTK_REV"
  MOD="$BUILD_DIR/tbctk/tbctk-mod/Cargo.toml"
  # Fail loudly if upstream layout changed (patch would silently no-op).
  grep -q 'bccsv = { path = "../../bccsv" }' "$MOD"
  grep -q 'mlua = { path = "../../../packages/mlua"' "$MOD"
  sed -i \
    -e 's|bccsv = { path = "../../bccsv" }|bccsv = { workspace = true }|' \
    -e "s|mlua = { path = \"../../../packages/mlua\", features = \[\"lua55\", \"serde\"\] }|mlua = { version = \"=$MLUA_VERSION\", features = [\"lua55\", \"serde\", \"vendored\"] }|" \
    "$MOD"
  cargo install --path "$BUILD_DIR/tbctk/tbctk-cli"
fi

mkdir -p lib
if [ ! -f lib/APKEditor.jar ]; then
  echo "Downloading APKEditor ${APKEDITOR_VERSION}..."
  curl -sSL -o lib/APKEditor.jar "$APKEDITOR_URL"
fi

echo "Tool versions:"
apkdown --version || true
tbctk-cli --version || true
java -jar lib/APKEditor.jar 2>&1 | head -2 || true
echo "setup_tools: OK"
