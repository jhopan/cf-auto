"""
cf_worker_token.py — Module 5: Buat API Token "Edit Cloudflare Workers"

Tanggung jawab:
  - Navigasi ke /profile/api-tokens
  - Klik "Create Token"
  - Pilih template card "Edit Cloudflare Workers" (UI baru CF,
    Policies terisi otomatis — Account/Zone Resources sudah dihapus CF)
  - Klik "Continue to summary"
  - Klik "Create Token"
  - Copy token (cfut_...)
  - Simpan & return token

Semua di tab yang sama.
"""
from __future__ import annotations
import re
import os
import time
import logging
from typing import Optional

from playwright.sync_api import Page

try:
    from .cf_helpers import (
        log,
        fill_input,
        wait_and_click,
        wait_for_turnstile,
        dismiss_cookie_banner,
    )
except ImportError:
    from cf_helpers import (
        log,
        fill_input,
        wait_and_click,
        wait_for_turnstile,
        dismiss_cookie_banner,
    )

__all__ = ["GetWorkerToken"]

API_TOKENS_URL = "https://dash.cloudflare.com/profile/api-tokens"


def _click_account_option(page: Page, email: str) -> bool:
    """Klik dropdown Account Resources lalu pilih akun yang cocok email.

    Form CF pakai <BUTTON aria-haspopup="listbox"> custom. Langkah:
    1. Klik button 'Select...' (sudah di-scroll oleh pemanggil)
    2. Tunggu menu (role=listbox / option visible)
    3. Pilih option yang mengandung email prefix (case-insensitive)
    """
    email_prefix = (email or "").split("@")[0].lower()
    log.info("→ Klik button Select... (Account Resources)")

    # klik button 'Select...' di section Account Resources — SCROLL
    # ke posisi terlihat dulu, lalu klik REAL (page.mouse).
    # Parent-walk kadang tidak menemukan 'Account Resources' (label
    # section bukan ancestor langsung di DOM baru CF) → fallback:
    # ambil button 'Select...' pertama yang visible.
    r = page.evaluate("""() => {
        const btns = Array.from(document.querySelectorAll(
            'button[aria-haspopup="listbox"], [aria-haspopup="listbox"]'));
        const selects = btns.filter(b => (b.textContent || '').trim() === 'Select...');
        let target = null;
        // strategy 1: parent mengandung 'Account Resources'
        for (const b of selects) {
            let p = b.parentElement;
            let ok = false;
            for (let j = 0; j < 15; j++) {
                if (!p) break;
                const pt = (p.textContent || '');
                if (pt.includes('Account Resources')) { ok = true; break; }
                p = p.parentElement;
            }
            if (ok) { target = b; break; }
        }
        // strategy 2: fallback — ambil button 'Select...' pertama.
        // (jangan filter visible; button Account Resources JUSTRU di bawah
        //  layar dan itu yang mau kita scroll ke tengah)
        if (!target && selects.length > 0) {
            target = selects[0];
        }
        if (!target) return null;
        target.scrollIntoView({block: 'center'});
        return true;
    }""")
    if not r:
        log.warning("⚠ Dropdown Account (Select...) tidak ditemukan")
        return False
    time.sleep(1.0)

    # ambil koordinat segar SETELAH scroll
    r = page.evaluate("""() => {
        const btns = Array.from(document.querySelectorAll(
            'button[aria-haspopup="listbox"], [aria-haspopup="listbox"]'));
        const selects = btns.filter(b => (b.textContent || '').trim() === 'Select...');
        let target = null;
        for (const b of selects) {
            let p = b.parentElement;
            let ok = false;
            for (let j = 0; j < 15; j++) {
                if (!p) break;
                const pt = (p.textContent || '');
                if (pt.includes('Account Resources')) { ok = true; break; }
                p = p.parentElement;
            }
            if (ok) { target = b; break; }
        }
        if (!target && selects.length > 0) {
            target = selects[0];
        }
        if (!target) return null;
        const rect = target.getBoundingClientRect();
        return { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 };
    }""")
    if not r:
        log.warning("⚠ Koordinat dropdown Account tidak didapat")
        return False
    log.info("→ Klik REAL dropdown Account di (%.0f, %.0f)", r['x'], r['y'])
    page.mouse.click(r['x'], r['y'])
    time.sleep(1.0)

    # tunggu menu
    menu_found = False
    for _ in range(10):
        time.sleep(0.5)
        menu_found = page.evaluate("""() => {
            const lb = document.querySelector('[role="listbox"]');
            if (lb) {
                const r = lb.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) return true;
            }
            return false;
        }""")
        if menu_found:
            break
    if menu_found:
        log.info("→ Menu Account terbuka")
    else:
        log.warning("⚠ Menu Account tidak terdeteksi")
        time.sleep(2)

    # cari option dengan email prefix
    opt = page.evaluate(f"""() => {{
        const all = document.querySelectorAll('*');
        const results = [];
        for (const o of all) {{
            const t = (o.textContent || '').trim();
            if (t.length > 0 && t.length < 80) {{
                const r = o.getBoundingClientRect();
                if (r.width > 0 && r.height > 0 && r.height < 60) {{
                    results.push({{
                        text: t.slice(0, 60),
                        x: r.x + r.width/2,
                        y: r.y + r.height/2,
                    }});
                }}
            }}
        }}
        return results;
    }}""")
    for o in opt:
        t = (o.get("text", "") or "").lower()
        if t.startswith("all accounts"):
            continue  # jangan pilih All accounts
        if email_prefix in t:
            page.mouse.click(o["x"], o["y"])
            log.info("✓ Akun dipilih: %s", o["text"][:40])
            return True

    log.warning("⚠ Option akun (%s...) tidak ditemukan", email_prefix[:12])
    page.keyboard.press("Escape")
    return False


class GetWorkerToken:
    """Module 5: Buat API Token dengan template Edit Cloudflare Workers."""

    def __init__(self, email: str):
        """
        Args:
            email: Email akun Cloudflare (untuk identifikasi account name
                   di dropdown "Account Resources")
        """
        self.email = email

    def run(self, page: Page) -> Optional[str]:
        """Jalankan create worker token flow.

        Returns:
            Token string (cfut_...) jika berhasil, None jika gagal.
        """
        log.info("═══ Module 5: Edit Cloudflare Workers API Token ═══")

        # --- Step A: Navigasi ke API Tokens ---
        log.info("→ Navigasi ke /profile/api-tokens")
        # Retry karena NS_BINDING_ABORTED bisa terjadi saat Cloudflare redirect
        for attempt in range(3):
            try:
                page.goto(API_TOKENS_URL, wait_until="domcontentloaded", timeout=60000)
                break
            except Exception as e:
                log.warning("⚠ Navigasi gagal (attempt %d): %s", attempt + 1, str(e)[:60])
                time.sleep(3.0)
        time.sleep(5.0)
        dismiss_cookie_banner(page)
        log.info("  URL: %s", page.url)

        # Guard: kalau di-redirect ke /login, session tidak valid
        # (bisa karena CF membatasi IP: 403/rate-limit)
        if "/login" in page.url:
            log.error("✗ Session tidak login (redirect ke /login) — "
                      "kemungkinan CF membatasi IP ini")
            return None

        # --- Step B: Klik "Create Token" ---
        log.info("→ Klik Create Token...")
        create_clicked = False
        for sel in [
            'a:has-text("Create Token")',
            'button:has-text("Create Token")',
        ]:
            try:
                el = page.wait_for_selector(sel, timeout=10000, state="visible")
                if el:
                    el.click(force=True, timeout=5000)
                    create_clicked = True
                    log.info("✓ Klik Create Token (%s)", sel)
                    break
            except Exception:
                continue

        if not create_clicked:
            page.evaluate("""() => {
                const els = Array.from(document.querySelectorAll('a, button'));
                const btn = els.find(e => e.textContent.trim().includes('Create Token'));
                if (btn) btn.click();
            }""")
            log.info("→ Klik Create Token via JS")

        time.sleep(3.0)

        # --- Step C: pilih template card 'Edit Cloudflare Workers' ---
        # UI Cloudflare BARU: template = card button (bukan 'Use template'),
        # dan section 'Account Resources'/'Zone Resources' SUDAH DIHAPUS CF.
        # Card template otomatis mengisi Policies (Zone/Account/User policy).
        log.info("→ Pilih template 'Edit Cloudflare Workers'...")
        template_ok = False

        # kalau card tidak terlihat, buka 'View all templates' dulu
        try:
            body_now = page.inner_text("body")
        except Exception:
            body_now = ""
        if "Edit Cloudflare Workers" not in body_now:
            log.info("→ Card tidak di layar, buka 'View all templates'...")
            try:
                page.click('button:has-text("View all templates")', timeout=6000)
                time.sleep(4)
            except Exception:
                pass

        for sel in [
            'button:has-text("Edit Cloudflare Workers")',
            'a:has-text("Edit Cloudflare Workers")',
        ]:
            try:
                el = page.wait_for_selector(sel, timeout=5000, state="visible")
                if el:
                    el.scroll_into_view_if_needed(timeout=3000)
                    el.click(timeout=5000)
                    template_ok = True
                    log.info("✓ Klik card 'Edit Cloudflare Workers' (%s)", sel)
                    break
            except Exception:
                continue

        if not template_ok:
            template_ok = page.evaluate("""() => {
                const bs = Array.from(document.querySelectorAll('button, a'));
                const b = bs.find(e => (e.textContent || '')
                    .includes('Edit Cloudflare Workers'));
                if (b) {
                    b.scrollIntoView({block: 'center'});
                    b.click();
                    return true;
                }
                return false;
            }""")
            if template_ok:
                log.info("✓ Klik card 'Edit Cloudflare Workers' (JS)")

        time.sleep(6)

        # verifikasi: Policies terisi setelah card dipilih
        policies_ok = False
        try:
            body = page.inner_text("body")
            policies_ok = ("Zone policy" in body or "Account policy" in body
                           or "User policy" in body)
            if template_ok and policies_ok:
                log.info("✓ Template terpasang — Policies terisi")
            elif template_ok:
                log.warning("⚠ Card diklik tapi Policies belum terlihat")
            else:
                log.error("✗ Card 'Edit Cloudflare Workers' tidak ditemukan")
        except Exception:
            pass

        if not template_ok:
            # diagnostik: tombol apa saja yang ada di layar + screenshot
            try:
                btns = page.evaluate("""() => Array.from(
                        document.querySelectorAll('button, a'))
                    .filter(e => e.offsetParent !== null)
                    .map(e => (e.textContent || '').trim().slice(0, 45))
                    .filter(t => t.length > 0).slice(0, 25)""")
                log.info("→ Tombol di layar: %s", btns)
                debug_dir = os.path.join(
                    os.path.dirname(__file__), "..", "debug")
                os.makedirs(debug_dir, exist_ok=True)
                page.screenshot(path=os.path.join(
                    debug_dir, "worker_template_fail.png"))
                log.info("→ Screenshot: debug/worker_template_fail.png")
            except Exception:
                pass
            log.error("✗ Abort Module 5 — template tidak terpasang")
            return None

        # --- Step D: Token name (opsional, biar rapi di daftar token) ---
        try:
            name_el = page.query_selector('input[name="name"]')
            if name_el:
                cur = (name_el.input_value() or "").strip()
                if not cur:
                    name_el.click(timeout=3000)
                    name_el.fill("Edit Cloudflare Workers", timeout=5000)
                    log.info("✓ Token name diisi: Edit Cloudflare Workers")
        except Exception as e:
            log.warning("⚠ Token name dilewati: %s", str(e)[:60])

        time.sleep(1.0)

        # --- Step E: screenshot debug sebelum summary ---
        try:
            debug_dir = os.path.join(
                os.path.dirname(__file__), "..", "debug"
            )
            os.makedirs(debug_dir, exist_ok=True)
            page.screenshot(path=os.path.join(debug_dir, "before_summary.png"))
        except Exception:
            pass

        time.sleep(1.0)

        # --- Step F: Klik "Continue to summary" ---
        log.info("→ Klik 'Continue to summary'...")

        cont_clicked = False
        for sel in [
            'button:has-text("Continue to summary")',
            'a:has-text("Continue to summary")',
            'button:has-text("Continue")',
        ]:
            try:
                el = page.wait_for_selector(sel, timeout=10000, state="visible")
                if el:
                    el.click(force=True, timeout=5000)
                    cont_clicked = True
                    log.info("✓ Klik Continue to summary (%s)", sel)
                    break
            except Exception:
                continue

        if not cont_clicked:
            page.evaluate("""() => {
                const els = Array.from(document.querySelectorAll('button, a'));
                const btn = els.find(e => e.textContent.includes('Continue'));
                if (btn) btn.click();
            }""")
            log.info("→ Klik Continue via JS")

        time.sleep(3.0)

        # --- Step G: Klik "Create Token" ---
        log.info("→ Klik 'Create Token'...")

        token_created = False
        for sel in [
            'button:has-text("Create Token")',
            'a:has-text("Create Token")',
            'button[type="submit"]:has-text("Create")',
        ]:
            try:
                el = page.wait_for_selector(sel, timeout=10000, state="visible")
                if el:
                    el.click(force=True, timeout=5000)
                    token_created = True
                    log.info("✓ Klik Create Token (%s)", sel)
                    break
            except Exception:
                continue

        if not token_created:
            page.evaluate("""() => {
                const els = Array.from(document.querySelectorAll('button'));
                const btn = els.find(e => e.textContent.trim() === 'Create Token');
                if (btn) btn.click();
            }""")
            log.info("→ Klik Create Token via JS")

        # --- Step H: Tunggu token muncul ---
        log.info("→ Menunggu token muncul...")
        time.sleep(5.0)

        token = None
        deadline = time.time() + 30
        while time.time() < deadline:
            time.sleep(1.0)
            token = self._extract_token(page)
            if token:
                break

        if not token:
            log.error("✗ Worker API Token tidak ditemukan")
            try:
                debug_dir = os.path.join(
                    os.path.dirname(__file__), "..", "debug"
                )
                os.makedirs(debug_dir, exist_ok=True)
                page.screenshot(
                    path=os.path.join(debug_dir, "worker_token_fail.png")
                )
                body = page.inner_text("body")
                log.info("→ Body: %s", body[:300])
            except Exception:
                pass
            return None

        log.info(
            "✓✓✓ Worker API Token: %s ✓✓✓",
            token[:12] + "..." + token[-4:],
        )

        # Klik Copy (opsional)
        wait_and_click(
            page,
            [
                'button:has-text("Copy")',
                'button:has-text("Copy API Token")',
            ],
            timeout=5000, force=True,
        )

        return token

    def _extract_token(self, page: Page) -> Optional[str]:
        """Ekstrak API Token (cfut_...) dari halaman."""
        try:
            results = page.evaluate("""() => {
                const results = [];
                const sels = 'input, code, pre, .font-mono, span, div, p, textarea';
                document.querySelectorAll(sels).forEach(el => {
                    const v = (el.value || el.textContent || '').trim();
                    if (v.match(/^cfut_[A-Za-z0-9]+$/)) results.push(v);
                    if (v.match(/^[A-Za-z0-9_-]{40,60}$/) && v.length < 100)
                        results.push(v);
                });
                return results;
            }""")
            if results:
                return results[0]
        except Exception:
            pass

        try:
            body_text = page.inner_text("body")
            m = re.search(r"(cfut_[A-Za-z0-9]+)", body_text)
            if m:
                return m.group(1)
            m = re.search(r"\b([A-Za-z0-9_-]{40,60})\b", body_text)
            if m:
                return m.group(1)
        except Exception:
            pass

        return None
