#!/usr/bin/env python3
"""
F1 Paddock Monitor & Race State Engine (0 LLM Tokens, Standard Library Only)
Sources:
- Jolpica Ergast F1 API (Live race weekend schedule, next sessions, last race TOP 10, last qualifying)
- Free-TV IPTV Playlist (Direct M3U8 stream links for ORF, ServusTV, Viaplay, Sky Sports F1)
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(BASE_DIR, "f1_status.json")
IPTV_URL = "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlist.m3u8"

def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Ariel-F1-Monitor/1.0"})
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))

def get_next_f1_race():
    url = "https://api.jolpi.ca/ergast/f1/current/next.json"
    try:
        data = fetch_json(url)
        race = data["MRData"]["RaceTable"]["Races"][0]
        name = race.get("raceName", "Grand Prix")
        circuit = race.get("Circuit", {}).get("circuitName", "Circuit")
        country = race.get("Circuit", {}).get("Location", {}).get("country", "")
        race_date = race.get("date", "")
        race_time = race.get("time", "13:00:00Z")
        
        fp1_d = race.get("FirstPractice", {}).get("date", "")
        fp1_t = race.get("FirstPractice", {}).get("time", "10:00:00Z")
        
        fp2_d = race.get("SecondPractice", {}).get("date", "")
        fp2_t = race.get("SecondPractice", {}).get("time", "13:00:00Z")
        
        fp3_d = race.get("ThirdPractice", {}).get("date", "")
        fp3_t = race.get("ThirdPractice", {}).get("time", "10:00:00Z")
        
        quali_d = race.get("Qualifying", {}).get("date", "")
        quali_t = race.get("Qualifying", {}).get("time", "13:00:00Z")
        
        sprint_d = race.get("Sprint", {}).get("date", "") if "Sprint" in race else None
        sprint_t = race.get("Sprint", {}).get("time", "13:00:00Z") if "Sprint" in race else None

        return {
            "race_name": name,
            "circuit": circuit,
            "country": country,
            "race_datetime_utc": f"{race_date}T{race_time}" if race_date else "2026-09-26T11:00:00Z",
            "fp1": f"{fp1_d}T{fp1_t}" if fp1_d else "2026-09-24T08:30:00Z",
            "fp2": f"{fp2_d}T{fp2_t}" if fp2_d else "2026-09-24T12:00:00Z",
            "fp3": f"{fp3_d}T{fp3_t}" if fp3_d else "2026-09-25T08:30:00Z",
            "qualifying": f"{quali_d}T{quali_t}" if quali_d else "2026-09-25T12:00:00Z",
            "sprint": f"{sprint_d}T{sprint_t}" if sprint_d else None
        }
    except Exception as e:
        print(f"[WARN] Błąd pobierania next race: {e}")
        return {
            "race_name": "Azerbaijan Grand Prix",
            "circuit": "Baku City Circuit",
            "country": "Azerbaijan",
            "race_datetime_utc": "2026-09-26T11:00:00Z",
            "fp1": "2026-09-24T08:30:00Z",
            "fp2": "2026-09-24T12:00:00Z",
            "fp3": "2026-09-25T08:30:00Z",
            "qualifying": "2026-09-25T12:00:00Z",
            "sprint": None
        }

def get_last_race_results():
    url = "https://api.jolpi.ca/ergast/f1/current/last/results.json"
    try:
        data = fetch_json(url)
        race = data["MRData"]["RaceTable"]["Races"][0]
        r_name = race.get("raceName", "Grand Prix")
        r_circuit = race.get("Circuit", {}).get("circuitName", "")
        r_date = race.get("date", "")
        r_time = race.get("time", "13:00:00Z")
        
        top10 = []
        for res in race.get("Results", [])[:10]:
            d_name = f"{res['Driver'].get('givenName', '')} {res['Driver'].get('familyName', '')}".strip()
            c_name = res.get("Constructor", {}).get("name", "F1 Team")
            time_val = res.get("Time", {}).get("time", res.get("status", "Fin"))
            top10.append({
                "pos": res.get("position", "1"),
                "driver": d_name,
                "constructor": c_name,
                "time": time_val,
                "points": res.get("points", "0")
            })

        return {
            "race_name": r_name,
            "circuit": r_circuit,
            "date": r_date,
            "datetime_utc": f"{r_date}T{r_time}" if r_date else "",
            "top10": top10
        }
    except Exception as e:
        print(f"[WARN] Błąd pobierania last race results: {e}")
        return None

def get_last_quali_results():
    url = "https://api.jolpi.ca/ergast/f1/current/last/qualifying.json"
    try:
        data = fetch_json(url)
        race = data["MRData"]["RaceTable"]["Races"][0]
        r_name = race.get("raceName", "Grand Prix")
        r_date = race.get("date", "")
        
        top5 = []
        for res in race.get("QualifyingResults", [])[:5]:
            d_name = f"{res['Driver'].get('givenName', '')} {res['Driver'].get('familyName', '')}".strip()
            c_name = res.get("Constructor", {}).get("name", "F1 Team")
            q_time = res.get("Q3") or res.get("Q2") or res.get("Q1") or "-"
            top5.append({
                "pos": res.get("position", "1"),
                "driver": d_name,
                "constructor": c_name,
                "time": q_time
            })

        return {
            "race_name": r_name,
            "date": r_date,
            "top5": top5
        }
    except Exception as e:
        print(f"[WARN] Błąd pobierania last qualifying: {e}")
        return None

def find_iptv_streams():
    keywords = ["Sky Sports F1", "Viaplay", "ServusTV", "ORF", "SuperTennis"]
    found = {}
    try:
        req = urllib.request.Request(IPTV_URL, headers={"User-Agent": "Ariel-F1-Monitor/1.0"})
        with urllib.request.urlopen(req, timeout=12) as response:
            lines = response.read().decode("utf-8", errors="ignore").splitlines()
            for i, line in enumerate(lines):
                for kw in keywords:
                    if kw.lower() in line.lower() and i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        if next_line.startswith("http"):
                            if kw not in found:
                                found[kw] = next_line
    except Exception as e:
        print(f"[IPTV WARN] Błąd pobierania playlisty IPTV: {e}")

    # Fallback direct verified streams
    fallback_streams = {
        "ORF": "https://orf1.mdn.ors.at/out/u/orf1/q8c/manifest.m3u8",
        "ServusTV": "https://rbmn-live.akamaized.net/hls/live/2002825/geoSTVATweb/master.m3u8",
        "Viaplay": "https://live-fi.tvkaista.net/viaplay-tv/live.m3u8?src=freetv",
        "SuperTennis": "https://live-embed.supertennix.hiway.media/restreamer/supertennix_client/gpu-a-c0-16/restreamer/outgest/aa3673f1-e178-44a9-a947-ef41db73211a/manifest.m3u8"
    }

    for k, v in fallback_streams.items():
        if k not in found or not found[k].startswith("http"):
            found[k] = v

    return found

def run():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🏎️ Pobieram dane F1 i streamy...")
    next_race = get_next_f1_race()
    last_race = get_last_race_results()
    last_quali = get_last_quali_results()
    streams = find_iptv_streams()

    payload = {
        "updated_at": datetime.now().isoformat(),
        "next_race": next_race,
        "last_race_results": last_race,
        "last_quali_results": last_quali,
        "streams": streams
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    top10_count = len(last_race.get("top10", [])) if last_race else 0
    print(f"✅ Zapisano F1 status: Nadchodzący {next_race['race_name']} | Poprzedni TOP 10 ({top10_count} kierowców) | Streamy: {len(streams)}")

if __name__ == "__main__":
    run()
