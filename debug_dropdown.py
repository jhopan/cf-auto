"""Debug: login + inspect DOM Create Token page."""
import sys, os, time, json
sys.path.insert(0, '.')
sys.path.insert(0, 'cf-modules')
from camoufox.sync_api import Camoufox
from camoufox import DefaultAddons
from cf_helpers import log, dismiss_cookie_banner, SEL_EMAIL, SEL_PASSWORD

CF_EMAIL = 'cfyoyf3o9b@renunganbot.qzz.io'
CF_PASSWORD = 'ap$u6Vut2OM#3p'

with Camoufox(headless=False, humanize=True, disable_coop=True, exclude_addons=[DefaultAddons.UBO], i_know_what_im_doing=True) as browser:
    page = browser.new_page()
    page.set_default_timeout(30000)

    # Login
    log.info("Login...")
    page.goto('https://dash.cloudflare.com/login', wait_until='domcontentloaded', timeout=60000)
    page.wait_for_timeout(3000)
    dismiss_cookie_banner(page)
    for esel in SEL_EMAIL:
        try:
            el = page.wait_for_selector(esel, timeout=10000, state='visible')
            if el: el.click(timeout=3000); el.fill(CF_EMAIL, timeout=5000); log.info("✓ Email"); break
        except Exception: continue
    for psel in SEL_PASSWORD:
        try:
            el = page.wait_for_selector(psel, timeout=10000, state='visible')
            if el: el.click(timeout=3000); el.fill(CF_PASSWORD, timeout=5000); log.info("✓ Password"); break
        except Exception: continue
    page.wait_for_timeout(1000)
    for bsel in ['button:has-text("Continue with password")','button:has-text("Sign in")','button:has-text("Continue")','button[type="submit"]']:
        try:
            el = page.wait_for_selector(bsel, timeout=5000, state='visible')
            if el:
                txt = el.text_content() or ""
                if "sso" in txt.lower(): continue
                el.click(force=True, timeout=5000)
                log.info("✓ Login diklik (%s)", bsel)
                break
        except Exception: continue
    page.wait_for_timeout(10000)
    log.info("URL: %s", page.url)

    # Navigasi ke API Tokens — retry karena NS_BINDING_ABORTED
    for attempt in range(3):
        try:
            page.goto('https://dash.cloudflare.com/profile/api-tokens', wait_until='domcontentloaded', timeout=60000)
            break
        except Exception as e:
            log.warning("⚠ Navigasi gagal (attempt %d): %s", attempt+1, str(e)[:60])
            page.wait_for_timeout(3000)
    page.wait_for_timeout(5000)
    log.info("URL: %s", page.url)

    # Klik Create Token — tunggu sampai benar-benar visible
    try:
        el = page.wait_for_selector('a:has-text("Create Token"), button:has-text("Create Token")', timeout=15000, state='visible')
        if el:
            el.click(force=True, timeout=10000)
            log.info("✓ Create Token diklik")
    except Exception as e:
        log.error("Create Token: %s", str(e)[:80])
        # Fallback: JS
        page.evaluate("""() => {
            const els = Array.from(document.querySelectorAll('a, button'));
            const btn = els.find(e => e.textContent.includes('Create Token'));
            if (btn) btn.click();
        }""")
        log.info("→ Create Token via JS")
    page.wait_for_timeout(3000)

    # Klik Use template "Edit Cloudflare Workers"
    try:
        el = page.wait_for_selector('tr:has-text("Edit Cloudflare Workers") button:has-text("Use template"), div:has-text("Edit Cloudflare Workers") button:has-text("Use template")', timeout=15000, state='visible')
        if el:
            el.click(force=True, timeout=10000)
            log.info("✓ Use template diklik")
    except Exception as e:
        log.error("Use template: %s", str(e)[:80])
        page.evaluate("""() => {
            const rows = document.querySelectorAll('tr, div, li');
            for (const row of rows) {
                if (row.textContent.includes('Edit Cloudflare Workers')) {
                    const btn = row.querySelector('button');
                    if (btn) { btn.click(); return; }
                }
            }
        }""")
        log.info("→ Use template via JS")
    page.wait_for_timeout(5000)

    # === INSPECT DOM ===
    log.info("=== INSPECT DOM CREATE TOKEN PAGE ===")

    # Dump semua element yang relevan: combobox, select, button, dll
    elements = page.evaluate("""() => {
        const results = [];
        const all = document.querySelectorAll('*');
        let idx = 0;
        for (const el of all) {
            const rect = el.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) continue;
            const tag = el.tagName;
            const role = el.getAttribute('role') || '';
            const cls = (el.className?.toString() || '').slice(0, 50);
            const txt = (el.textContent || '').trim().slice(0, 60);
            const id = el.id || '';
            const name = el.getAttribute('name') || '';
            const placeholder = el.getAttribute('placeholder') || '';
            const ariaHasPopup = el.getAttribute('aria-haspopup') || '';
            const ariaExpanded = el.getAttribute('aria-expanded') || '';
            // Filter: hanya yang relevan (dropdown, select, combobox, button, dll)
            if (role === 'combobox' || role === 'listbox' || role === 'option' ||
                tag === 'SELECT' || tag === 'BUTTON' ||
                cls.toLowerCase().includes('select') ||
                cls.toLowerCase().includes('dropdown') ||
                cls.toLowerCase().includes('combobox') ||
                ariaHasPopup === 'listbox' || ariaHasPopup === 'true' ||
                txt === 'Include' || txt === 'Select...' || txt === 'Specific zone' ||
                txt === 'Account Resources' || txt === 'Zone Resources' || txt === 'Permissions' ||
                txt === 'All zones' || txt === 'All accounts') {
                results.push({
                    idx: idx++,
                    tag, role, cls, txt: txt.slice(0, 40), id, name, placeholder,
                    ariaHasPopup, ariaExpanded,
                    x: Math.round(rect.x), y: Math.round(rect.y),
                    w: Math.round(rect.width), h: Math.round(rect.height),
                });
            }
        }
        return results;
    }""")

    log.info("Elements found: %d", len(elements))
    for e in elements:
        log.info("  [%d] <%s> role=%s cls='%s' text='%s' id=%s popup=%s pos=(%d,%d) %dx%d",
                 e['idx'], e['tag'], e['role'], e['cls'][:30], e['txt'][:30],
                 e['id'], e['ariaHasPopup'], e['x'], e['y'], e['w'], e['h'])

    # Screenshot
    os.makedirs('debug', exist_ok=True)
    page.screenshot(path='debug/create_token_inspect.png')
    log.info("Screenshot: debug/create_token_inspect.png")

    # Tunggu
    log.info("Selesai. Ctrl+C untuk keluar.")
    try:
        while True:
            page.wait_for_timeout(10000)
    except KeyboardInterrupt:
        pass
