"""
menucfauto.py — Menu interaktif untuk mengatur config cf-auto.

Meniru pola menutempmail: menu pilihan, prompt input, simpan ke config.json.
Digunakan untuk atur endpoint temp mail, domain, password, browser, storage.

Jalankan: python menucfauto.py
"""
import json
import os
import sys

from cf_config import load_config, save_config, load_accounts

CLEAR = "cls" if os.name == "nt" else "clear"


def clear():
    os.system(CLEAR)


def divider():
    print("=" * 52)


def ask(prompt, default=None, validator=None):
    """Prompt input dengan default (string). Validator => fungsi str->bool."""
    while True:
        hint = f" [{default}]" if default is not None else ""
        val = input(f"  {prompt}{hint}: ").strip()
        if val == "" and default is not None:
            val = default
        if validator:
            try:
                if not validator(val):
                    print("  ❌ Input tidak valid. Coba lagi.")
                    continue
            except Exception:
                print("  ❌ Input tidak valid. Coba lagi.")
                continue
        return val


def ask_int(prompt, default, min_v=0, max_v=10**9):
    while True:
        s = ask(prompt, str(default))
        try:
            n = int(s)
            if min_v <= n <= max_v:
                return n
            print(f"  ❌ Harus antara {min_v} dan {max_v}.")
        except ValueError:
            print("  ❌ Harus angka.")


def ask_bool(prompt, default):
    d = "y/n"
    s = ask(prompt, "y" if default else "n").lower()
    return s in ("y", "yes", "1", "true", "ya")


def ask_domains(current):
    print("  (masukkan tiap domain, Enter untuk selesai)")
    domains = []
    if current:
        print(f"  Domain sekarang: {', '.join(current)}")
    while True:
        d = input("    domain> ").strip()
        if d == "":
            break
        domains.append(d)
    return domains or current


def show_config(cfg):
    divider()
    print("CONFIG CFAUTO")
    divider()
    print(f"Temp Mail")
    print(f"  Base URL   : {cfg['temp_mail']['base_url']}")
    print(f"  API Key    : {cfg['temp_mail']['api_key'][:12]}... (disembunyikan)" if cfg['temp_mail']['api_key'] else "  API Key    : (kosong)")
    print(f"  Domains    : {', '.join(cfg['temp_mail']['domains'])}")
    print(f"  Prefix     : {cfg['temp_mail']['prefix']}")
    print(f"  Email Fmt  : {cfg['temp_mail'].get('email_format', '{prefix}{rand8}')}")
    print(f"Password")
    print(f"  Mode       : {cfg['password']['mode']}")
    if cfg['password']['mode'] == 'fixed':
        print(f"  Fixed      : {cfg['password']['fixed']}")
    else:
        print(f"  Length     : {cfg['password']['length']}")
    print(f"Browser")
    print(f"  Headless   : {cfg['browser']['headless']}")
    print(f"  Proxy      : {cfg['browser']['proxy'] or '(tidak ada)'}")
    print(f"Storage")
    print(f"  File JSON    : {cfg['storage']['accounts_file']}")
    print(f"  File CSV     : {cfg['storage'].get('csv_file', 'accounts.csv')}")
    print(f"  File WAI     : {cfg['storage'].get('workers_ai_file', 'workers_ai.txt')}")
    print(f"  WAI Format   : {cfg['storage'].get('workers_ai_format', '{name}|{apiKey}|{accountId}')}")
    print(f"  CSV Aktif    : {cfg['storage'].get('csv_enabled', True)}")
    print(f"  WAI Aktif    : {cfg['storage'].get('workers_ai_enabled', True)}")
    print(f"  Append       : {cfg['storage']['append']}")
    print(f"  Dedupe       : {cfg['storage'].get('dedupe_field', 'email')}")


def menu_tmpmail(cfg):
    print("\n  SETUP TEMP MAIL")
    divider()
    tm = cfg["temp_mail"]
    tm["base_url"] = ask("Base URL endpoint", tm["base_url"]).rstrip("/")
    tm["api_key"] = ask("API Key (kosongkan jika tidak perlu)", tm["api_key"])
    tm["domains"] = ask_domains(tm["domains"])
    tm["prefix"] = ask("Prefix username", tm["prefix"])
    print("  Format username email (placeholder: {prefix} {rand8} {rand6} {randnum})")
    tm["email_format"] = ask("email_format", tm.get("email_format", "{prefix}{rand8}"))
    save_config(cfg)
    print("  ✅ Config temp mail disimpan.")


def menu_password(cfg):
    print("\n  SETUP PASSWORD")
    divider()
    pw = cfg["password"]
    print("  Mode:")
    print("    random = acak tiap akun")
    print("    fixed  = pakai password tetap")
    pw["mode"] = ask("Mode (random/fixed)", pw["mode"]).lower()
    if pw["mode"] == "fixed":
        pw["fixed"] = ask("Password tetap", pw["fixed"])
        pw["length"] = len(pw["fixed"])
    else:
        pw["length"] = ask_int("Panjang password", pw["length"], min_v=8)
        pw["fixed"] = ""
    save_config(cfg)
    print("  ✅ Config password disimpan.")


def menu_browser(cfg):
    print("\n  SETUP BROWSER")
    divider()
    br = cfg["browser"]
    br["headless"] = ask_bool("Headless (tidak disarankan di Windows)", br["headless"])
    br["proxy"] = ask("Proxy (kosongkan jika tidak ada)", br["proxy"])
    save_config(cfg)
    print("  ✅ Config browser disimpan.")


def menu_storage(cfg):
    print("\n  SETUP STORAGE (3 format output)")
    divider()
    st = cfg["storage"]
    print("  Format yang tersedia:")
    print("    1. JSON  (accounts.json)  — semua field lengkap")
    print("    2. CSV   (accounts.csv)   — spreadsheet, semua kolom")
    print("    3. WAI   (workers_ai.txt) — name|apiKey|accountId per baris")
    print()
    st["accounts_file"] = ask("File JSON penyimpanan akun", st["accounts_file"])
    st["csv_file"] = ask("File CSV penyimpanan akun", st.get("csv_file", "accounts.csv"))
    st["workers_ai_file"] = ask("File Workers AI (.txt)", st.get("workers_ai_file", "workers_ai.txt"))
    print("  Format Workers AI (placeholder: {name} {apiKey} {accountId})")
    st["workers_ai_format"] = ask("Format WAI", st.get("workers_ai_format", "{name}|{apiKey}|{accountId}"))
    st["csv_enabled"] = ask_bool("Simpan ke CSV", st.get("csv_enabled", True))
    st["workers_ai_enabled"] = ask_bool("Simpan ke Workers AI txt", st.get("workers_ai_enabled", True))
    st["append"] = ask_bool("Append (tidak menimpa akun lama)", st["append"])
    st["dedupe_field"] = ask("Field untuk cek duplikat", st.get("dedupe_field", "email"))
    save_config(cfg)
    print("  ✅ Config storage disimpan.")


def menu_run(cfg):
    print("\n  JALANKAN RUNNER")
    divider()
    mode = cf_password_mode(cfg)
    print(f"  Akan buat 1 akun, password mode: {mode}")
    if not ask_bool("Lanjutkan?", True):
        return
    from runner import main as runner_main
    # runner baca config sendiri dari config.json (sudah disimpan)
    runner_main()


def cf_password_mode(cfg):
    return "fixed" if cfg["password"]["mode"] == "fixed" else "random"


def main():
    cfg = load_config()
    while True:
        clear()
        divider()
        print("       MENU CFAUTO")
        divider()
        print("  1. Lihat config sekarang")
        print("  2. Atur Temp Mail (endpoint/domain/key)")
        print("  3. Atur Password")
        print("  4. Atur Browser")
        print("  5. Atur Storage (file akun)")
        print("  6. Lihat akun tersimpan")
        print("  7. Jalankan runner.py (1 akun)")
        print("  8. Keluar")
        divider()
        choice = input("  Pilih [1-8]: ").strip()

        if choice == "1":
            clear()
            show_config(cfg)
            input("  Tekan Enter untuk kembali...")
        elif choice == "2":
            menu_tmpmail(cfg)
            cfg = load_config()
        elif choice == "3":
            menu_password(cfg)
            cfg = load_config()
        elif choice == "4":
            menu_browser(cfg)
            cfg = load_config()
        elif choice == "5":
            menu_storage(cfg)
            cfg = load_config()
        elif choice == "6":
            clear()
            accounts = load_accounts(cfg)
            divider()
            print(f"AKUN TERSIMPAN ({len(accounts)})")
            divider()
            if not accounts:
                print("  (belum ada akun)")
            for i, a in enumerate(accounts, 1):
                print(f"  {i}. {a.get('email')}  {a.get('created_at','')}")
            input("  Tekan Enter untuk kembali...")
        elif choice == "7":
            menu_run(cfg)
        elif choice == "8":
            print("  👋 Sampai jumpa!")
            break
        else:
            print("  ❌ Pilihan tidak valid.")


if __name__ == "__main__":
    main()
