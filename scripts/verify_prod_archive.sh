#!/usr/bin/env bash
# verify_prod_archive.sh — App Store production pre-upload safety gate (modeled on verify_beta_archive.sh).
#
# Inspects a BUILT app's embedded Info.plist and FAILS CLOSED unless it carries a fully-consistent PRODUCTION
# environment. This verifies the ARCHIVE ITSELF (baked metadata), not just source — the thing that actually
# ships. Run it against a Production-configured build product (an .app or Info.plist), e.g. as a post-archive /
# pre-upload check:
#
#   scripts/verify_prod_archive.sh /path/to/Story.app
#   scripts/verify_prod_archive.sh /path/to/Info.plist
#
# Exit 0 = the archive's baked environment is production and internally consistent (safe to upload).
# Exit non-zero = wrong label, missing values or a dev/beta identifier (DO NOT upload).
#
# Expected production identifiers (production account 854689494157, story-production-auth deployed 2026-11-25):
set -euo pipefail

EXPECT_ENV="production"
EXPECT_API="https://api.yotale.ai"
EXPECT_POOL="us-east-1_m9HoNhR7M"
EXPECT_CLIENT="4oesvialvc5i8g3cuv1b7vg3to"
EXPECT_DOMAIN="story-production-auth"
# Development and beta identifiers that must NEVER appear in a production archive:
TRIPWIRES="https://ydmju5wdps.us-east-1.awsapprunner.com https://api-dev.yotale.ai us-east-1_AzfHOEdA5 5rnvp7oq6d7crbt01ldpe89tkh https://asxtxgjiis.us-east-1.awsapprunner.com https://api-beta.yotale.ai us-east-1_3cPNfbrUl 4f3dtn9d0nk5uq1hcvbdc7m73c"

target="${1:-}"
[ -n "$target" ] || { echo "usage: $0 <Story.app | Info.plist>" >&2; exit 2; }

if [ -d "$target" ]; then
  PLIST="$target/Info.plist"
elif [ -f "$target" ]; then
  PLIST="$target"
else
  echo "FAIL: not found: $target" >&2; exit 2
fi
[ -f "$PLIST" ] || { echo "FAIL: no Info.plist at $PLIST" >&2; exit 2; }

read_key() {
  /usr/libexec/PlistBuddy -c "Print :$1" "$PLIST" 2>/dev/null || echo ""
}

ENV_VAL="$(read_key StoryBuildEnv)"
API="$(read_key StoryEnvApiBaseURL)"
REGION="$(read_key StoryEnvCognitoRegion)"
POOL="$(read_key StoryEnvUserPoolId)"
CLIENT="$(read_key StoryEnvAppClientId)"
DOMAIN="$(read_key StoryEnvDomainPrefix)"
REDIRECT="$(read_key StoryEnvRedirectURI)"

fail() { echo "FAIL: $1" >&2; exit 1; }

# 1) Must be LABELLED production.
[ "$ENV_VAL" = "$EXPECT_ENV" ] || fail "StoryBuildEnv='$ENV_VAL' (expected '$EXPECT_ENV'). A production archive must be labelled production."

# 2) No unresolved build tokens / empties.
for kv in "StoryEnvApiBaseURL=$API" "StoryEnvCognitoRegion=$REGION" "StoryEnvUserPoolId=$POOL" \
          "StoryEnvAppClientId=$CLIENT" "StoryEnvDomainPrefix=$DOMAIN" "StoryEnvRedirectURI=$REDIRECT"; do
  v="${kv#*=}"
  [ -n "$v" ] || fail "missing baked value: ${kv%%=*}"
  case "$v" in '$('*) fail "unresolved build token in ${kv%%=*}: $v";; esac
done

# 3) Must MATCH the expected production identifiers.
[ "$API" = "$EXPECT_API" ]       || fail "StoryEnvApiBaseURL='$API' != production '$EXPECT_API'"
[ "$POOL" = "$EXPECT_POOL" ]     || fail "StoryEnvUserPoolId='$POOL' != production '$EXPECT_POOL'"
[ "$CLIENT" = "$EXPECT_CLIENT" ] || fail "StoryEnvAppClientId='$CLIENT' != production '$EXPECT_CLIENT'"
[ "$DOMAIN" = "$EXPECT_DOMAIN" ] || fail "StoryEnvDomainPrefix='$DOMAIN' != production '$EXPECT_DOMAIN'"

# 4) Dev and beta tripwires must be ABSENT (catches a mixed build).
for devv in $TRIPWIRES; do
  for got in "$API" "$POOL" "$CLIENT"; do
    [ "$got" = "$devv" ] && fail "non-production identifier leaked into production archive: $devv"
  done
done

echo "OK: production archive verified — env=$ENV_VAL api=$API pool=$POOL client=$CLIENT domain=$DOMAIN redirect=$REDIRECT"
echo "    (no development or beta identifiers present; no unresolved tokens)"
