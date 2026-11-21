#!/bin/sh
# LumaBrowser updater for a rooted TV (Homebrew Channel init.d; busybox sh, python3 for JSON).
#
#   tv-update.sh boot      init.d entry: detaches, checks 10 minutes after boot and then every 6 hours
#   tv-update.sh once      one check now
#
# Installs the latest nphil/LumaBrowser release when its version differs from the installed one, the browser is not
# running, and the download matches the sha256 GitHub records for the asset. Log: /tmp/lumabrowser-update.log.
ID=org.nphil.lumabrowser
API=https://api.github.com/repos/nphil/LumaBrowser/releases/latest
APP=/media/developer/apps/usr/palm/applications/$ID
LOG=/tmp/lumabrowser-update.log
IPK=/tmp/lumabrowser-update.ipk

log() { echo "$(date '+%F %T') $*" >> "$LOG"; }

running() {
	for c in /proc/[0-9]*; do [ "$c/exe" -ef "$APP/browser/chrome" ] && return 0; done
	return 1
}

check() {
	rel=$(curl -fsS --max-time 30 "$API") || { log "release check failed"; return 1; }
	set -- $(printf '%s' "$rel" | python3 -c '
import json, sys
r = json.load(sys.stdin)
a = [x for x in r["assets"] if x["name"].endswith("_arm.ipk")][0]
print(r["tag_name"][1:].split("-")[0], a["browser_download_url"], a["digest"].split(":", 1)[1])
') || { log "release has no IPK"; return 1; }
	want=$1 url=$2 sum=$3
	have=$(sed -n 's/.*"version": *"\([^"]*\)".*/\1/p' "$APP/appinfo.json" 2>/dev/null)
	[ "$have" = "$want" ] && return 0
	running && { log "$want available, browser open: later"; return 0; }
	curl -fsSL --max-time 900 -o "$IPK" "$url" || { log "download failed"; rm -f "$IPK"; return 1; }
	[ "$(sha256sum "$IPK" | cut -d' ' -f1)" = "$sum" ] || { log "sha256 mismatch, not installed"; rm -f "$IPK"; return 1; }
	out=$(luna-send -w 300000 -i luna://com.webos.appInstallService/dev/install \
		"{\"id\":\"$ID\",\"ipkUrl\":\"$IPK\",\"subscribe\":true}" 2>&1 | grep -m1 -E '"state": *"(installed|install failed)"|errorCode')
	rm -f "$IPK"
	log "${have:-none} -> $want: $out"
}

case "$1" in
boot)
	exec 9>/tmp/lumabrowser-update.lock
	flock -n 9 || exit 0
	( sleep 600; while :; do check; sleep 21600; done ) </dev/null >/dev/null 2>&1 &
	;;
once) check ;;
*) echo "usage: $0 boot|once" >&2; exit 2 ;;
esac
