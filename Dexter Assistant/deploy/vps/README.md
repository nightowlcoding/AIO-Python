# Dexter Assistant VPS Deploy (Ubuntu)

## 1) Provision server
- Ubuntu 22.04 LTS
- Open ports: 22, 80, 443
- DNS target for `app.dexterassist.com` should point to this server IP

## 2) Install OS packages
Run as root:

```bash
apt update
apt install -y python3 python3-venv python3-pip nginx certbot python3-certbot-nginx git
```

## 3) Copy project to server
Expected path:

```bash
/opt/dexter-assistant
```

If using git:

```bash
git clone <your-repo-url> /opt/dexter-assistant
```

If uploading manually, preserve this folder structure.

## 4) Python environment

```bash
cd /opt/dexter-assistant
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements_dexter_assistant.txt
```

## 5) Production config
Edit `dexter_assistant_config.json`:
- set `front_door.auto_open_browser` to `false`
- keep `front_door.host` as `127.0.0.1`
- keep `front_door.port` as `5080`

## 6) Systemd service

```bash
cp deploy/vps/dexter-assistant.service /etc/systemd/system/dexter-assistant.service
systemctl daemon-reload
systemctl enable dexter-assistant
systemctl start dexter-assistant
systemctl status dexter-assistant --no-pager
```

## 7) Nginx reverse proxy

```bash
cp deploy/vps/nginx-dexterassist.com.conf /etc/nginx/sites-available/dexterassist.com
ln -sf /etc/nginx/sites-available/dexterassist.com /etc/nginx/sites-enabled/dexterassist.com
nginx -t
systemctl reload nginx
```

## 8) SSL certificate
After DNS for `app.dexterassist.com` points to server IP and resolves:

```bash
certbot --nginx -d app.dexterassist.com --redirect -m you@dexterassist.com --agree-tos -n
```

## 9) Verify
- `https://app.dexterassist.com/`
- `https://app.dexterassist.com/portal/productmix`
- `https://app.dexterassist.com/portal/ic3`

## Useful commands

```bash
journalctl -u dexter-assistant -f
systemctl restart dexter-assistant
systemctl restart nginx
```
