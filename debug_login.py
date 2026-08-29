"""Debug login issue."""
import sys, os, time
sys.path.insert(0, '.')
sys.path.insert(0, 'cf-modules')
from camoufox.sync_api import Camoufox
from camoufox import DefaultAddons
from cf_helpers import log, dismiss_cookie_banner, extract_account_id_from_url, SEL_EMAIL, SEL_PASSWORD

CF_EMAIL = 'cfyoyf3o9b@renunganbot.qzz.io'
CF_PASSWORD = 'ap$u6Vut2OM#3p'

logging_check = False
import logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s', datefmt='%H:%M:%S')

with Camoufox(headless=False, humanize=True, disable_coop=True, exclude_addons=[DefaultAddons.UBO], i_know_what_im_doing=True) as browser:
    page = browser.new_page()
    page.set_default_timeout(30000)
    page.goto('https://dash.cloudflare.com/login', wait_until='domcontentloaded', timeout=60000)
    page.wait_for_timeout(3000)
    dismiss_cookie_banner(page)

    # Screenshot sebelum
    os.makedirs('debug', exist_ok=True)
    page.screenshot(path='debug/login_before.png')

    # Isi email
    email_ok = False
    for esel in SEL_EMAIL:
        try:
            el = page.wait_for_selector(esel, timeout=10000, state='visible')
            if el:
                el.click(timeout=3000)
                el.fill(CF_EMAIL, timeout=5000)
                email_ok = True
                log.info('✓ Email terisi (%s)', esel)
                break
        except Exception as e:
            log.debug('Email selector %s gagal: %s', esel, str(e)[:60])

    # Isi password
    pass_ok = False
    for psel in SEL_PASSWORD:
        try:
            el = page.wait_for_selector(psel, timeout=10000, state='visible')
            if el:
                el.click(timeout=3000)
                el.fill(CF_PASSWORD, timeout=5000)
                pass_ok = True
                log.info('✓ Password terisi (%s)', psel)
                break
        except Exception as e:
            log.debug('Password selector %s gagal: %s', psel, str(e)[:60])

    # Cek isi field
    actual_email = page.evaluate('() => document.querySelector("input[name=email], input[type=email]")?.value || ""')
    actual_pass = page.evaluate('() => document.querySelector("input[name=password], input[type=password]")?.value || ""')
    log.info('Email field value: "%s"', actual_email)
    log.info('Password field value: "%s" (%d chars)', actual_pass[:3] + '***', len(actual_pass))

    # Screenshot setelah isi
    page.screenshot(path='debug/login_after_fill.png')

    # Klik login
    page.wait_for_timeout(1000)
    for bsel in ['button:has-text("Continue with password")',
                 'button:has-text("Sign in")',
                 'button:has-text("Continue")',
                 'button[type="submit"]']:
        try:
            el = page.wait_for_selector(bsel, timeout=5000, state='visible')
            if el:
                txt = el.text_content() or ''
                log.info('→ Tombol ditemukan: %s — text: "%s"', bsel, txt[:50])
                if 'sso' in txt.lower():
                    log.info('→ Skip SSO button')
                    continue
                el.click(force=True, timeout=5000)
                log.info('✓ Login diklik (%s)', bsel)
                break
        except Exception as e:
            log.debug('Tombol %s tidak ditemukan: %s', bsel, str(e)[:60])

    # Tunggu
    page.wait_for_timeout(8000)
    url = page.url
    log.info('URL setelah login: %s', url)

    # Screenshot hasil
    page.screenshot(path='debug/login_result.png')

    # Cek body
    body = page.inner_text('body')
    log.info('Body (300 char): %s', body[:300])

    aid = extract_account_id_from_url(url)
    if aid:
        log.info('✓✓✓ LOGIN BERHASIL! Account ID: %s', aid)
    else:
        log.error('✗ Login gagal — URL: %s', url)
