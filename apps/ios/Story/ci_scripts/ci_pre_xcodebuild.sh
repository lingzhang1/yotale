#!/bin/sh
# Xcode Cloud pre-build hook: stamp the build's git revision into Info.plist (GitCommitSHA) so a TestFlight /
# Xcode Cloud build reports its real commit in EditPlan build_provenance instead of "unknown".
#
# Why here: Info.plist carries `GitCommitSHA = $(GIT_COMMIT_SHA)` and the project pins GIT_COMMIT_SHA=unknown at
# target level (which an xcconfig cannot override). Writing the literal value into the CLOUD clone's Info.plist
# avoids any project.pbxproj change. It runs only inside Xcode Cloud (CI_COMMIT set) and never touches a local
# checkout. Local CLI builds can pass `GIT_COMMIT_SHA=$(git rev-parse --short=12 HEAD)` to xcodebuild instead.
# Never fails the build: with no commit available the value stays "unknown".
set -u
SHA="${CI_COMMIT:-}"
ROOT="${CI_PRIMARY_REPOSITORY_PATH:-}"
PLIST="${ROOT}/apps/ios/Story/Story/Info.plist"
if [ -z "$SHA" ] || [ -z "$ROOT" ] || [ ! -f "$PLIST" ]; then
  echo "ci_pre_xcodebuild: no CI_COMMIT / Info.plist — GitCommitSHA left as-is"
  exit 0
fi
SHORT=$(printf '%s' "$SHA" | cut -c1-12)
if /usr/libexec/PlistBuddy -c "Set :GitCommitSHA ${SHORT}" "$PLIST"; then
  echo "ci_pre_xcodebuild: GitCommitSHA=${SHORT}"
else
  echo "ci_pre_xcodebuild: could not stamp GitCommitSHA (left as-is)"
fi
exit 0
