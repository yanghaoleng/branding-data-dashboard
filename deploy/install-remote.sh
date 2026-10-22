#!/usr/bin/env bash
set -euo pipefail
release="$1"
staging="$2"
case "$release" in *[!a-zA-Z0-9-]*) echo 'invalid release'; exit 1;; esac
getent passwd branding-data >/dev/null || useradd --system --home /var/lib/branding-database --shell /usr/sbin/nologin branding-data
install -d -m 0755 /opt/branding-database/releases /var/www/branding-database/releases
install -d -o branding-data -g branding-data -m 0700 /var/lib/branding-database
install -d -m 0755 "/opt/branding-database/releases/$release" "/var/www/branding-database/releases/$release"
cp -a "$staging/server" "/opt/branding-database/releases/$release/"
cp -a "$staging/dist/." "/var/www/branding-database/releases/$release/"
chown -R root:root "/opt/branding-database/releases/$release" "/var/www/branding-database/releases/$release"
chmod -R a+rX "/opt/branding-database/releases/$release" "/var/www/branding-database/releases/$release"
if [ ! -f /etc/branding-database.env ]; then install -m 0600 "$staging/service.env" /etc/branding-database.env; fi
if [ -f /var/lib/branding-database/branding.sqlite ]; then
  python3 - "$release" <<'PY'
import sqlite3,sys
src=sqlite3.connect('/var/lib/branding-database/branding.sqlite')
dst=sqlite3.connect('/var/lib/branding-database/pre-release-'+sys.argv[1]+'.sqlite')
src.backup(dst);dst.close();src.close()
PY
fi
install -m 0644 "$staging/deploy/branding-database.service" /etc/systemd/system/branding-database.service
install -m 0644 "$staging/deploy/branding-database.nginx.conf" /etc/nginx/snippets/branding-database.conf
site_config="$(readlink -f /etc/nginx/sites-enabled/mikeywa.site)"
install -d -m 0700 /etc/nginx/branding-backups
cp -a "$site_config" "/etc/nginx/branding-backups/mikeywa.site-$release"
if ! grep -q 'include /etc/nginx/snippets/branding-database.conf;' "$site_config"; then
  sed -i '/root \/var\/www\/mikeywa-site\/current;/a\    include /etc/nginx/snippets/branding-database.conf;' "$site_config"
fi
nginx -t
old_api="$(readlink /opt/branding-database/current || true)"
old_web="$(readlink /var/www/branding-database/current || true)"
ln -sfn "/opt/branding-database/releases/$release" /opt/branding-database/current.next
mv -Tf /opt/branding-database/current.next /opt/branding-database/current
systemctl daemon-reload
systemctl enable branding-database.service >/dev/null
systemctl restart branding-database.service
healthy=false
for attempt in 1 2 3 4 5; do
  if curl -fsS http://127.0.0.1:8836/brandingdatabse/api/health >/dev/null; then healthy=true;break;fi
  sleep 1
done
if [ "$healthy" != true ]; then
 if [ -n "$old_api" ]; then ln -sfn "$old_api" /opt/branding-database/current;systemctl restart branding-database.service;fi
 echo 'API health check failed';exit 1
fi
ln -sfn "/var/www/branding-database/releases/$release" /var/www/branding-database/current.next
mv -Tf /var/www/branding-database/current.next /var/www/branding-database/current
systemctl reload nginx
printf 'released=%s\nprevious_api=%s\nprevious_web=%s\n' "$release" "$old_api" "$old_web"
rm -f "$staging/service.env"
