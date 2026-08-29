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
log "  Cara atur config : python menucfauto.py"
log "  Jalankan akun    : python runner.py"
log "  (atau) --count N : python runner.py --count 3"
echo ""
log "Tips: di VPS/Linux set headless=true di config.json (menu 4)."
