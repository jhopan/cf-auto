"""
cf_worker_token.py — Module 5: Buat API Token "Edit Cloudflare Workers"

Tanggung jawab:
  - Navigasi ke /profile/api-tokens
  - Klik "Create Token"
  - Cari template "Edit Cloudflare Workers" → klik "Use template"
  - Scroll ke "Account Resources" → pilih akun (BUKAN "All accounts")
  - Scroll ke "Zone Resources" → pilih "All zones"
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
    # Event sintetik (dispatchEvent) ke elemen di luar viewport
    # diabaikan React/custom dropdown CF.
    found = page.evaluate("""() => {
        const btns = Array.from(document.querySelectorAll(
            'button[aria-haspopup="listbox"], [aria-haspopup="listbox"]'));
        for (const b of btns) {
            const txt = (b.textContent || '').trim();
            if (txt !== 'Select...') continue;
            let p = b.parentElement;
            for (let j = 0; j < 10; j++) {
                if (!p) break;
                const pt = (p.textContent || '');
                if (pt.includes('Account Resources')
                        && !pt.includes('Zone Resources')) {
                    b.scrollIntoView({block: 'center'});
                    return true;
                }
                p = p.parentElement;
            }
        }
        return false;
    }""")
    if not found:
        log.warning("⚠ Dropdown Account (Select...) tidak ditemukan")
        return False
    time.sleep(1.0)

    # ambil koordinat segar SETELAH scroll
    r = page.evaluate("""() => {
        const btns = Array.from(document.querySelectorAll(
            'button[aria-haspopup="listbox"], [aria-haspopup="listbox"]'));
        for (const b of btns) {
            const txt = (b.textContent || '').trim();
            if (txt !== 'Select...') continue;
            let p = b.parentElement;
            for (let j = 0; j < 10; j++) {
                if (!p) break;
                const pt = (p.textContent || '');
                if (pt.includes('Account Resources')
                        && !pt.includes('Zone Resources')) {
                    const rect = b.getBoundingClientRect();
                    return {
                        x: rect.x + rect.width / 2,
                        y: rect.y + rect.height / 2,
                    };
                }
                p = p.parentElement;
            }
        }
        return null;
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

        # --- Step C: Cari template "Edit Cloudflare Workers" → klik "Use template" ---
        log.info("→ Cari template 'Edit Cloudflare Workers'...")
        template_clicked = False

        try:
            for sel in [
                'text="Edit Cloudflare Workers" >> .. >> button:has-text("Use template")',
                'div:has-text("Edit Cloudflare Workers") button:has-text("Use template")',
                'li:has-text("Edit Cloudflare Workers") button:has-text("Use template")',
                'tr:has-text("Edit Cloudflare Workers") button:has-text("Use template")',
            ]:
                try:
                    loc = page.locator(sel).first
                    if loc.count() > 0:
                        loc.click(force=True, timeout=5000)
                        template_clicked = True
                        log.info("✓ Klik Use template (Edit Cloudflare Workers)")
                        break
                except Exception:
                    continue
        except Exception as e:
            log.warning("⚠ Step C locator error: %s", str(e)[:80])

        if not template_clicked:
            try:
                result = page.evaluate("""() => {
                    const btns = Array.from(
                        document.querySelectorAll('button, a')
                    ).filter(b => b.textContent.includes('Use template'));
                    for (const btn of btns) {
                        const row = btn.closest('tr, div, li, section');
                        if (row && row.textContent.includes('Edit Cloudflare Workers')) {
                            btn.click();
                            return true;
                        }
                    }
                    return false;
                }""")
                if result:
                    template_clicked = True
                    log.info("✓ Klik Use template via JS (Edit Cloudflare Workers)")
            except Exception as e:
                log.warning("⚠ Step C JS error: %s", str(e)[:80])

        if not template_clicked:
            log.error("✗ Template 'Edit Cloudflare Workers' tidak ditemukan!")

        import time as _time
        _time.sleep(5)

        print(">>> STEP D START", flush=True)
        # --- Step D: Account Resources -> pilih akun ---
        # Form CF pakai <BUTTON aria-haspopup=listbox> custom,
        # helper _click_account_option handle scroll+klik+pilih
        log.info("-> Setting Account Resources...")
        account_selected = False

        try:
            account_selected = _click_account_option(page, self.email)
        except Exception as e:
            log.warning("⚠ Account error: %s", str(e)[:100])

        time.sleep(1.0)

        # --- Step E: Zone Resources → "Specific zone" → "All zones" ---
        log.info("→ Setting Zone Resources (All zones)...")
        zone_selected = False

        try:
            zpos = page.evaluate("""() => {
                const ctrls = document.querySelectorAll('[class*="react-select__control"], [class*="control"]');
                for (const ctrl of ctrls) {
                    if (ctrl.textContent.includes('Specific zone')) {
                        let p = ctrl;
                        for (let j = 0; j < 15; j++) {
                            p = p.parentElement;
                            if (!p) break;
                            if (p.textContent.includes('Zone Resources')) {
                                const r = ctrl.getBoundingClientRect();
                                return {x: r.x + r.width/2, y: r.y + r.height/2};
                            }
                        }
                    }
                }
                return null;
            }""")
            if zpos:
                log.info("→ Klik dropdown Zone di (%.0f, %.0f)", zpos['x'], zpos['y'])
                # Klik control dengan PointerEvent
                page.evaluate("""() => {
                    const ctrls = document.querySelectorAll('[class*="react-select__control"], [class*="control"]');
                    for (const ctrl of ctrls) {
                        if (ctrl.textContent.includes('Specific zone')) {
                            let p = ctrl;
                            for (let j = 0; j < 15; j++) {
                                p = p.parentElement;
                                if (!p) break;
                                if (p.textContent.includes('Zone Resources')) {
                                    ctrl.dispatchEvent(new PointerEvent('pointerdown',
                                        {bubbles: true, cancelable: true, pointerId: 1, pointerType: 'mouse'}));
                                    ctrl.dispatchEvent(new PointerEvent('pointerup',
                                        {bubbles: true, cancelable: true, pointerId: 1, pointerType: 'mouse'}));
                                    ctrl.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true}));
                                    ctrl.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true}));
                                    ctrl.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
                                    ctrl.click();
                                    return true;
                                }
                            }
                        }
                    }
                    return false;
                }""")
                # Tunggu menu muncul
                zmenu_found = False
                for _ in range(10):
                    time.sleep(0.5)
                    zmenu_found = page.evaluate("""() => {
                        return !!document.querySelector(
                            '[class*="react-select__menu"]'
                        );
                    }""")
                    if zmenu_found:
                        break
                if zmenu_found:
                    log.info("→ Menu Zone terbuka")
                else:
                    log.warning("⚠ Menu Zone tidak terdeteksi")
                    time.sleep(2)

                zopt = page.evaluate("""() => {
                    const all = document.querySelectorAll('*');
                    const results = [];
                    for (const o of all) {
                        const directText = Array.from(o.childNodes)
                            .filter(n => n.nodeType === 3)
                            .map(n => n.textContent.trim())
                            .join('');
                        if (directText === 'All zones') {
                            const r = o.getBoundingClientRect();
                            if (r.width > 0 && r.height > 0 && r.height < 50) {
                                results.push({
                                    tag: o.tagName,
                                    text: directText,
                                    x: r.x + r.width/2, y: r.y + r.height/2,
                                });
                            }
                        }
                    }
                    const seen = new Set();
                    return results.filter(r => {
                        if (seen.has(r.text)) return false;
                        seen.add(r.text); return true;
                    }).slice(0, 5);
                }""")
                if zopt:
                    log.info("→ Zone options: %d", len(zopt))
                    for o in zopt:
                        log.info("  <%s> '%s' pos=(%.0f,%.0f)",
                                 o.get('tag',''), o.get('text','')[:30],
                                 o.get('x',0), o.get('y',0))
                    for o in zopt:
                        if "All zones" in o.get('text',''):
                            page.mouse.click(o['x'], o['y'])
                            zone_selected = True
                            log.info("✓ All zones dipilih")
                            break
                else:
                    log.warning("⚠ Option 'All zones' tidak ditemukan")
                    page.keyboard.press("Escape")
            else:
                log.warning("⚠ Dropdown Zone tidak ditemukan")
        except Exception as e:
            log.warning("⚠ Zone error: %s", str(e)[:100])

        time.sleep(1.0)

        # --- Step F: Cek error merah ---
        try:
            body = page.inner_text("body")
            if "Choose an account resource" in body:
                log.error("✗ Account Resources masih kosong!")
            if "Choose a zone resource" in body:
                log.error("✗ Zone Resources masih kosong!")
            if "Choose a permission" in body:
                log.warning("⚠ Permission error (seharusnya pre-filled dari template)")
        except Exception:
            pass

        # --- DEBUG: dump semua dropdown posisi & screenshot ---
        try:
            debug_dir = os.path.join(
                os.path.dirname(__file__), "..", "debug"
            )
            os.makedirs(debug_dir, exist_ok=True)
            page.screenshot(path=os.path.join(debug_dir, "before_summary.png"))

            # Dump semua combobox/select position
            dd = page.evaluate("""() => {
                const results = [];
                document.querySelectorAll('[role="combobox"], select, [aria-haspopup]').forEach(el => {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        results.push({
                            text: (el.textContent || '').trim().slice(0, 40),
                            tag: el.tagName,
                            role: el.getAttribute('role'),
                            popup: el.getAttribute('aria-haspopup'),
                            x: Math.round(rect.x), y: Math.round(rect.y),
                            w: Math.round(rect.width), h: Math.round(rect.height),
                        });
                    }
                });
                return results;
            }""")
            log.info("→ Dropdown positions:")
            for i, d in enumerate(dd):
                log.info("  [%d] '%s' <%s> popup=%s pos=(%d,%d) %dx%d",
                         i, d['text'][:30], d['tag'], d['popup'],
                         d['x'], d['y'], d['w'], d['h'])
        except Exception:
            pass

        time.sleep(1.0)

        # --- HARD GATE: jangan klik summary kalau Account Resources
        # belum terpilih — form akan tetap di halaman & token tidak muncul ---
        if not account_selected:
            try:
                body = page.inner_text("body")
                if "Choose an account resource" in body:
                    log.error("✗ Account Resources masih kosong - form belum valid")
            except Exception:
                pass
            # retry sekali: scroll ke 'Select...' lalu coba helper lagi
            try:
                page.evaluate("""() => {
                    const btns = Array.from(document.querySelectorAll(
                        'button[aria-haspopup="listbox"], [aria-haspopup="listbox"]'));
                    for (const b of btns) {
                        if ((b.textContent || '').trim() !== 'Select...') continue;
                        b.scrollIntoView({block: 'center'});
                        return true;
                    }
                    return false;
                }""")
                time.sleep(1.5)
                if _click_account_option(page, self.email):
                    account_selected = True
                    log.info("✓ Retry Account Resources berhasil")
            except Exception as e:
                log.warning("⚠ Retry account gagal: %s", str(e)[:80])

        if not account_selected:
            log.error("✗ Gagal pilih Account Resources setelah retry - abort Module 5")
            return None

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
