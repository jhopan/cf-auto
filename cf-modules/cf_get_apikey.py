"""
cf_get_apikey.py — Module 3: Ambil Global API Key

Tanggung jawab:
  - Navigasi ke profile/api-tokens
  - Klik View di Global API Key (tombol pertama)
  - Klik "Send Verification Code" di modal "Verify Your Identity"
  - Tunggu email kode 7-digit di temp mail
  - Input kode ke modal "Your API Key" (pakai Playwright fill, bukan JS)
  - Solve Turnstile di modal
  - Klik View di DALAM modal (bukan View di baris Global API Key)
  - Tunggu API key muncul, ekstrak & return

TIDAK tanggung jawab:
  - Signup
  - Verifikasi email
"""
from __future__ import annotations
import re
import os
import time
import json
import logging
from typing import Optional

from playwright.sync_api import Page

from cf_helpers import (
    log,
    API_TOKENS_URL,
    SEL_PASSWORD,
    fill_input,
    wait_and_click,
    wait_for_turnstile,
    dismiss_cookie_banner,
)

__all__ = ["GetApiKey"]


class GetApiKey:
    """Module 3: Ambil Global API Key."""

    def __init__(self, email: str, password: str, mail_client):
        """
        Args:
            email: Email Cloudflare
            password: Password Cloudflare
            mail_client: Instance TempMailAdapter (wait_for_email, delete_inbox)
        """
        self.email = email
        self.password = password
        self.mail = mail_client

    def run(self, page: Page) -> Optional[str]:
        """Jalankan ambil API key flow.

        Returns:
            API key string jika berhasil, None jika gagal.
        """
        log.info("═══ Module 3: Ambil Global API Key ═══")

        # --- Step A: Navigasi ke API Tokens ---
        for attempt in range(3):
            try:
                page.goto(
                    API_TOKENS_URL,
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
                break
            except Exception as e:
                log.warning("⚠ Navigasi gagal (attempt %d): %s", attempt + 1, str(e)[:60])
                time.sleep(3)
        time.sleep(5.0)
        dismiss_cookie_banner(page)
        log.info("  URL: %s", page.url)

        # --- Step B: Klik View di Global API Key (tombol pertama) ---
        page.evaluate(
            "window.scrollTo(0, document.body.scrollHeight)"
        )
        time.sleep(2.0)

        wait_and_click(
            page,
            [
                'button:has-text("View")',
                'a:has-text("View")',
            ],
            timeout=15000, force=True,
        )
        time.sleep(3.0)

        # --- Step C: Modal "Verify Your Identity" → Send Verification Code ---
        log.info("→ Menunggu modal 'Verify Your Identity'...")
        wait_and_click(
            page,
            [
                'button:has-text("Send Verification Code")',
                'button:has-text("Send")',
            ],
            timeout=15000, force=True,
        )
        time.sleep(3.0)
        log.info("✓ Verification code dikirim ke email")

        # --- Step D: Tunggu email kode 7-digit ---
        # Hapus inbox lama dulu agar dapat email baru
        self.mail.delete_inbox(self.email)
        log.info("✓ Inbox lama dibersihkan")
        time.sleep(2.0)

        log.info("→ Menunggu email kode verifikasi...")
        code_msg = self.mail.wait_for_email(self.email, timeout=120)

        # Ekstrak kode 7-digit
        codes = code_msg.get("codes", [])
        code = codes[0] if codes else None
        if not code:
            text = code_msg.get("text_body", "")
            m = re.search(r"\b(\d{7})\b", text)
            code = m.group(1) if m else None
        if not code:
            log.error("✗ Kode 7-digit tidak ditemukan")
            log.info("  Codes: %s", codes)
            log.info(
                "  Text: %s",
                code_msg.get("text_body", "")[:200],
            )
            return None

        log.info("✓ Kode verifikasi: %s", code)

        # --- Step E: Input kode ke modal "Your API Key" ---
        log.info("→ Input kode ke modal...")

        # Tunggu modal muncul
        modal_found = False
        for modal_sel in [
            '[data-testid*="modal"]',
            '[role="dialog"]',
            '[aria-modal="true"]',
            '.modal',
            '[class*="modal"]',
            '[class*="Modal"]',
        ]:
            try:
                page.wait_for_selector(
                    modal_sel, timeout=10000, state="visible"
                )
                log.info("✓ Modal terdeteksi: %s", modal_sel)
                modal_found = True
                break
            except Exception:
                continue

        if not modal_found:
            log.warning("⚠ Modal tidak terdeteksi via selector")

        # Isi kode via Playwright fill (BUKAN JS el.value!)
        # React controlled components butuh simulasi keyboard
        code_filled = False
        for sel in [
            '[data-testid*="modal"] input[name="code"]',
            '[role="dialog"] input[name="code"]',
            '[aria-modal="true"] input[name="code"]',
            '.modal input[name="code"]',
            'input[name="code"]',
            '[data-testid*="modal"] input[placeholder*="code" i]',
            '[role="dialog"] input[placeholder*="Verify" i]',
            '[data-testid*="modal"] input[type="text"]:not([name="search"])',
            '[role="dialog"] input[type="text"]:not([name="search"])',
        ]:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0 and loc.is_visible(timeout=3000):
                    loc.click(timeout=3000)
                    loc.fill(code, timeout=5000)
                    code_filled = True
                    log.info("✓ Kode dimasukkan (%s)", sel)
                    break
            except Exception:
                continue

        # Fallback: keyboard type
        if not code_filled:
            try:
                page.evaluate("""() => {
                    const modal = document.querySelector(
                        '[data-testid*="modal"], [role="dialog"]'
                    );
                    if (modal) {
                        const inputs = modal.querySelectorAll(
                            'input[type="text"], input:not([type])'
                        );
                        for (const inp of inputs) {
                            if (!inp.name?.includes('search')
                                && !inp.id?.includes('search')) {
                                inp.focus();
                                return;
                            }
                        }
                    }
                }""")
                time.sleep(0.5)
                page.keyboard.type(code, delay=50)
                code_filled = True
                log.info("✓ Kode diketik via keyboard")
            except Exception:
                pass

        if not code_filled:
            log.error("✗ Tidak bisa mengisi kode ke modal!")
            return None

        time.sleep(1.0)

        # --- Step F: Solve Turnstile di modal ---
        solved = wait_for_turnstile(page, timeout=90)
        if not solved:
            log.warning("⚠ Turnstile modal belum solved, tunggu manual...")
            try:
                page.wait_for_function(
                    """() => {
                        const el = document.querySelector(
                            'input[name="cf_challenge_response"]'
                        );
                        return el && el.value && el.value.length > 20;
                    }""",
                    timeout=60000,
                )
                log.info("✓ Turnstile solved (manual)")
            except Exception:
                log.error("✗ Turnstile modal tidak solved")
                return None

        # --- Step G: Klik View di DALAM modal ---
        # PENTING: pakai page.locator (bukan query_selector) karena
        # :has-text() hanya support di locator, bukan CSS selector
        log.info("→ Klik View di dalam modal...")
        time.sleep(1.0)
        view_clicked = False

        for modal_sel in [
            '[data-testid*="modal"]',
            '[role="dialog"]',
            '[aria-modal="true"]',
            '.modal',
        ]:
            try:
                loc = page.locator(
                    f'{modal_sel} >> button:has-text("View")'
                ).first
                if loc.count() > 0:
                    loc.click(force=True, timeout=5000)
                    view_clicked = True
                    log.info("✓ Klik View di modal (%s)", modal_sel)
                    break
            except Exception:
                continue

        # Fallback 1: cari semua tombol View, klik terakhir
        if not view_clicked:
            try:
                btns = page.locator('button:has-text("View")')
                cnt = btns.count()
                if cnt > 1:
                    btns.nth(cnt - 1).click(force=True, timeout=5000)
                    view_clicked = True
                    log.info(
                        "✓ Klik View terakhir (modal, %d total)", cnt
                    )
                elif cnt == 1:
                    btns.first.click(force=True, timeout=5000)
                    view_clicked = True
                    log.info("→ Klik View (1 ditemukan)")
            except Exception:
                pass

        # Fallback 2: JS evaluate
        if not view_clicked:
            page.evaluate("""() => {
                const m = document.querySelector(
                    '[data-testid*="modal"], [role="dialog"]'
                );
                if (m) {
                    const b = Array.from(m.querySelectorAll('button'))
                        .find(b => b.textContent.includes('View'));
                    if (b) b.click();
                }
            }""")
            log.info("→ Klik View via JS")

        # --- Step H: Tunggu API key muncul ---
        log.info("→ Menunggu API key muncul...")
        api_key = None
        deadline = time.time() + 30
        while time.time() < deadline:
            time.sleep(0.5)
            api_key = self._extract_api_key(page)
            if api_key:
                break

        if not api_key:
            log.error("✗ Global API Key tidak ditemukan")
            # Debug
            try:
                debug_dir = os.path.join(
                    os.path.dirname(__file__), "..", "debug"
                )
                os.makedirs(debug_dir, exist_ok=True)
                page.screenshot(
                    path=os.path.join(debug_dir, "apikey_not_found.png")
                )
                body = page.inner_text("body")
                log.info("→ Body: %s", body[:300])
            except Exception:
                pass
            return None

        log.info(
            "✓✓✓ Global API Key: %s ✓✓✓",
            api_key[:8] + "..." + api_key[-4:],
        )
        return api_key

    def _extract_api_key(self, page: Page) -> Optional[str]:
        """Ekstrak API key dari halaman/modal.

        Cloudflare Global API Key format:
        - Hex 37 char (format lama)
        - cfx_tk_... atau cfk_... (format baru)
        """
        try:
            results = page.evaluate("""() => {
                const results = [];
                const sels = 'input, code, pre, .font-mono, span, div, p, textarea';
                document.querySelectorAll(sels).forEach(el => {
                    const v = (el.value || el.textContent || '').trim();
                    if (v.match(/^[a-f0-9]{37}$/)) results.push(v);
                    if (v.match(/^cf[xk]_[A-Za-z0-9]+$/)) results.push(v);
                    if (v.match(/^[A-Za-z0-9_-]{40,60}$/) && v.length < 100)
                        results.push(v);
                });
                return results;
            }""")
            if results:
                return results[0]
        except Exception:
            pass

        # Fallback: regex di body text
        try:
            body_text = page.inner_text("body")
            m = re.search(r"\b([a-f0-9]{37})\b", body_text)
            if m:
                return m.group(1)
            m = re.search(r"(cf[xk]_[A-Za-z0-9]+)", body_text)
            if m:
                return m.group(1)
            m = re.search(r"\b([A-Za-z0-9_-]{40,60})\b", body_text)
            if m:
                return m.group(1)
        except Exception:
            pass

        return None
