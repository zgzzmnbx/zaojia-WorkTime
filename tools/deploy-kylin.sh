#!/bin/bash
# First installation only. Run as root after reviewing the target and archive hash.
set -euo pipefail
archive=${1:?deployment archive path required}
expected=${2:?SHA256 required}
echo "$expected  $archive" | sha256sum -c -
test "$(uname -m)" = aarch64
test ! -e /opt/expert-hours/current
test ! -e /etc/systemd/system/expert-hours.service
test ! -e /etc/systemd/system/expert-hours-proxy.service
test ! -e /var/lib/expert-hours/data
test -z "$(ss -H -ltn '( sport = :8791 or sport = :18791 )')"
ip -4 addr show | grep -q '10.54.9.47/24'
firewall-cmd --state
runtime=/opt/gongwen-agent/runtime/python-3.12.14
test -x "$runtime/bin/python3.12"
test -x /usr/local/lib/gongwen-agent/caddy
stamp=$(date +%Y%m%d-%H%M%S)
backup=/var/backups/expert-hours/$stamp-first-install
release=/opt/expert-hours/releases/0.7.0-kylin-$stamp
install -d -m 700 "$backup"
systemctl show gongwen-agent gongwen-caddy eqis eqis-proxy kylin-model-api -p Id -p MainPID -p ActiveState > "$backup/existing-services.before"
firewall-cmd --zone=public --list-all > "$backup/firewall.before"
firewall-cmd --permanent --zone=public --list-all > "$backup/firewall-permanent.before"
rule='rule family="ipv4" source address="10.54.9.0/24" destination address="10.54.9.47" port port="8791" protocol="tcp" accept'
firewall-cmd --zone=public --query-rich-rule="$rule" > "$backup/rule-runtime.before" || true
firewall-cmd --permanent --zone=public --query-rich-rule="$rule" > "$backup/rule-permanent.before" || true
getent passwd expert-hours >/dev/null || useradd --system --home-dir /var/lib/expert-hours --shell /sbin/nologin expert-hours
install -d -m 755 "$release" /opt/expert-hours/runtime /etc/expert-hours
install -d -o expert-hours -g expert-hours -m 750 /var/lib/expert-hours /var/lib/expert-hours/data
# Copy the base interpreter, never a venv with release-specific shebangs.
cp -a "$runtime/." /opt/expert-hours/runtime/
install -m 755 /usr/local/lib/gongwen-agent/caddy /opt/expert-hours/caddy
tar -xzf "$archive" -C "$release"
chmod -R go-w "$release" /opt/expert-hours/runtime
(cd "$release" && /opt/expert-hours/runtime/bin/python3.12 -B -m unittest discover -s tests -v) > "$backup/tests.log" 2>&1 || { cat "$backup/tests.log"; exit 1; }
ln -s "$release" /opt/expert-hours/current
cat > /etc/expert-hours/Caddyfile <<'EOF'
{
    admin off
    auto_https off
    persist_config off
}
http://10.54.9.47:8791 {
    bind 10.54.9.47
    @lan remote_ip 10.54.9.0/24
    handle @lan {
        reverse_proxy 127.0.0.1:18791
    }
    handle {
        respond "LAN access only" 403
    }
}
EOF
/opt/expert-hours/caddy validate --config /etc/expert-hours/Caddyfile --adapter caddyfile
cat > /etc/systemd/system/expert-hours.service <<'EOF'
[Unit]
Description=Expert hours review backend
After=network.target
[Service]
Type=simple
User=expert-hours
Group=expert-hours
WorkingDirectory=/opt/expert-hours/current
ExecStart=/opt/expert-hours/runtime/bin/python3.12 -B /opt/expert-hours/current/server.py --port 18791 --data-dir /var/lib/expert-hours/data
Restart=on-failure
RestartSec=3
UMask=0027
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/expert-hours
[Install]
WantedBy=multi-user.target
EOF
cat > /etc/systemd/system/expert-hours-proxy.service <<'EOF'
[Unit]
Description=Expert hours review LAN gateway
After=network-online.target expert-hours.service
Wants=network-online.target expert-hours.service
[Service]
Type=simple
User=expert-hours
Group=expert-hours
Environment=HOME=/var/lib/expert-hours
ExecStart=/opt/expert-hours/caddy run --config /etc/expert-hours/Caddyfile --adapter caddyfile
Restart=on-failure
RestartSec=3
UMask=0027
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/expert-hours
[Install]
WantedBy=multi-user.target
EOF
cat > "$backup/rollback.sh" <<'EOF'
#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
systemctl disable --now expert-hours-proxy.service expert-hours.service
rule='rule family="ipv4" source address="10.54.9.0/24" destination address="10.54.9.47" port port="8791" protocol="tcp" accept'
if ! grep -qx yes rule-runtime.before; then firewall-cmd --zone=public --query-rich-rule="$rule" >/dev/null && firewall-cmd --zone=public --remove-rich-rule="$rule" || true; fi
if ! grep -qx yes rule-permanent.before; then firewall-cmd --permanent --zone=public --query-rich-rule="$rule" >/dev/null && firewall-cmd --permanent --zone=public --remove-rich-rule="$rule" || true; fi
echo 'Services disabled; release, runtime, config and all data retained.'
EOF
chmod 700 "$backup/rollback.sh"
systemd-analyze verify /etc/systemd/system/expert-hours.service /etc/systemd/system/expert-hours-proxy.service
systemctl daemon-reload
systemctl enable --now expert-hours.service expert-hours-proxy.service
firewall-cmd --zone=public --add-rich-rule="$rule"
firewall-cmd --permanent --zone=public --add-rich-rule="$rule"
echo "RELEASE=$release"
echo "BACKUP=$backup"
systemctl is-active expert-hours.service expert-hours-proxy.service
