"""
vnc.py — Manajemen VNC untuk cf-auto (Linux).

Komponen:
  - Xvfb (display virtual) — ditampilkan oleh runner virtual mode
  - x11vnc (mirror display → VNC server, localhost saja)
  - websockify (VNC → WebSocket) + noVNC web
  - cloudflared tunnel (opsional, untuk akses via domain)

Mode:
  - on_demand: semua komponen start saat runner jalan, kill saat selesai
  - permanent: systemd services, hidup 24/7 (dibuat via menu)
"""
import os
import shutil
import subprocess
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def log(msg):
    import logging
    logging.getLogger("vnc").info(msg)


def _which(name):
    return shutil.which(name)


def _run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def _popen(cmd):
    return subprocess.Popen(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


# ---------------------------------------------------------------------------
# Xvfb
# ---------------------------------------------------------------------------
def start_xvfb(display=":98", w=1920, h=1080):
    """Start Xvfb kalau belum jalan. Return Popen atau None kalau sudah jalan."""
    if not _which("Xvfb"):
        raise RuntimeError("Xvfb tidak ada. Install: sudo apt install xvfb")
    # Sudah jalan? (cek lock atau pgrep)
    r = _run(["pgrep", "-f", f"Xvfb {display}"])
    if r.returncode == 0:
        log(f"Xvfb {display} sudah jalan")
        return None
    proc = _popen([
        "Xvfb", display, "-screen", "0", f"{w}x{h}x24",
        "-ac", "-nolisten", "tcp",
    ])
    time.sleep(2)
    log(f"Xvfb {display} {w}x{h} di-start (pid {proc.pid})")
    return proc


def stop_xvfb(display=":98"):
    _run(["pkill", "-f", f"Xvfb {display}"])
    log(f"Xvfb {display} di-stop")


# ---------------------------------------------------------------------------
# x11vnc + websockify
# ---------------------------------------------------------------------------
def start_vnc(display=":98", password="", port=6081, vnc_port=5901):
    """Start x11vnc + websockify+noVNC. Return (x11vnc_proc, websockify_proc)."""
    procs = [None, None]

    if not _which("x11vnc"):
        raise RuntimeError("x11vnc tidak ada. Install: sudo apt install x11vnc")
    if not _which("websockify"):
        raise RuntimeError(
            "websockify tidak ada. Install: sudo apt install novnc websockify"
        )

    passfile = os.path.expanduser("~/.vnc/cfauto.pass")

    # x11vnc — VNC server di localhost:vnc_port (5901, unik per project)
    r = _run(["pgrep", "-x", "x11vnc"])
    if r.returncode != 0:
        cmd = [
            "x11vnc", "-display", display,
            "-rfbport", str(vnc_port),
            "-localhost", "-forever", "-repeat", "-shared",
        ]
        if password:
            os.makedirs(os.path.dirname(passfile), exist_ok=True)
            if not os.path.exists(passfile):
                _run(["x11vnc", "-storepasswd", password, passfile])
            cmd += ["-rfbauth", passfile]
        procs[0] = _popen(cmd)
        log(f"x11vnc di-start (localhost:{vnc_port})")
    else:
        log("x11vnc sudah jalan")

    # websockify — bridge WebSocket → VNC + serve noVNC web di :port
    novnc_web = None
    for p in ["/usr/share/novnc", "/usr/share/webapps/novnc"]:
        if os.path.isdir(p):
            novnc_web = p
            break

    r = _run(["pgrep", "-x", "websockify"])
    if r.returncode != 0:
        cmd = ["websockify"]
        if novnc_web:
            cmd += ["--web", novnc_web]
        cmd += [str(port), f"localhost:{vnc_port}"]
        procs[1] = _popen(cmd)
        log(f"websockify di-start (:{port})")
    else:
        log("websockify sudah jalan")

    return procs[0], procs[1]


def stop_vnc():
    _run(["pkill", "-x", "x11vnc"])
    _run(["pkill", "-x", "websockify"])
    log("x11vnc + websockify di-stop")


# ---------------------------------------------------------------------------
# Cloudflare Tunnel
# ---------------------------------------------------------------------------
def tunnel_cmd(domain, tunnel_name="cfvnc", port=6081):
    """Return command cloudflared untuk tunnel ke noVNC."""
    return [
        "cloudflared", "tunnel", "run", tunnel_name,
    ]


def tunnel_config_text(domain, tunnel_name="cfvnc", port=6081):
    """Config yml untuk cloudflared tunnel VNC."""
    return (
        f"tunnel: {tunnel_name}\n"
        f"credentials-file: ~/.cloudflared/{tunnel_name}.json\n"
        "ingress:\n"
        f"  - hostname: {domain}\n"
        f"    service: http://localhost:{port}\n"
        "  - service: http_status:404\n"
    )


def is_tunnel_installed(tunnel_name="cfvnc"):
    """Cek apakah cloudflared tunnel sudah dibuat (credentials ada)."""
    cred = os.path.expanduser(f"~/.cloudflared/{tunnel_name}.json")
    return os.path.exists(cred) and _which("cloudflared") is not None


def start_tunnel(tunnel_name="cfvnc"):
    if not _which("cloudflared"):
        log("cloudflared tidak ada — tunnel dilewati")
        return None
    r = _run(["pgrep", "-f", f"cloudflared tunnel run {tunnel_name}"])
    if r.returncode == 0:
        log("cloudflared tunnel sudah jalan")
        return None
    proc = _popen(["cloudflared", "tunnel", "run", tunnel_name])
    log(f"cloudflared tunnel '{tunnel_name}' di-start")
    return proc


# ---------------------------------------------------------------------------
# High-level: dipanggil runner & menu
# ---------------------------------------------------------------------------
def start_stack(cfg):
    """
    Start Xvfb + VNC sesuai config. Dipanggil runner saat mode virtual.

    Returns:
        dict: {'xvfb': proc|None, 'x11vnc': proc|None, 'websockify': proc|None,
               'tunnel': proc|None, 'vnc_enabled': bool}
    """
    br = cfg.get("browser", {})
    display = br.get("vnc_display", ":98")
    result = {"xvfb": None, "x11vnc": None, "websockify": None,
              "tunnel": None, "vnc_enabled": False}

    result["xvfb"] = start_xvfb(display)

    if br.get("vnc"):
        try:
            result["x11vnc"], result["websockify"] = start_vnc(
                display,
                br.get("vnc_password", ""),
                int(br.get("vnc_port", 6081)),
            )
            result["vnc_enabled"] = True
            domain = br.get("vnc_domain", "")
            if domain:
                log(f"→ VNC web: https://{domain} (password Anda)")
            else:
                log(f"→ VNC web: http://localhost:{br.get('vnc_port', 6081)}")
        except RuntimeError as e:
            log(f"⚠ VNC dilewati: {e}")

    return result


def stop_stack(stack, force_vnc=False):
    """Stop komponen yang di-start oleh runner (on_demand)."""
    if not stack:
        return
    br_cfg = stack.get("_cfg", {})
    if stack.get("x11vnc") or force_vnc:
        stop_vnc()
    if stack.get("xvfb"):
        try:
            stack["xvfb"].terminate()
            stack["xvfb"].wait(timeout=5)
        except Exception:
            try:
                stack["xvfb"].kill()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# systemd permanent mode
# ---------------------------------------------------------------------------
SYSTEMD_VNC = """[Unit]
Description=cf-auto VNC stack (x11vnc + websockify/noVNC)
After=cfauto-display.service
Requires=cfauto-display.service

[Service]
User={user}
Type=simple
ExecStart=/usr/bin/x11vnc -display {display} -rfbport {vnc_port} -rfbauth {home}/.vnc/cfauto.pass -localhost -forever -repeat -shared
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""

SYSTEMD_NOVNC = """[Unit]
Description=cf-auto noVNC web ({port})
After=cfvnc.service
Requires=cfvnc.service

[Service]
User={user}
Type=simple
ExecStart=/usr/bin/websockify --web /usr/share/novnc {port} localhost:{vnc_port}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""

SYSTEMD_XVFB = """[Unit]
Description=cf-auto Xvfb virtual display

[Service]
Type=simple
ExecStart=/usr/bin/Xvfb {display} -screen 0 1920x1080x24 -ac -nolisten tcp
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""

SYSTEMD_TUNNEL = """[Unit]
Description=cf-auto cloudflared tunnel (VNC)
After=network.target

[Service]
User={user}
Type=simple
ExecStart=/usr/local/bin/cloudflared tunnel --no-autoupdate --config /etc/cloudflared/cfauto.yml run {tunnel}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""


def systemd_write(cfg):
    """Tulis 4 service file (butuh sudo saat penerapan). Return dict nama→isi."""
    import getpass
    user = getpass.getuser()
    home = os.path.expanduser("~")
    br = cfg.get("browser", {})
    display = br.get("vnc_display", ":98")
    port = int(br.get("vnc_port", 6081))
    vnc_port = 5901
    tunnel = "cfvnc"

    return {
        "cfauto-display.service": SYSTEMD_XVFB.format(display=display, user=user),
        "cfauto-vnc.service": SYSTEMD_VNC.format(
            user=user, home=home, display=display, vnc_port=vnc_port
        ),
        "cfauto-novnc.service": SYSTEMD_NOVNC.format(
            user=user, port=port, vnc_port=vnc_port
        ),
        "cloudflare-cfauto.service": SYSTEMD_TUNNEL.format(user=user, tunnel=tunnel),
    }


def systemd_print(cfg):
    """Print semua service file + perintah penerapan (untuk di-copy user)."""
    files = systemd_write(cfg)
    print("Salin 4 file berikut ke /etc/systemd/system/, lalu jalankan")
    print("perintah enable di bawah:\n")
    for name, content in files.items():
        print(f"───── /etc/systemd/system/{name} ─────")
        print(content)
    print("───── Perintah penerapan ─────")
    print("sudo cp *.service /etc/systemd/system/  # dari folder file ini")
    print("sudo systemctl daemon-reload")
    print("sudo systemctl enable --now cfauto-display cfauto-vnc cfauto-novnc cloudflare-cfauto")
    print()
    print("Status: systemctl status cfauto-display cfauto-vnc cfauto-novnc cloudflare-cfauto")
