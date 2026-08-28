"""
cf_workers_ai.py — Module 4: Ambil Workers AI API Token

Tanggung jawab:
  - Navigasi ke /{account_id}/ai/workers-ai/api-quick-start
  - Klik "Create a Workers AI API Token"
  - Modal muncul → ubah "Token name" jadi "jhopanstore"
  - Klik "Create API Token"
  - Copy token yang muncul (cfut_...)
  - Return token

TIDAK tanggung jawab:
  - Signup, verifikasi email, ambil Global API Key

Aturan:
  - Semua di tab yang sama (page utama)
"""
from __future__ import annotations
import re
import os
import time
import logging
from typing import Optional

from playwright.sync_api import Page

from .cf_helpers import (
    log,
    fill_input,
    wait_and_click,
    wait_for_turnstile,
    dismiss_cookie_banner,
)

__all__ = ["GetWorkersAiToken"]


class GetWorkersAiToken:
    """Module 4: Ambil Workers AI API Token."""

    def __init__(self, account_id: str):
        self.account_id = account_id

    def run(self, page: Page) -> Optional[str]:
        """Jalankan ambil Workers AI API Token.

        Returns:
            Token string (cfut_...) jika berhasil, None jika gagal.
        """
        log.info("═══ Module 4: Ambil Workers AI API Token ═══")

        # --- Step A: Navigasi ke Workers AI API quick start ---
        url = (
            f"https://dash.cloudflare.com/{self.account_id}"
            f"/ai/workers-ai/api-quick-start"
        )
        log.info("→ Navigasi ke: %s", url)
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        dismiss_cookie_banner(page)
        log.info("  URL: %s", page.url)

        # --- Step B: Klik "Create a Workers AI API Token" ---
        log.info("→ Cari tombol 'Create a Workers AI API Token'...")

        create_clicked = False
        for sel in [
            'button:has-text("Create a Workers AI API Token")',
            'button:has-text("Create API Token")',
            'a:has-text("Create a Workers AI API Token")',
            'a:has-text("Create API Token")',
        ]:
            try:
                el = page.wait_for_selector(sel, timeout=10000, state="visible")
                if el:
                    el.click(force=True, timeout=5000)
                    create_clicked = True
                    log.info("✓ Klik Create (%s)", sel)
                    break
            except Exception:
                continue

        if not create_clicked:
            # Fallback: cari via JS
            page.evaluate("""() => {
                const btns = Array.from(document.querySelectorAll('button, a'));
                const btn = btns.find(b =>
                    b.textContent.includes('Create') &&
                    b.textContent.includes('API Token')
                );
                if (btn) btn.click();
            }""")
            log.info("→ Klik Create via JS")

        page.wait_for_timeout(3000)

        # --- Step C: Modal "Create a Workers AI API Token" muncul ---
        # Ubah Token name jadi "jhopanstore"
        log.info("→ Isi Token name: jhopanstore")

        # Cari input "Token name" di modal
        token_name_filled = False
        for sel in [
            '[data-testid*="modal"] input[name="name"]',
            '[role="dialog"] input[name="name"]',
            '[data-testid*="modal"] input[placeholder*="Token"]',
            '[role="dialog"] input[placeholder*="Token"]',
            '[data-testid*="modal"] input[type="text"]:not([name="search"])',
            '[role="dialog"] input[type="text"]:not([name="search"])',
            'input[name="tokenName"]',
            'input[name="name"]',
        ]:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0 and loc.is_visible(timeout=3000):
                    # Clear dulu, lalu isi
                    loc.click(timeout=3000)
                    loc.fill("", timeout=2000)  # clear
                    loc.fill("jhopanstore", timeout=5000)
                    token_name_filled = True
                    log.info("✓ Token name diisi: jhopanstore (%s)", sel)
                    break
            except Exception:
                continue

        if not token_name_filled:
            # Fallback: keyboard type
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
                                inp.select();
                                return;
                            }
                        }
                    }
                }""")
                page.wait_for_timeout(500)
                # Clear existing text
                page.keyboard.press("Control+a")
                page.keyboard.press("Delete")
                page.keyboard.type("jhopanstore", delay=50)
                token_name_filled = True
                log.info("✓ Token name diketik: jhopanstore")
            except Exception:
                pass

        if not token_name_filled:
            log.error("✗ Tidak bisa mengisi Token name")
            return None

        page.wait_for_timeout(1000)

        # --- Step D: Klik "Create API Token" di modal ---
        log.info("→ Klik 'Create API Token' di modal...")

        create_token_clicked = False
        for sel in [
            'button:has-text("Create API Token")',
            'button:has-text("Create Token")',
            'button:has-text("Create")',
        ]:
            try:
                # Cari di dalam modal
                for modal_sel in [
                    '[data-testid*="modal"]',
                    '[role="dialog"]',
                    '[aria-modal="true"]',
                ]:
                    try:
                        loc = page.locator(
                            f'{modal_sel} >> {sel}'
                        ).first
                        if loc.count() > 0:
                            loc.click(force=True, timeout=5000)
                            create_token_clicked = True
                            log.info("✓ Klik Create API Token (%s)", sel)
                            break
                    except Exception:
                        continue
                if create_token_clicked:
                    break
            except Exception:
                continue

        if not create_token_clicked:
            # Fallback: cari semua tombol Create
            try:
                btns = page.locator('button:has-text("Create")')
                cnt = btns.count()
                if cnt > 0:
                    btns.last.click(force=True, timeout=5000)
                    create_token_clicked = True
                    log.info("→ Klik Create (terakhir, %d total)", cnt)
            except Exception:
                pass

        if not create_token_clicked:
            page.evaluate("""() => {
                const m = document.querySelector(
                    '[data-testid*="modal"], [role="dialog"]'
                );
                if (m) {
                    const b = Array.from(m.querySelectorAll('button'))
                        .find(b => b.textContent.includes('Create'));
                    if (b) b.click();
                }
            }""")
            log.info("→ Klik Create via JS")

        # --- Step E: Tunggu halaman token muncul ---
        # Cloudflare akan tampilkan: "API Token Created" + token string
        log.info("→ Menunggu token muncul...")
        page.wait_for_timeout(5000)

        # Tunggu teks "API Token Created" atau "Copy" muncul
        token = None
        deadline = time.time() + 30
        while time.time() < deadline:
            page.wait_for_timeout(1000)
            token = self._extract_token(page)
            if token:
                break

        if not token:
            log.error("✗ Workers AI API Token tidak ditemukan")
            # Debug
            try:
                debug_dir = os.path.join(
                    os.path.dirname(__file__), "..", "debug"
                )
                os.makedirs(debug_dir, exist_ok=True)
                page.screenshot(
                    path=os.path.join(debug_dir, "workers_ai_token.png")
                )
                body = page.inner_text("body")
                log.info("→ Body: %s", body[:300])
            except Exception:
                pass
            return None

        log.info(
            "✓✓✓ Workers AI API Token: %s ✓✓✓",
            token[:12] + "..." + token[-4:],
        )

        # --- Step F: Klik "Copy API Token" (opsional, untuk konfirmasi) ---
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
        """Ekstrak Workers AI API Token dari halaman.

        Format token: cfut_... (Cloudflare User Token)
        """
        # 1. Cari di input, code, pre, span, div
        try:
            results = page.evaluate("""() => {
                const results = [];
                const sels = 'input, code, pre, .font-mono, span, div, p, textarea';
                document.querySelectorAll(sels).forEach(el => {
                    const v = (el.value || el.textContent || '').trim();
                    // cfut_ prefix (Workers AI API Token)
                    if (v.match(/^cfut_[A-Za-z0-9]+$/)) results.push(v);
                    // Fallback: string alfanumerik 40-60 char
                    if (v.match(/^[A-Za-z0-9_-]{40,60}$/) && v.length < 100)
                        results.push(v);
                });
                return results;
            }""")
            if results:
                return results[0]
        except Exception:
            pass

        # 2. Cari di body text
        try:
            body_text = page.inner_text("body")
            # cfut_ pattern
            m = re.search(r"(cfut_[A-Za-z0-9]+)", body_text)
            if m:
                return m.group(1)
            # Fallback: string 40-60 char
            m = re.search(r"\b([A-Za-z0-9_-]{40,60})\b", body_text)
            if m:
                return m.group(1)
        except Exception:
            pass

        return None
