"""
cf_telegram.py — Notifikasi Telegram untuk cf-auto.

Pengiriman satu arah (sendMessage/sendPhoto). Tanpa polling, tanpa webhook.
Dipanggil saat runner butuh bantuan manual (Turnstile stuck) atau laporan.

Config (config.json → "telegram"):
    bot_token              : token dari @BotFather
    chat_id                : chat tujuan (diisi via menu, auto-detect)
    notify_manual          : kirim notif saat butuh klik manual (default True)
    manual_timeout_minutes : berapa lama menunggu manual (default 10)
    notify_success         : notif juga saat akun sukses (default False)
"""
import json
import os

import requests

from cf_helpers import log

_BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(os.path.dirname(_BASE), "config.json")
API = "https://api.telegram.org"

CONFIG = {}


def _cfg():
    global CONFIG
    if not CONFIG:
        try:
            with open(CONFIG_PATH) as f:
                CONFIG = (json.load(f) or {}).get("telegram", {})
        except Exception:
            CONFIG = {}
    return CONFIG


def enabled():
    c = _cfg()
    return bool(c.get("bot_token") and c.get("chat_id"))


def send_message(text, silent=False):
    """Kirim teks. Return True kalau terkirim."""
    c = _cfg()
    if not (c.get("bot_token") and c.get("chat_id")):
        return False
    try:
        r = requests.post(
            f"{API}/bot{c['bot_token']}/sendMessage",
            json={
                "chat_id": c["chat_id"],
                "text": text,
                "parse_mode": "HTML",
                "disable_notification": silent,
            },
            timeout=15,
        )
        if r.status_code != 200:
            log.warning("⚠ Telegram sendMessage gagal: %s %s",
                        r.status_code, r.text[:120])
            return False
        return True
    except Exception as e:
        log.warning("⚠ Telegram error: %s", str(e)[:100])
        return False


def send_photo(path, caption="", silent=False):
    """Kirim file gambar (screenshot). Return True kalau terkirim."""
    c = _cfg()
    if not (c.get("bot_token") and c.get("chat_id")):
        return False
    try:
        with open(path, "rb") as f:
            r = requests.post(
                f"{API}/bot{c['bot_token']}/sendPhoto",
                data={"chat_id": c["chat_id"], "caption": caption[:1000]},
                files={"photo": f},
                timeout=30,
            )
        if r.status_code != 200:
            log.warning("⚠ Telegram sendPhoto gagal: %s %s",
                        r.status_code, r.text[:120])
            return False
        return True
    except Exception as e:
        log.warning("⚠ Telegram sendPhoto error: %s", str(e)[:100])
        return False


def notify_manual_need(idx, email, reason, screenshot_path=None):
    """Notif: akun butuh bantuan manual. Sekali per akun."""
    c = _cfg()
    if not c.get("notify_manual", True) or not enabled():
        return False
    vnc = (json.load(open(CONFIG_PATH)).get("browser", {}) or {}).get("vnc_domain", "")
    lines = [
        f"⚠ <b>Butuh bantuan manual — Akun #{idx}</b>",
        f"Email: <code>{email}</code>",
        f"Alasan: {reason}",
    ]
    if vnc:
        lines.append(f"👉 Buka VNC: https://{vnc}")
    txt = "\n".join(lines)
    ok = send_message(txt)
    if screenshot_path and os.path.exists(screenshot_path):
        send_photo(screenshot_path, caption=f"Akun #{idx} — {reason}")
    return ok


def notify_success(idx, email, account_id):
    """Notif sukses (opsional, default off)."""
    c = _cfg()
    if not c.get("notify_success") or not enabled():
        return False
    return send_message(
        f"✅ Akun #{idx} sukses\n"
        f"Email: <code>{email}</code>\n"
        f"Account ID: <code>{account_id}</code>"
    )


def detect_chat_id(bot_token):
    """Ambil chat_id dari getUpdates (sekali saat setup, bukan polling)."""
    r = requests.get(f"{API}/bot{bot_token}/getUpdates", timeout=15)
    if r.status_code != 200:
        raise RuntimeError(f"getUpdates gagal: {r.status_code} {r.text[:120]}")
    updates = r.json().get("result", [])
    seen = []
    for u in updates:
        msg = u.get("message") or u.get("edited_message") or {}
        chat = msg.get("chat") or {}
        cid = chat.get("id")
        title = chat.get("title") or chat.get("username") or chat.get("first_name") or "?"
        if cid and (cid, title) not in seen:
            seen.append((cid, title))
    return seen
