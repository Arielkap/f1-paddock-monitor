#!/usr/bin/env python3
"""
F1 Race Live DVR Engine (Zero LLM Tokens)
Records live race broadcast from verified HLS streams (RTL Zwee 1080p, Eleven Sports 1, ServusTV)
directly to VPS disk using ffmpeg in lossless stream-copy mode.
Uses ffprobe to verify real video stream (avoiding paywalls, dead loops or 404s).
Extracts and sends a live photo snapshot to Telegram so the user gets instant visual proof.
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

DEFAULT_FILENAME = "f1_live_race.mp4"
DEFAULT_TARGET = os.path.join(DOWNLOADS_DIR, DEFAULT_FILENAME)

DOWNLOAD_BASE_URL = "https://mission.srv1986482.hstgr.cloud/downloads"
AUTH_TOKEN = "ariel-m2-studio-2026"
DEFAULT_CHAT_ID = "8929130284"

ENV_PATHS = [
    "/docker/hermes-agent-umxh/data/.env",
    "/opt/data/.env",
    os.path.expanduser("~/.env"),
    os.path.join(BASE_DIR, ".env")
]

def get_env_var(name: str):
    val = os.environ.get(name)
    if val:
        return val.strip("\"'")
    for p in ENV_PATHS:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith(f"{name}="):
                            return line.split("=", 1)[1].strip("\"' \n\r")
            except Exception:
                pass
    return None

def get_telegram_token():
    return get_env_var("TELEGRAM_BOT_TOKEN")

def get_candidate_streams():
    custom_url = get_env_var("F1_STREAM_URL") or ""
    return [
        {
            "id": "custom",
            "label": "Eleven Sports 1 PL / Custom (F1_STREAM_URL)",
            "url": custom_url
        },
        {
            "id": "rtl_zwee",
            "label": "RTL Zwee HD (F1 Live 1080p, EU)",
            "url": "https://stream.rtl.lu/data/live/tele/channel2/playlist.m3u8"
        },
        {
            "id": "servustv",
            "label": "ServusTV HD (Austriacki F1)",
            "url": "https://rbmn-live.akamaized.net/hls/live/2002825/geoSTVATweb/master.m3u8"
        },
        {
            "id": "orf1",
            "label": "ORF 1 HD (Austriacki F1)",
            "url": "https://orf1.mdn.ors.at/out/u/orf1/q8c/manifest.m3u8"
        }
    ]

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

def send_alert_photo(photo_path: str, caption: str, chat_id: str = DEFAULT_CHAT_ID) -> bool:
    token = get_telegram_token()
    if not token or not os.path.exists(photo_path):
        return False
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    try:
        with open(photo_path, "rb") as f:
            photo_data = f.read()
        boundary = "----WebKitFormBoundary" + os.urandom(16).hex()
        body = bytearray()
        # chat_id
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(b'Content-Disposition: form-data; name="chat_id"\r\n\r\n' + chat_id.encode("utf-8") + b"\r\n")
        # caption
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(b'Content-Disposition: form-data; name="caption"\r\n\r\n' + caption.encode("utf-8") + b"\r\n")
        # parse_mode
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(b'Content-Disposition: form-data; name="parse_mode"\r\n\r\nHTML\r\n')
        # photo
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(b'Content-Disposition: form-data; name="photo"; filename="preview.jpg"\r\nContent-Type: image/jpeg\r\n\r\n')
        body.extend(photo_data)
        body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode("utf-8"))

        req = urllib.request.Request(url, data=bytes(body), headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}"
        })
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[WARN] Błąd wysyłania zdjęcia na Telegram: {e}", file=sys.stderr)
        return False

def validate_stream_ffprobe(url: str, timeout: int = 7) -> tuple:
    """
    Validates the live stream using ffprobe to ensure it is delivering real video
    (resolution >= 640x360), not a 404, dead connection, or static paywall error card.
    """
    if not url or not url.startswith("http"):
        return False, "Brak lub niepoprawny URL"

    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,codec_name",
        "-of", "json",
        url
    ]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        if proc.returncode == 0 and proc.stdout:
            info = json.loads(proc.stdout.decode("utf-8", errors="ignore"))
            streams = info.get("streams", [])
            if streams:
                v = streams[0]
                w = v.get("width", 0)
                h = v.get("height", 0)
                codec = v.get("codec_name", "unknown")
                if w >= 640 and h >= 360:
                    return True, f"{w}x{h} ({codec})"
    except Exception:
        pass
    return False, "Brak aktywnego wideo / błąd strumienia"

def extract_snapshot(video_path: str, output_jpg: str) -> bool:
    """Takes a single frame snapshot from the recorded video to verify picture."""
    cmd = [
        "ffmpeg",
        "-y",
        "-ss", "00:00:05",
        "-i", video_path,
        "-vframes", "1",
        "-q:v", "2",
        output_jpg
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=12)
        return os.path.exists(output_jpg) and os.path.getsize(output_jpg) > 4000
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
        return os.path.exists(output_path) and os.path.getsize(output_path) > 1024 * 1024
    except subprocess.TimeoutExpired:
        print("[INFO] Nagrywanie zakończone po upływie zaplanowanego czasu.")
        return os.path.exists(output_path) and os.path.getsize(output_path) > 1024 * 1024
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

    # 1. Dobór działającego źródła (ffprobe real validation)
    chosen_url = None
    chosen_label = None
    candidates = get_candidate_streams()

    if force_stream:
        matched = [c for c in candidates if c["id"] == force_stream]
        if matched and matched[0]["url"]:
            chosen_url = matched[0]["url"]
            chosen_label = matched[0]["label"]
        else:
            chosen_url = force_stream
            chosen_label = f"Wymuszony: {force_stream[:30]}"
    else:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Weryfikuję dostępne źródła strumieniowe...")
        for c in candidates:
            url = c["url"]
            if not url:
                continue
            print(f" -> Badam: {c['label']} ...", end=" ")
            ok, details = validate_stream_ffprobe(url)
            if ok:
                print(f"✅ OK [{details}]")
                chosen_url = url
                chosen_label = f"{c['label']} [{details}]"
                break
            else:
                print(f"❌ Odpada ({details})")

    if not chosen_url:
        err_msg = "❌ <b>Dori DVR: Błąd krytyczny!</b> Żadne ze zdefiniowanych źródeł F1 nie nadaje aktywnego strumienia wideo."
        print(f"[CRITICAL] {err_msg}")
        if send_alerts:
            send_alert(err_msg)
        return False

    print(f"🎯 Wybrano źródło do nagrywania: {chosen_label}")

    if send_alerts:
        start_msg = (
            "🔴 <b>Dori DVR: Rozpoczęto nagrywanie wyścigu F1!</b> 🏎️\n\n"
            f"📡 Źródło: <b>{chosen_label}</b>\n"
            f"⏱️ Zaplanowany czas: <b>{duration_sec // 60} minut</b>\n"
            "📁 Zapis bezstratny HLS bezpośrednio na dysk VPS.\n\n"
            "<i>Po 15 sekundach wyślę klatkę z nagrania dla potwierdzenia obrazu!</i>"
        )
        send_alert(start_msg)

    # 2. Nagrywanie z próbkowaniem w tle
    start_time = time.time()

    # Odpalamy 15-sekundowy zrzut próbny, aby wysłać zdjęcie podglądowe
    preview_path = f"/tmp/f1_preview_{int(start_time)}.jpg"
    test_clip_path = f"/tmp/f1_probe_{int(start_time)}.mp4"

    # Nagraj krótki 8s klip do zdjęcia podglądowego
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Pobieram próbkę do klatki weryfikacyjnej Telegram...")
    probe_cmd = [
        "ffmpeg", "-user_agent", "Mozilla/5.0", "-i", chosen_url,
        "-c", "copy", "-bsf:a", "aac_adtstoasc", "-t", "8", "-y", test_clip_path
    ]
    subprocess.run(probe_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
    
    if os.path.exists(test_clip_path) and os.path.getsize(test_clip_path) > 500 * 1024:
        if extract_snapshot(test_clip_path, preview_path):
            if send_alerts:
                caption = f"📸 <b>Podgląd z transmisji na żywo</b>\n📡 Źródło: {chosen_label}\n✅ Obraz potwierdzony!"
                send_alert_photo(preview_path, caption)
            try:
                os.remove(preview_path)
            except Exception:
                pass
    try:
        if os.path.exists(test_clip_path):
            os.remove(test_clip_path)
    except Exception:
        pass

    # Główny proces nagrywania
    remaining_duration = duration_sec
    success = record_stream(chosen_url, target, remaining_duration)

    elapsed_min = int((time.time() - start_time) // 60)

    # 3. Weryfikacja pliku docelowego
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
        # Prawdziwy wyścig w 1080p waży minimum 1 GB na 2 godziny
        if file_size_mb > 500:
            size_txt = f"{file_size_gb:.2f} GB" if file_size_gb >= 1.0 else f"{file_size_mb:.1f} MB"
            finish_msg = (
                "🏆 <b>Dori DVR: Wyścig nagrany i gotowy!</b> 🏁\n\n"
                f"📡 Zgrano z: <b>{chosen_label}</b>\n"
                f"📦 Rozmiar pliku: <b>{size_txt}</b>\n\n"
                "🔗 <b>Bezpośredni link HTTPS (VLC / Pobranie):</b>\n"
                f"<a href=\"{download_url}\">{download_url}</a>\n\n"
                "💡 <i>Możesz wkleić ten link w VLC na Macu / Apple TV (Plik ➔ Otwórz sieć) lub otworzyć w przeglądarce.</i>"
            )
            send_alert(finish_msg)
        else:
            err_msg = (
                "❌ <b>Dori DVR: Podejrzanie mały plik wyścigu!</b>\n"
                f"Plik ma zaledwie {file_size_mb:.1f} MB (oczekiwano >500 MB). Sprawdź czy transmisja nie została przerwana lub czy nie nadano planszy błędu."
            )
            send_alert(err_msg)

    return success

def main():
    parser = argparse.ArgumentParser(description="F1 Live DVR Recorder")
    parser.add_argument("--duration", "-d", type=int, default=8400, help="Czas nagrywania w sekundach (domyslnie 8400 = 2h 20m)")
    parser.add_argument("--source", "-s", default=None, help="Wymus konkretne zrodlo (id lub url)")
    parser.add_argument("--no-alert", action="store_true", help="Wycisz alerty Telegram")
    parser.add_argument("--output", "-o", default=None, help="Wlasna sciezka pliku docelowego")
    parser.add_argument("--test", action="store_true", help="Szybki test z klatką i 15-sekundowym nagraniem")

    args = parser.parse_args()

    dur = 15 if args.test else args.duration
    target = os.path.join(DOWNLOADS_DIR, "test_f1_stream.mp4") if args.test else args.output

    run_dvr(duration_sec=dur, force_stream=args.source, send_alerts=not args.no_alert, output_file=target)

if __name__ == "__main__":
    main()
