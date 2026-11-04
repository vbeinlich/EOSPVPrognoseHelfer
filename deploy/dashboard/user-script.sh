#!/bin/bash
# TEMPLATE ONLY. Install/schedule in Unraid User Scripts only after approval.
# One serialized, bounded READ export; never calls replay_export or EOS HTTP.
set -euo pipefail
dashboard_root=/mnt/user/appdata/ems-dashboard-review
exec timeout 70s bash "$dashboard_root/tools/unraid-dashboard-publish.sh" \
  "$dashboard_root/tools" "$dashboard_root/private" "$dashboard_root/publish"
# Optional Stage B: append --replays /ABSOLUTE/PRIVATE/REVIEWED-SIDECAR.json
# only after independently checking its file hash and matching source hashes.
