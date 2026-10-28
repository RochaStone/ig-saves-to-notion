#!/bin/bash
# Security and IP check for a Rocha Coded free tool. Run before any commit or push: ./scripts/security-check.sh
# Exit 0 = safe to publish. Any failure blocks.
set -u
cd "$(dirname "$0")/.." || exit 1
PASS=0; FAIL=0
check() { if [ "$2" = "0" ]; then echo "✓ $1"; PASS=$((PASS+1)); else echo "✗ $1"; FAIL=$((FAIL+1)); fi; }
EXCL='--exclude-dir=node_modules --exclude-dir=.git --exclude-dir=.venv --exclude-dir=dist --exclude-dir=out --exclude-dir=state --exclude-dir=__pycache__ --exclude=security-check.sh'

# 1. Secrets (keys, tokens, JWTs, Stripe, Resend, Supabase service keys)
S=$(grep -rIE $EXCL -E "(sk_live_[A-Za-z0-9]{10,}|sk-[A-Za-z0-9]{20,}|re_[A-Za-z0-9]{20,}|AAAA[A-Za-z0-9]{20,}|eyJ[A-Za-z0-9_-]{30,}\.[A-Za-z0-9_-]{10,}|ghp_[A-Za-z0-9]{20,}|xox[bp]-[A-Za-z0-9-]{20,}|AKIA[A-Z0-9]{16})" . 2>/dev/null | grep -v "example" | wc -l | tr -d ' ')
check "No hardcoded keys or tokens" $([ "$S" -eq 0 ] && echo 0 || echo 1)

# 2. No env files tracked
E=$(git ls-files 2>/dev/null | grep -E "(^|/)\.env($|\.)" | grep -v example | wc -l | tr -d ' ')
check "No .env files tracked by git" $([ "$E" -eq 0 ] && echo 0 || echo 1)

# 3. No personal paths or private identifiers
P=$(grep -rIE $EXCL -E "/Users/[A-Za-z0-9._-]+/|/home/[A-Za-z0-9._-]+/|supabase\.co/|project_id|service_role" . 2>/dev/null | wc -l | tr -d ' ')
check "No home-directory paths or private project identifiers" $([ "$P" -eq 0 ] && echo 0 || echo 1)

# 4. IP terms that must never ship (moat)
I=$(grep -rIiE $EXCL -E "voice dna|voice-dna|brand playbook|brand alchemy method|frequency of thriving|brand-positioning\.md|niche kit|initiatrix|cfos|\bcoco\b" . 2>/dev/null | grep -vi "author of brand alchemy in the thriving era" | wc -l | tr -d ' ')
check "No moat IP terms" $([ "$I" -eq 0 ] && echo 0 || echo 1)

# 5. Private forbidden list (client names etc.), kept outside the repo and never committed
F=0
if [ -f "../_private/forbidden.txt" ]; then
  while IFS= read -r term; do
    [ -z "$term" ] && continue
    c=$(grep -rIil $EXCL -- "$term" . 2>/dev/null | wc -l | tr -d ' ')
    if [ "$c" -gt 0 ]; then echo "   forbidden term present: $term"; F=1; fi
  done < ../_private/forbidden.txt
fi
check "No forbidden names (private list)" $F

# 6. Empty catch blocks and console.log in source
C=$(grep -rIE $EXCL --include="*.js" --include="*.mjs" --include="*.cjs" --include="*.ts" -E "catch ?\([^)]*\) ?\{[[:space:]]*\}" . 2>/dev/null | wc -l | tr -d ' ')
check "No empty catch blocks" $([ "$C" -eq 0 ] && echo 0 || echo 1)
L=$(grep -rIE $EXCL --include="*.ts" --include="*.tsx" -E "console\.log\(" src app lib 2>/dev/null | wc -l | tr -d ' ')
check "No console.log in src/app/lib (ts)" $([ "$L" -eq 0 ] && echo 0 || echo 1)

# 7. No images of real people committed (allow svg/png generated art only if listed in docs/IMAGES.md)
IMG=0
for f in $(git ls-files 2>/dev/null | grep -iE "\.(jpe?g|heic|mov|mp4)$"); do
  grep -qF -- "$f" docs/IMAGES.md 2>/dev/null || { echo "   unlisted media: $f"; IMG=1; }
done
check "No photos or video tracked unless listed in docs/IMAGES.md (stand-in art only)" $IMG

# 8. Required files
R=0; for f in README.md LICENSE SKILL.md; do [ -f "$f" ] || { echo "   missing $f"; R=1; }; done
check "README, LICENSE and SKILL.md present" $R

echo "=== $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] && { echo "SAFE TO PUBLISH"; exit 0; } || { echo "BLOCKED"; exit 1; }
