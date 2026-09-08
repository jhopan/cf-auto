#!/usr/bin/env bash
# ============================================================
# install.sh — Install cf-auto di Windows (git-bash), Linux, macOS
#
# Auto-detect OS:
#   - Install Python dependencies (camoufox[geoip], playwright, requests)
#   - Install Playwright system dependencies (Linux saja)
#   - Copy config.example.json -> config.json kalau belum ada
#
# Jalankan:   bash install.sh
# ============================================================
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

log()  { printf "\033[1;32m[install]\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[warn]\033[0m %s\n" "$*"; }
die()  { printf "\033[1;31m[error]\033[0m %s\n" "$*"; exit 1; }

# ------------------------------------------------------------
# 1. Deteksi OS
# ------------------------------------------------------------
OS="$(uname -s)"
case "$OS" in
    Linux*)  OS_NAME="linux" ;;
    Darwin*) OS_NAME="macos" ;;
    MINGW*|MSYS*|CYGWIN*) OS_NAME="windows" ;;
    *)       warn "OS tidak dikenali ($OS), anggap Linux."; OS_NAME="linux" ;;
esac
log "OS terdeteksi: $OS_NAME"

# ------------------------------------------------------------
# 2. Cari Python (hindari alias palsu Microsoft Store)
# ------------------------------------------------------------
PYTHON=""
# Prioritas: python (asli) > py launcher > python3
# Deteksi python palsu: versi berisi "Python was not found" / "Microsoft Store"
for cand in python py python3; do
    if command -v "$cand" >/dev/null 2>&1; then
        # Cek versi; kalau keluar pesan palsu, skip
        VER="$("$cand" --version 2>&1 || true)"
        if echo "$VER" | grep -qi "was not found\|Microsoft Store\|App execution aliases"; then
            continue
        fi
        # Untuk 'py' launcher, pilih versi terbaru: py -3
        if [ "$cand" = "py" ]; then
            if "$cand" -3 --version >/dev/null 2>&1; then
                PYTHON="py -3"
            else
                continue
            fi
        else
            PYTHON="$(command -v "$cand")"
        fi
        break
    fi
done
[ -z "$PYTHON" ] && die "Python tidak ditemukan. Install Python 3.11+ dulu (jangan dari Microsoft Store)."

log "Python: $PYTHON ($("$PYTHON" --version 2>&1))"

# ------------------------------------------------------------
# 3. Install Python dependencies
# ------------------------------------------------------------
# Deteksi PEP 668 (Debian 12+/Ubuntu 23+) — pip system diblokir
PEP668=0
if [ "$OS_NAME" = "linux" ] || [ "$OS_NAME" = "macos" ]; then
    if [ -f "/usr/lib/python3.13/EXTERNALLY-MANAGED" ] || \
       ls /usr/lib/python3*/EXTERNALLY-MANAGED >/dev/null 2>&1 || \
       "$PYTHON" -c "import sysconfig, os; sys.exit(0 if os.path.exists(os.path.join(sysconfig.get_path('stdlib'), 'EXTERNALLY-MANAGED')) else 1)" 2>/dev/null; then
        PEP668=1
    fi
fi

if [ "$PEP668" = "1" ] && [ -z "$VIRTUAL_ENV" ]; then
    log "PEP 668 terdeteksi (externally-managed) — pakai venv."
    VENV_DIR="$PROJECT_DIR/venv"
    if [ ! -d "$VENV_DIR" ]; then
        log "Buat venv di $VENV_DIR..."
        "$PYTHON" -m venv "$VENV_DIR" 2>/dev/null || "$PYTHON" -m venv --without-pip "$VENV_DIR" && "$VENV_DIR/bin/python" -m ensurepip >/dev/null 2>&1 || true
        [ -d "$VENV_DIR" ] || die "Gagal buat venv. Install: sudo apt install python3-venv"
    fi
    # Aktifkan venv untuk sisa script
    . "$VENV_DIR/bin/activate"
    PYTHON="$VENV_DIR/bin/python"
    log "Python (venv): $PYTHON"
fi

log "Install dependencies Python..."
"$PYTHON" -m pip install --upgrade pip >/dev/null 2>&1 || warn "pip upgrade gagal (lanjut)."
"$PYTHON" -m pip install -r requirements.txt || die "Gagal install pip requirements."

# ------------------------------------------------------------
# 4. Download binary Camoufox browser (DNS/geoip library)
# ------------------------------------------------------------
log "Download binary Camoufox browser..."
"$PYTHON" -m camoufox fetch || warn "camoufox fetch gagal. Jalankan manual: python -m camoufox fetch"

# ------------------------------------------------------------
# 5. Playwright system deps (Linux saja)
# ------------------------------------------------------------
if [ "$OS_NAME" = "linux" ]; then
    log "Install Playwright system dependencies (Linux)..."
    "$PYTHON" -m playwright install-deps || warn "playwright install-deps gagal (jalankan manual: playwright install-deps)"
    # Xvfb untuk headless='virtual' Camoufox (virtual display)
    if ! command -v Xvfb >/dev/null 2>&1; then
        log "Install Xvfb (untuk headless='virtual')..."
        (sudo apt-get install -y xvfb 2>/dev/null || sudo dnf install -y xorg-x11-server-Xvfb 2>/dev/null || warn "Xvfb gagal di-install. Install manual: apt install xvfb")
    else
        log "Xvfb sudah terinstall."
    fi
fi

# ------------------------------------------------------------
# 6. Copy config.example.json -> config.json kalau belum ada
# ------------------------------------------------------------
if [ ! -f config.json ]; then
    if [ -f config.example.json ]; then
        cp config.example.json config.json
        log "config.json dibuat dari config.example.json."
        warn "EDIT config.json: isi API key temp mail, domain, dan headless (true untuk VPS/Linux)."
    else
        warn "config.example.json tidak ada. Buat config.json manual."
    fi
else
    log "config.json sudah ada, tidak dioverwrited."
fi

# ------------------------------------------------------------
# 7. Selesai
# ------------------------------------------------------------
echo ""
log "═══ INSTALL SELESAI ═══"
log "  Cara atur config : python menu.py"
log "  Jalankan akun    : python main.py"
log "  (atau) --count N : python main.py --count 3"
echo ""
if [ "$OS_NAME" = "linux" ]; then
    if [ "$PEP668" = "1" ]; then
        log "Linux + venv: jalankan dengan ./venv/bin/python main.py"
    fi
    log "Rekomendasi mode browser: 'virtual' (Xvfb 1920x1080) — menu 4 → pilih 3"
else
    log "Windows: mode browser 'visible' (headless='false' di config.json)"
fi
