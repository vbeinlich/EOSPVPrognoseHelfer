#!/bin/bash
# Read-only host preflight; NEVER starts containers, opens ports or changes files.
set -euo pipefail
[ "$#" -eq 1 ] || { printf '%s\n' 'Usage: unraid-dashboard-preflight.sh PRIVATE_UNRAID_IPV4' >&2; exit 2; }
lan=$1
[[ "$lan" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || exit 2
IFS=. read -r a b c d <<< "$lan"
for octet in "$a" "$b" "$c" "$d"; do
  [[ "$octet" == 0 || "$octet" != 0* ]] && [ "$octet" -le 255 ] || exit 2
done
{ [ "$a" -eq 10 ] || { [ "$a" -eq 192 ] && [ "$b" -eq 168 ]; } ||
  { [ "$a" -eq 172 ] && [ "$b" -ge 16 ] && [ "$b" -le 31 ]; }; } || exit 2
addresses=$(ip -o -4 addr show)
printf '%s\n' "$addresses" | awk '{print $4}' | cut -d/ -f1 | grep -Fxq -- "$lan" || {
  printf '%s\n' 'LAN address is not assigned to this host; BLOCKED' >&2; exit 1;
}
# Conservatively reject ANY TCP listener on 8505, including other addresses/IPv6.
listeners=$(ss -H -ltn)
if printf '%s\n' "$listeners" | awk '{print $4}' | grep -Eq ':8505$'; then
  printf '%s\n' 'Port 8505 already has a TCP listener; BLOCKED' >&2; exit 1
fi
docker() { command docker --host unix:///var/run/docker.sock "$@"; }
ids=$(docker ps --quiet --no-trunc)
while IFS= read -r id; do
  [ -n "$id" ] || continue
  [[ "$id" =~ ^[0-9a-f]{12,64}$ ]] || exit 1
  ports=$(docker inspect --format '{{range .HostConfig.PortBindings}}{{range .}}{{println .HostPort}}{{end}}{{end}}' "$id")
  if printf '%s\n' "$ports" | grep -Fxq 8505; then
    printf '%s\n' 'Docker already reserves host port 8505; BLOCKED' >&2; exit 1
  fi
done <<< "$ids"
printf '%s\n' "PASS: $lan exists; no current TCP or Docker port 8505 conflict. Recheck immediately before activation."
