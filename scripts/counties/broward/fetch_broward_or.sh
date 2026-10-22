#!/usr/bin/env bash
# Broward County Records, Taxes & Treasury free Official Records index FTP (published public login crpublic/crpublic,
# sftp://bcftp.broward.org/Official_Records_Download, last ~7-10 days only -> must run at least weekly, ideally daily).
# Saves the pipe-delimited DOC / NAME / LEGAL index files into $RAW/broward/official_records/ (accumulates; never deletes).
# Lis pendens = doc type LP; probate-related doc types listed on the RTT FTP info page. Broward only.
# NOTE: the shared box cannot reach port 22 (egress is HTTP(S) only) - run this from a machine with SFTP egress.
set -uo pipefail
RAW="${RAW:-/workspace/raw}"; D="$RAW/broward/official_records"; mkdir -p "$D"
U="sftp://bcftp.broward.org/Official_Records_Download/"
ls=$(curl -s -k --connect-timeout 30 --list-only -u crpublic:crpublic "$U") || { echo "cannot reach $U"; exit 1; }
n=0; for f in $(echo "$ls" | grep -E '\.txt$'); do [ -s "$D/$f" ] && continue
  curl -s -k --retry 4 --retry-delay 20 -u crpublic:crpublic -o "$D/$f" "$U$f" && n=$((n+1)); done
echo "broward OR: $n new files in $D"
