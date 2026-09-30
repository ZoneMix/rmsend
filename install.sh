#!/usr/bin/env bash
set -euo pipefail

# The executable resolves this symlink to find its library and bundled styles.
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
install_prefix="${RMSEND_PREFIX:-$HOME/.local}"
command_path="$install_prefix/bin/rmsend"

if ! command -v uv >/dev/null 2>&1; then
  echo "Install uv first: https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
fi
mkdir -p "$install_prefix/bin"
if [[ -e "$command_path" || -L "$command_path" ]]; then
  if [[ -L "$command_path" && "$(readlink "$command_path")" == "$project_dir/rmsend" ]]; then
    echo "Already installed: $command_path"
    exit 0
  fi
  echo "Refusing to replace $command_path. Choose another RMSEND_PREFIX or move the existing command." >&2
  exit 1
fi
ln -s "$project_dir/rmsend" "$command_path"
echo "Installed: $command_path"
echo "Keep this checkout in place and add $install_prefix/bin to your PATH."
