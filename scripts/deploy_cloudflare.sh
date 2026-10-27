#!/bin/bash
# Deploy one commit of this repo (default: origin/main) to the private site https://app.prop-hunters.com
# (Cloudflare Pages project "ph-parcel-finder", protected by Cloudflare Access: email one-time PIN, allow list in Zero Trust > Access > Applications > "Parcel Finder").
# Needs a logged-in wrangler (npx wrangler whoami) with Pages write. No secrets are read or written here.
# Usage: scripts/deploy_cloudflare.sh [git-ref]      (CF_PAGES_PROJECT overrides the project name)
set -euo pipefail
REF=${1:-origin/main}; PROJECT=${CF_PAGES_PROJECT:-ph-parcel-finder}
ROOT=$(git rev-parse --show-toplevel); SHA=$(git -C "$ROOT" rev-parse "$REF^{commit}")
MSG=$(git -C "$ROOT" log -1 --format=%s "$SHA" | cut -c1-200)
WORK=$(mktemp -d /tmp/pf-cf-deploy.XXXXXX); trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/site" "$WORK/node_modules"          # node_modules: wrangler writes its cache next to the working dir
git -C "$ROOT" archive "$SHA" | tar -x -C "$WORK/site"
cd "$WORK/site"
# only the web app is published: no tests, screenshots, build scripts, Worker source or notes
rm -rf shots tests test_runs scripts worker logs docs drafts raw out .github .gitignore
find . -maxdepth 1 -name '*.md' -delete
# a top-level 404.html turns off Pages' single-page-app fallback (unknown paths return 404, not index.html)
printf '<!doctype html><meta charset="utf-8"><title>Not found</title><p>Not found. <a href="/">Open Parcel Finder</a></p>\n' > 404.html
cat > _headers <<'H'
/*
  X-Robots-Tag: noindex, nofollow
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
/sw.js
  Cache-Control: no-cache
/manifest.webmanifest
  Cache-Control: no-cache
H
echo "deploying $SHA ($(find . -type f | wc -l) files, $(du -sh . | cut -f1)) to Pages project $PROJECT"
cd "$WORK"
npx wrangler pages deploy site --project-name "$PROJECT" --branch main --commit-hash "$SHA" --commit-message "$MSG" --commit-dirty=true
