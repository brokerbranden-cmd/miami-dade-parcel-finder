#!/bin/bash
# Rebuild the read-only /classic/ copy of the pre-simplification UI from tag v-classic-2026-10-12.
# It reuses the live ../data, ../vendor and ../icons (no data is duplicated) and does not register a service worker.
set -e
cd "$(dirname "$0")/.."
TAG=${1:-v-classic-2026-10-12}
rm -rf classic && mkdir classic
for f in index.html app.js styles.css saved.js lenders.js lenders-page.js teardown.js drive.js; do git show "$TAG:$f" > "classic/$f"; done
sed -i -E "s#([\"'\`(])(data|vendor|icons)/#\1../\2/#g" classic/*.js classic/index.html
sed -i -E "s#href=\"manifest.webmanifest\"#href=\"../manifest.webmanifest\"#" classic/index.html
sed -i "s#navigator.serviceWorker.register('sw.js')#Promise.resolve()#" classic/app.js
sed -i 's#<body>#<body><div style="background:\#1f1f1f;color:\#fff;font:13px system-ui;padding:6px 12px;text-align:center">Classic layout (saved '"$TAG"'). <a style="color:\#FC4C02" href="../">Back to the current version</a></div>#' classic/index.html
echo "classic/ rebuilt from $TAG"
