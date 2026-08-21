#!/usr/bin/env bash
# Report the size of a compote3 image and of the binary inside it.
#
# The runtime image is FROM scratch, so the two numbers should stay within a
# few kilobytes of each other. A gap means something beyond the binary and its
# default config found its way into the image.
#
# Usage: scripts/report_compote_size.sh <image-ref> [binary-path-in-image]

set -euo pipefail

image="${1:?usage: report_compote_size.sh <image-ref> [binary-path-in-image]}"
binary_path="${2:-/usr/local/bin/compote3}"

image_bytes=$(docker image inspect --format '{{.Size}}' "$image")

# `scratch` has no shell, so read the binary out of a created — never started —
# container rather than trying to run anything inside it.
container=$(docker create "$image")
workdir=$(mktemp -d)
cleanup() {
  docker rm -f "$container" >/dev/null 2>&1 || true
  rm -rf "$workdir"
}
trap cleanup EXIT

docker cp "$container:$binary_path" "$workdir/binary"
binary_bytes=$(stat -c %s "$workdir/binary")

human() {
  numfmt --to=iec --suffix=B --format='%.1f' "$1"
}

printf 'image  %s bytes (%s)\n' "$image_bytes" "$(human "$image_bytes")"
printf 'binary %s bytes (%s)\n' "$binary_bytes" "$(human "$binary_bytes")"

if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  {
    printf '### compote3 size\n\n'
    printf '`%s`\n\n' "$image"
    printf '| Artifact | Bytes | Size |\n'
    printf '| --- | ---: | ---: |\n'
    printf '| Binary (musl, stripped) | %s | %s |\n' "$binary_bytes" "$(human "$binary_bytes")"
    printf '| Image (uncompressed) | %s | %s |\n' "$image_bytes" "$(human "$image_bytes")"
  } >>"$GITHUB_STEP_SUMMARY"
fi

printf '::notice title=compote3 size::binary %s, image %s\n' \
  "$(human "$binary_bytes")" "$(human "$image_bytes")"
