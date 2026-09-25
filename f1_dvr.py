#!/usr/bin/env python3
"""
F1 Race Live DVR Engine (Zero LLM Tokens)
Records live race broadcast from HLS stream (Eleven Sports 1 PL with ServusTV fallback)
directly to VPS disk using ffmpeg in lossless stream-copy mode.
Notifies via Telegram when recording starts and when completed with direct VLC/download link.
"""

import os
import sys
import time
import subprocess
import argparse
import urllib.request
import urllib.error
import json
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Target output directory
DOWNLOADS_DIR = "/docker/hermes-agent-umxh/data/projects/mission-control/static/downloads"
if not os.path.exists(DOWNLOADS_DIR):
    # Fallback to local path when running on local Mac
    DOWNLOADS_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "mission-control", "static", "downloads"))
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)

DEFAULT_FILENAME = "f1_azerbaijan_gp_2026.mp4"
DEFAULT_TARGET = os.path.join(DOWNLOADS_DIR, DEFAULT_FILENAME)

PRIMARY_STREAM = "http://9b129915.akadatel.com/iptv/83GA6FAV4DPTPQ/20068/index.m3u8"
FALLBACK_STREAM = "https://rbmn-live.akamaized.net/hls/live/2002825/geoSTVATweb/master.m3u8"

DOWNLOAD_BASE_URL = "https://mission.srv1986482.hstgr.cloud/downloads"
AUTH_TOKEN = "ariel-m2-studio-2026"
DEFAULT_CHAT_ID = "8929130284"

ENV_PATHS = [
    "/docker/hermes-agent-umxh/data/.env",
    "/opt/data/.env",
    os.path.expanduser("~/.env"),
    os.path.join(BASE_DIR, ".env")
]

def get_telegram_token():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if token:
        return token.strip("\"'")
    for p in ENV_PATHS:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("TELEGRAM_BOT_TOKEN="):
                            return line.split("=", 1)[1].strip("\"' \n\r")
            except Exception:
                pass
    return None

def send_alert(message: str, chat_id: str = DEFAULT_CHAT_ID) -> bool:
    token = get_telegram_token()
    if not token:
        print("[WARN] Brak TELEGRAM_BOT_TOKEN, pomijam powiadomienie Telegram.")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[ERROR] Błąd wysyłania alertu na Telegram: {e}", file=sys.stderr)
        return False

def test_stream_alive(url: str, timeout: int = 5) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False

def record_stream(url: str, output_path: str, duration_sec: int) -> bool:
    """Executes ffmpeg in stream copy mode for HLS live streams."""
    cmd = [
        "ffmpeg",
        "-user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "-i", url,
        "-c", "copy",
        "-bsf:a", "aac_adtstoasc",
        "-t", str(duration_sec),
        "-y",
        output_path
    ]
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Odpalam ffmpeg dla {duration_sec}s...")
    try:
        proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=duration_sec + 30)
        return os.path.exists(output_path) and os.path.getsize(output_path) > 100 * 1024
    except subprocess.TimeoutExpired:
        print("[INFO] Nagrywanie zakończone po upływie zaplanowanego czasu.")
        return os.path.exists(output_path) and os.path.getsize(output_path) > 100 * 1024
    except Exception as e:
        print(f"[ERROR] Błąd uruchamiania ffmpeg: {e}", file=sys.stderr)
        return False

def run_dvr(duration_sec: int = 8400, force_stream: str = None, send_alerts: bool = True, output_file: str = None):
    target = output_file or DEFAULT_TARGET
    target_filename = os.path.basename(target)
    download_url = f"{DOWNLOAD_BASE_URL}/{target_filename}?token={AUTH_TOKEN}"

    print(f"==================================================")
    print(f"🏎️ F1 LIVE DVR RECORDER START")
    print(f"Czas nagrywania: {duration_sec}s ({duration_sec // 60}m)")
    print(f"Plik docelowy: {target}")
    print(f"==================================================")

    # 1. Wybór źródła
    chosen_url = None
    chosen_label = None

    if force_stream == "fallback":
        chosen_url = FALLBACK_STREAM
        chosen_label = "ServusTV HD (Rezerwa)"
    elif force_stream == "primary":
        chosen_url = PRIMARY_STREAM
        chosen_label = "Eleven Sports 1 PL"
    else:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Sprawdzam dostepnosc Eleven Sports 1 PL...")
        if test_stream_alive(PRIMARY_STREAM):
            chosen_url = PRIMARY_STREAM
            chosen_label = "Eleven Sports 1 PL (Komentarz PL)"
            print(f"✅ Eleven Sports 1 PL odpowiada, wybieram jako zrodlo glowne.")
        else:
            print(f"⚠️ Eleven Sports 1 PL nie odpowiada! Przelaczam na ServusTV HD...")
            chosen_url = FALLBACK_STREAM
            chosen_label = "ServusTV HD (Austriacki fallback)"

    if send_alerts:
        start_msg = (
            "🔴 <b>Dori DVR: Rozpoczęto nagrywanie wyścigu F1!</b> 🏎️\n\n"
            "🏁 <b>Grand Prix Azerbejdżanu (Baku) 2026</b>\n"
            f"📡 Źródło: <b>{chosen_label}</b>\n"
            f"⏱️ Zaplanowany czas: <b>{duration_sec // 60} minut</b>\n"
            "📁 Plik ląduje bezpośrednio na dysku VPS.\n\n"
            "<i>Dam znać z linkiem zaraz po fladze w szachownicę!</i>"
        )
        send_alert(start_msg)

    # 2. Nagrywanie
    start_time = time.time()
    success = record_stream(chosen_url, target, duration_sec)

    # Jeśli główny zawiódł, a nie był wymuszony fallback, spróbuj fallback
    if not success and chosen_url == PRIMARY_STREAM and force_stream is None:
        print(f"⚠️ Stream Eleven zawiodl. Przelaczam natychmiast na ServusTV HD!")
        if send_alerts:
            send_alert("⚠️ <i>Stream Eleven przerwał połączenie. Przełączam rejestrator na awaryjny ServusTV HD...</i>")
        chosen_url = FALLBACK_STREAM
        chosen_label = "ServusTV HD (Fallback po awarii)"
        remaining_sec = max(300, duration_sec - int(time.time() - start_time))
        success = record_stream(chosen_url, target, remaining_sec)

    elapsed_min = int((time.time() - start_time) // 60)

    # 3. Weryfikacja pliku
    if os.path.exists(target):
        file_size_bytes = os.path.getsize(target)
        file_size_mb = file_size_bytes / (1024 * 1024)
        file_size_gb = file_size_bytes / (1024 * 1024 * 1024)
    else:
        file_size_bytes, file_size_mb, file_size_gb = 0, 0, 0

    print(f"\n==================================================")
    print(f"🏁 ZAKOŃCZONO NAGRYWANIE")
    print(f"Czas trwania: {elapsed_min} minut")
    print(f"Rozmiar pliku: {file_size_mb:.1f} MB ({file_size_gb:.2f} GB)")
    print(f"Link do pobrania: {download_url}")
    print(f"==================================================\n")

    if send_alerts:
        if file_size_mb > 10:
            size_txt = f"{file_size_gb:.2f} GB" if file_size_gb >= 1.0 else f"{file_size_mb:.1f} MB"
            finish_msg = (
                "🏆 <b>Dori DVR: Wyścig nagrany i gotowy!</b> 🏁\n\n"
                "🏎️ <b>Grand Prix Azerbejdżanu (Baku) 2026</b>\n"
                f"📡 Zgrano z: <b>{chosen_label}</b>\n"
                f"📦 Rozmiar pliku: <b>{size_txt}</b>\n\n"
                "🔗 <b>Bezpośredni link HTTPS (VLC / Pobranie):</b>\n"
                f"<a href=\"{download_url}\">{download_url}</a>\n\n"
                "💡 <i>Możesz wkleić ten link w VLC na Macu / Apple TV (Plik ➔ Otwórz sieć) lub otworzyć w przeglądarce.</i>"
            )
            send_alert(finish_msg)
        else:
            err_msg = (
                "❌ <b>Dori DVR: Błąd zapisu wyścigu!</b>\n"
                f"Plik ma zaledwie {file_size_mb:.1f} MB. Sprawdź logi serwera na VPS."
            )
            send_alert(err_msg)

def main():
    parser = argparse.ArgumentParser(description="F1 Live DVR Recorder")
    parser.add_argument("--duration", "-d", type=int, default=8400, help="Czas nagrywania w sekundach (domyslnie 8400 = 2h 20m)")
    parser.add_argument("--source", "-s", choices=["primary", "fallback"], default=None, help="Wymus konkretne zrodlo")
    parser.add_argument("--no-alert", action="store_true", help="Wycisz alerty Telegram")
    parser.add_argument("--output", "-o", default=None, help="Wlasna sciezka pliku docelowego")
    parser.add_argument("--test", action="store_true", help="Szybki test 15-sekundowy")

    args = parser.parse_args()

    dur = 15 if args.test else args.duration
    target = os.path.join(DOWNLOADS_DIR, "test_f1_stream.mp4") if args.test else args.output

    run_dvr(duration_sec=dur, force_stream=args.source, send_alerts=not args.no_alert, output_file=target)

if __name__ == "__main__":
    main()
