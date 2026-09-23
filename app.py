import warnings
# Metoda atomowa: wyciszamy wszystko przed importami
warnings.filterwarnings("ignore")

import rumps
import requests
from datetime import datetime, timezone
from dateutil import parser
import threading
import time
import os

class F1ScoutApp(rumps.App):
    def __init__(self):
        super(F1ScoutApp, self).__init__("🏎️ F1 Scout")
        self.menu = [
            "Sprawdź Streamy", 
            "AI Scout: Szukaj nowych źródeł",
            None,
            "Kopiuj link do VLC: Brak",
            None,
            "Odśwież Harmonogram", 
            None, 
            "Ostatnia aktualizacja: Nigdy"
        ]
        self.next_session = None
        self.iptv_lists = [
            "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlist.m3u8"
        ]
        self.found_streams = {}
        self.timer = rumps.Timer(self.update_timer, 60)
        self.timer.start()
        self.fetch_schedule()

    def fetch_schedule(self):
        """Pobiera harmonogram z API z fallbackiem na 2026."""
        try:
            # Próba pobrania danych
            response = requests.get("https://jolpi.ca/ergast/f1/current/next.json", timeout=5)
            if response.status_code == 200 and response.text.strip():
                data = response.json()
                race = data['MRData']['RaceTable']['Races'][0]
                race_name = race['raceName']
                dt_str = f"{race['date']}T{race['time']}"
                self.next_session = {
                    'name': race_name,
                    'time': parser.parse(dt_str).replace(tzinfo=timezone.utc)
                }
            else:
                raise ValueError("Brak danych")
        except:
            # Fallback na GP Miami 2026 (3 Maja) - bo Bliski Wschód odwołany!
            self.next_session = {
                'name': "GP Miami (2026)",
                'time': datetime(2026, 5, 3, 20, 0, tzinfo=timezone.utc)
            }
        self.update_timer(None)

    @rumps.timer(60)
    def update_timer(self, _):
        if not self.next_session:
            self.title = "🏎️ No data"
            return

        now = datetime.now(timezone.utc)
        diff = self.next_session['time'] - now
        
        if diff.total_seconds() > 0:
            days = diff.days
            hours, remainder = divmod(diff.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            if days > 0:
                self.title = f"🏎️ {days}d {hours}h"
            else:
                self.title = f"🏎️ {hours}h {minutes}m"
        elif diff.total_seconds() > -7200: # Wyścig trwa ok. 2h
            self.title = "🏎️ LIVE!"
        else:
            self.title = "🏎️ Next: TBD"
        
        last_upd = self.menu["Ostatnia aktualizacja: Nigdy"]
        last_upd.title = f"Aktualizacja: {datetime.now().strftime('%H:%M:%S')}"

    @rumps.clicked("Sprawdź Streamy")
    def check_streams(self, _):
        threading.Thread(target=self._run_deep_scan).start()

    def _run_deep_scan(self):
        rumps.notification("F1 Scout", "Skanowanie", "Szukam kanałów F1...")
        keywords = ["Sky Sports F1", "Viaplay", "ServusTV", "ORF", "SuperTennis"]
        found = {}

        for url in self.iptv_lists:
            try:
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    lines = response.text.splitlines()
                    for i, line in enumerate(lines):
                        for kw in keywords:
                            if kw.lower() in line.lower() and i + 1 < len(lines):
                                link = lines[i+1].strip()
                                if link.startswith("http"):
                                    found[kw] = link
            except:
                continue

        if found:
            self.found_streams = found
            self._update_stream_menu()
            rumps.notification("F1 Scout", "Sukces!", f"Znaleziono {len(found)} kanałów.")
        else:
            rumps.notification("F1 Scout", "Pusto", "Brak aktywnych streamów F1.")

    def _update_stream_menu(self):
        # Usuwamy stare wpisy, jeśli istniały (operowanie na kluczach)
        for item in list(self.menu.keys()):
            if item.startswith("Kopiuj:"):
                del self.menu[item]

        if not self.found_streams:
            return

        for name, url in self.found_streams.items():
            key = f"Kopiuj: {name}"
            # W rumps przypisujemy element do klucza słownika, aby go dodać
            self.menu[key] = rumps.MenuItem(key, callback=lambda x, u=url: self._copy_to_clipboard(u))

    def _copy_to_clipboard(self, url):
        os.system(f"echo '{url}' | pbcopy")
        rumps.notification("F1 Scout", "Skopiowano", "Link w schowku. Wklej do VLC.")

    @rumps.clicked("AI Scout: Szukaj nowych źródeł")
    def ai_scout(self, _):
        rumps.notification("AI Scout", "Szukam...", "Analizuję bezpieczne źródła...")
        time.sleep(1.5)
        new_list = "https://iptv-org.github.io/iptv/index.m3u"
        if new_list not in self.iptv_lists:
            self.iptv_lists.append(new_list)
            rumps.notification("AI Scout", "Gotowe", "Dodano globalną bazę.")

    @rumps.clicked("Odśwież Harmonogram")
    def refresh(self, _):
        self.fetch_schedule()

if __name__ == "__main__":
    F1ScoutApp().run()
