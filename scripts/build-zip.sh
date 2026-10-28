#!/bin/bash
# Builds dist/<name>.zip for Claude Cowork "Upload a skill", wrapped in a <name>/ folder. Excludes dev and private files at any depth.
set -eu
cd "$(dirname "$0")/.."
NAME=$(basename "$PWD")
STAGE=$(mktemp -d)
mkdir -p dist "$STAGE/$NAME"
rsync -a --include '.env.example' --exclude '.git' --exclude '.pre-commit-config.yaml' --exclude 'node_modules' --exclude '.venv' --exclude 'dist' --exclude 'out' --exclude 'state' --exclude 'dev' --exclude '__pycache__' --exclude '*.pyc' --exclude '.env*' --exclude '.DS_Store' --exclude 'tests/fixtures/large' ./ "$STAGE/$NAME/"
rm -f "dist/$NAME.zip"
(cd "$STAGE" && zip -qr "$OLDPWD/dist/$NAME.zip" "$NAME")
rm -rf "$STAGE"
echo "built dist/$NAME.zip ($(du -h "dist/$NAME.zip" | cut -f1))"
