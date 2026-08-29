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
                page.wait_for_timeout(3000)
        page.wait_for_timeout(5000)
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

        page.wait_for_timeout(3000)

        # --- Step C: Cari template "Edit Cloudflare Workers" → klik "Use template" ---
        log.info("→ Cari template 'Edit Cloudflare Workers'...")

        template_clicked = False

        # Cloudflare render template sebagai div/row, bukan <tr>
        # Cari baris yang berisi TEKS PERSIS "Edit Cloudflare Workers"
        # lalu klik tombol "Use template" DI DALAM baris itu
        for sel in [
            # Cari elemen yang text-nya persis "Edit Cloudflare Workers"
            # lalu cari button "Use template" di parent/sibling-nya
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

        if not template_clicked:
            # Fallback: cari via JS — CARI PERSIS "Edit Cloudflare Workers"
            # JANGAN ambil button pertama! Cari row yang text-nya match
            result = page.evaluate("""() => {
                // Cari semua elemen yang mengandung "Use template"
                const btns = Array.from(
                    document.querySelectorAll('button, a')
                ).filter(b => b.textContent.includes('Use template'));

                for (const btn of btns) {
                    // Cari parent container (row/card)
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

        if not template_clicked:
            log.error("✗ Template 'Edit Cloudflare Workers' tidak ditemukan!")

        try:
            page.wait_for_timeout(3000)
        except Exception:
            pass

        print(">>> DEBUG: before Step D", flush=True)
        # --- Step D: Account Resources → pilih akun ---
        log.info("→ Setting Account Resources...")
        account_selected = False

        # Pakai JS untuk cari & klik react-select control
        # lalu cari option dan klik via page.mouse.click()
        try:
            # Step 1: Klik control "Select..." di Account Resources
            ctrl_pos = page.evaluate("""() => {
                // Cari semua react-select control
                const controls = document.querySelectorAll(
                    'div[class*="react-select__control"], div[class*="control"]'
                );
                for (const ctrl of controls) {
                    if (ctrl.textContent.includes('Select...')) {
                        // Cek parent: Account Resources
                        let p = ctrl;
                        for (let j = 0; j < 15; j++) {
                            p = p.parentElement;
                            if (!p) break;
                            const txt = p.textContent || '';
                            if (txt.includes('Account Resources') &&
                                !txt.includes('Zone Resources')) {
                                const rect = ctrl.getBoundingClientRect();
                                return {
                                    x: rect.x + rect.width / 2,
                                    y: rect.y + rect.height / 2,
                                };
                            }
                        }
                    }
                }
                return null;
            }""")
            if ctrl_pos:
                log.info("→ Klik control Account di (%.0f, %.0f)", ctrl_pos['x'], ctrl_pos['y'])
                page.mouse.click(ctrl_pos['x'], ctrl_pos['y'])
                page.wait_for_timeout(2000)

                # Step 2: Cari option yang berisi email akun
                email_prefix = self.email.split("@")[0]
                opt_pos = page.evaluate(f"""() => {{
                    // Cari semua option di menu yang terbuka
                    const opts = document.querySelectorAll(
                        'div[class*="react-select__option"], [role="option"], li'
                    );
                    for (const opt of opts) {{
                        const txt = opt.textContent || '';
                        if (txt.includes('{email_prefix}') ||
                            (txt.includes("Account") && !txt.includes("All accounts"))) {{
                            const rect = opt.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0) {{
                                return {{
                                    x: rect.x + rect.width / 2,
                                    y: rect.y + rect.height / 2,
                                    text: txt.trim().slice(0, 50),
                                }};
                            }}
                        }}
                    }}
                    return null;
                }}""")
                if opt_pos:
                    log.info("→ Klik option akun di (%.0f, %.0f): %s",
                             opt_pos['x'], opt_pos['y'], opt_pos['text'])
                    page.mouse.click(opt_pos['x'], opt_pos['y'])
                    account_selected = True
                    log.info("✓ Akun dipilih")
                else:
                    log.warning("⚠ Option akun tidak ditemukan di menu")
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(500)
            else:
                log.warning("⚠ Control Account tidak ditemukan")
        except Exception as e:
            log.warning("⚠ Account error: %s", str(e)[:100])

        if not account_selected:
            log.warning("⚠ Account Resources tidak terpilih")

        page.wait_for_timeout(1000)

        # --- Step E: Zone Resources → "Specific zone" → "All zones" ---
        log.info("→ Setting Zone Resources (All zones)...")
        zone_selected = False

        try:
            # Step 1: Klik control "Specific zone" di Zone Resources
            zctrl_pos = page.evaluate("""() => {
                const controls = document.querySelectorAll(
                    'div[class*="react-select__control"], div[class*="control"]'
                );
                for (const ctrl of controls) {
                    if (ctrl.textContent.includes('Specific zone')) {
                        let p = ctrl;
                        for (let j = 0; j < 15; j++) {
                            p = p.parentElement;
                            if (!p) break;
                            if (p.textContent.includes('Zone Resources')) {
                                const rect = ctrl.getBoundingClientRect();
                                return {
                                    x: rect.x + rect.width / 2,
                                    y: rect.y + rect.height / 2,
                                };
                            }
                        }
                    }
                }
                return null;
            }""")
            if zctrl_pos:
                log.info("→ Klik control Zone di (%.0f, %.0f)", zctrl_pos['x'], zctrl_pos['y'])
                page.mouse.click(zctrl_pos['x'], zctrl_pos['y'])
                page.wait_for_timeout(2000)

                # Step 2: Cari option "All zones"
                zopt_pos = page.evaluate("""() => {
                    const opts = document.querySelectorAll(
                        'div[class*="react-select__option"], [role="option"], li'
                    );
                    for (const opt of opts) {
                        if (opt.textContent.includes('All zones')) {
                            const rect = opt.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0) {
                                return {
                                    x: rect.x + rect.width / 2,
                                    y: rect.y + rect.height / 2,
                                };
                            }
                        }
                    }
                    return null;
                }""")
                if zopt_pos:
                    log.info("→ Klik option 'All zones' di (%.0f, %.0f)",
                             zopt_pos['x'], zopt_pos['y'])
                    page.mouse.click(zopt_pos['x'], zopt_pos['y'])
                    zone_selected = True
                    log.info("✓ All zones dipilih")
                else:
                    log.warning("⚠ Option 'All zones' tidak ditemukan")
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(500)
            else:
                log.warning("⚠ Control Zone tidak ditemukan")
        except Exception as e:
            log.warning("⚠ Zone error: %s", str(e)[:100])

        if not zone_selected:
            log.warning("⚠ Zone Resources tidak terpilih")

        page.wait_for_timeout(1000)

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

        page.wait_for_timeout(1000)

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

        page.wait_for_timeout(3000)

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
        page.wait_for_timeout(5000)

        token = None
        deadline = time.time() + 30
        while time.time() < deadline:
            page.wait_for_timeout(1000)
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
