#!/usr/bin/env bash
# Install the tools needed by update.py:
#   - apkdown   (Rust CLI, downloads APKs from APKPure)
#   - tbctk-cli (Rust CLI, extracts/decrypts Battle Cats game data)
#   - APKEditor.jar (merges split APKs; committed in lib/, download fallback)
# Requires: cargo/rustc, git, curl, java (JRE 17+).
#
# Tools are installed from GitHub forks so the pipeline does not depend on
# the original hosts staying online:
#   - SploeCyber/apkdown (fork of codeberg.org/fieryhenry/apkdown)
#   - SploeCyber/tbctk   (fork of codeberg.org/fieryhenry/tbctk; the
#     `build-fix` branch makes the workspace build standalone: bccsv comes
#     from the SploeCyber/bccsv fork, mlua from crates.io with vendored Lua)
# Bump the pinned revs deliberately after re-verifying a build.
set -euo pipefail

APKDOWN_REV="32d32ebac89635f7d2c6c6b168c11dcfaefb1a21"
TBCTK_REV="9b55dd7a12011900a7a73fb7f17e70c4ce589263" # SploeCyber/tbctk build-fix
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
  echo "Installing apkdown @ ${APKDOWN_REV:0:8} (GitHub fork)..."
  cargo install --git https://github.com/SploeCyber/apkdown --rev "$APKDOWN_REV" --locked \
    || cargo install --git https://github.com/SploeCyber/apkdown --rev "$APKDOWN_REV"
fi

if ! command -v tbctk-cli >/dev/null 2>&1; then
  echo "Installing tbctk-cli @ ${TBCTK_REV:0:8} (GitHub fork, build-fix)..."
  cargo install --git https://github.com/SploeCyber/tbctk --rev "$TBCTK_REV" tbctk-cli --locked
fi

# APKEditor.jar is committed in lib/; download only if it is missing.
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
