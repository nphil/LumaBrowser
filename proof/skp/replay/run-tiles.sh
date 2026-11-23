#!/usr/bin/env bash
# 512x512 tile raster timing on one thread (wall and CLOCK_THREAD_CPUTIME_ID), cold pass then warm passes.
# Usage: run-tiles.sh   (env: LB_SKP_OUT = capture.py scratch directory, CARGO_TARGET_DIR or SKP_REPLAY)
# Run it with nothing else heavy on the host; /proc/loadavg is recorded in each result.
set -euo pipefail
OUT=${LB_SKP_OUT:?set LB_SKP_OUT to the directory capture.py wrote captures/ into}
R=${SKP_REPLAY:-$CARGO_TARGET_DIR/release/skp-replay}
mkdir -p "$OUT/results"
cd "$OUT/captures"
case_() { # name, then skp-replay tiles args
  local n=$1; shift
  "$R" tiles "$@" > "$OUT/results/tiles-$n.json"
}
case_ article-s1-isolated   article@1_y0   --scale 1 --height 4800 --passes 5
case_ article-s1-direct     article@1_y0   --scale 1 --height 4800 --passes 5 --direct
case_ article-s2-isolated   article@2_y0   --scale 2 --height 4800 --passes 4
case_ article-s2-direct     article@2_y0   --scale 2 --height 4800 --passes 4 --direct
case_ wikipedia-s1-isolated wikipedia@1_y0 --scale 1 --height 4800 --passes 5
case_ news-s1-isolated      news@1_y0      --scale 1 --height 4800 --passes 5
case_ mix-s1-isolated       mix@1_y0       --scale 1 --height 2200 --passes 9
python3 - "$OUT/results" <<'EOF'
import glob, json, os, sys
for f in sorted(glob.glob(os.path.join(sys.argv[1], "tiles-*.json"))):
    d = json.load(open(f)); c = d["passes"][0]; w = d["warm_pooled"]
    print(f'{os.path.basename(f)[6:-5]:22s} scale {d["scale"]:.0f} tiles/pass {c["tiles"]:3d} (ink>=3%: {c["tiles_with_ink_ge_3pct"]:3d}) ops {[l["ops"] for l in d["layers"]]} load {d["host_load_before"].split()[0]}')
    for label, wall, cpu in (("cold  ink", c["ink_wall_ms"], c["ink_thread_cpu_ms"]), ("warm  ink", w["ink_wall_ms"], w["ink_thread_cpu_ms"]), ("warm  all", w["wall_ms"], w["thread_cpu_ms"])):
        print(f'   {label} n={wall["n"]:4d} wall median {wall["median"]:7.3f} ms (p10 {wall["p10"]:.3f} p90 {wall["p90"]:.3f})  thread-cpu median {cpu["median"]:7.3f} ms')
EOF
