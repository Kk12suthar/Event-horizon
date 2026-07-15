#!/usr/bin/env bash
set -Eeuo pipefail

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl jq docker.io docker-compose-v2 unattended-upgrades
systemctl enable --now docker

install -d -m 0750 /opt/eventhorizon
install -d -m 0750 /opt/eventhorizon/data
install -d -m 0700 /opt/eventhorizon/secrets

DATA_DEVICE=/dev/disk/by-id/google-eventhorizon-data
if [[ -e "$DATA_DEVICE" ]]; then
  if ! blkid "$DATA_DEVICE" >/dev/null 2>&1; then
    mkfs.ext4 -F "$DATA_DEVICE"
  fi
  UUID=$(blkid -s UUID -o value "$DATA_DEVICE")
  grep -q "$UUID" /etc/fstab || echo "UUID=$UUID /opt/eventhorizon/data ext4 defaults,nofail,discard 0 2" >> /etc/fstab
  mountpoint -q /opt/eventhorizon/data || mount /opt/eventhorizon/data
fi

if [[ ! -f /swapfile ]]; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
swapon -a

cat >/etc/sysctl.d/99-eventhorizon-streaming.conf <<'EOF'
net.ipv4.tcp_keepalive_time=60
net.ipv4.tcp_keepalive_intvl=20
net.ipv4.tcp_keepalive_probes=5
EOF
sysctl --system >/dev/null

install -d -m 0755 /etc/systemd/journald.conf.d
cat >/etc/systemd/journald.conf.d/eventhorizon.conf <<'EOF'
[Journal]
SystemMaxUse=512M
MaxRetentionSec=7day
EOF
systemctl restart systemd-journald

SAFETY_STOP_AT=$(curl -fsS -H 'Metadata-Flavor: Google' \
  http://metadata.google.internal/computeMetadata/v1/instance/attributes/eventhorizon-safety-stop-at || true)
if [[ -n "$SAFETY_STOP_AT" ]]; then
  cat >/etc/systemd/system/eventhorizon-safety-stop.service <<'EOF'
[Unit]
Description=Stop EventHorizon before trial expiry

[Service]
Type=oneshot
ExecStart=/sbin/shutdown -h now
EOF
  cat >/etc/systemd/system/eventhorizon-safety-stop.timer <<EOF
[Unit]
Description=Hard calendar safety stop for EventHorizon

[Timer]
OnCalendar=$SAFETY_STOP_AT
Persistent=true

[Install]
WantedBy=timers.target
EOF
  systemctl daemon-reload
  systemctl enable --now eventhorizon-safety-stop.timer
fi
