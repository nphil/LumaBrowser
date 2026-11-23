#!/usr/bin/env bash
# Replay every capture bundle with skp-replay and compare it with the Page.captureScreenshot taken with it.
# Usage: run-compare.sh [EXTRA skp-replay args, e.g. --skia-text]   (env: LB_SKP_OUT = capture.py scratch directory)
# Prints one JSON line per run to stdout.
set -euo pipefail
OUT=${LB_SKP_OUT:?set LB_SKP_OUT to the directory capture.py wrote captures/ into}
R=${SKP_REPLAY:-$CARGO_TARGET_DIR/release/skp-replay}
cd "$OUT/captures"
extra=("$@")
run() { # capture scale hints reference
  local cap=$1 scale=$2 hints=$3 ref=${4:-}
  "$R" compare "$cap" --scale "$scale" ${hints:+--hints} ${ref:+--reference "$ref"} "${extra[@]}"
}
for c in mix@1_y0 mix@1_y300 mix@1_y800 mix@1_y1400 mix@1_y1900; do run $c 1 "" ; run $c 1 hints; done
for c in article@1_y0 article@1_y10000 news@1_y0 wikipedia@1_y0 bbc@1_y0; do run $c 1 ""; done
# CSS-pixel captures replayed at 2x against the emulated-DSF-2 screenshots
for p in mix article news; do run $p@1_y0 2 "" "$PWD/$p@2_y0/screenshot.png"; done
run mix@1_y0 2 hints "$PWD/mix@2_y0/screenshot.png"
for c in mix@2_y0 article@2_y0 news@2_y0 article@n2_y0 mix@n2_y0; do run $c 2 ""; done
run mix@n2_y1400 2 ""; run mix@n2_y1400 2 hints
# native-2x pictures replayed at 1x against the DSF-1 screenshots
run mix@n2_y0 1 "" "$PWD/mix@1_y0/screenshot.png"
run article@n2_y0 1 "" "$PWD/article@1_y0/screenshot.png"
