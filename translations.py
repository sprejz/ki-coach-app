# translations.py — KI Coach i18n strings
# Usage: T = TRANSLATIONS.get(os.environ.get("APP_LANG","de"), TRANSLATIONS["de"])

TRANSLATIONS = {
    "de": {
        # App
        "app_title":        "KI Coach",
        "splash_sub":       "Triathlon · Tagescoaching",
        # Loading states
        "loading":           "Laden…",
        "loading_data":      "Daten werden geladen…",
        "loading_weather":   "Wetter wird geladen…",
        "loading_workouts":  "Workouts werden geladen…",
        "refreshing":        "Daten werden aktualisiert…",
        "ready":             "Bereit!",
        # Tabs
        "tab_abend":         "Abend",
        "tab_morgen":        "Morgen",
        "tab_analyse":       "Analyse",
        "tab_erholung":      "Erholung",
        "tab_profil":        "Profil",
        "tab_about":         "Info",
        # Section titles
        "sec_tomorrow":      "Morgen",
        "sec_today":         "Heute",
        "sec_body_evening":  "Körperzustand heute Abend",
        "sec_body_morning":  "Körperzustand heute Morgen",
        "sec_athlete":       "Athletenprofil",
        "sec_races":         "Rennen",
        "sec_baseline":      "Schlaf-Baseline",
        "sec_baseline_recalc": "Baseline neu berechnen",
        "sec_erholung_letzte": "Letzte Nacht",
        "sec_erholung_verlauf": "7-Tage-Verlauf",
        # Form labels
        "lbl_knie":          "Knie",
        "lbl_achilles_l":    "Achillessehne L",
        "lbl_achilles_r":    "Achillessehne R",
        "lbl_waden":         "Waden",
        "lbl_muedigkeit":    "Müdigkeit",
        "lbl_mud_hint":      "1 = frisch · 5 = erschöpft",
        "lbl_muskelkater":   "Muskelkater",
        "lbl_symptome":      "Symptome",
        "lbl_wasser_temp":   "Wassertemperatur Freibad",
        "lbl_optional":      "optional",
        "lbl_no_pain":       "0 — kein Schmerz",
        "lbl_max":           "10 — max",
        # CSV upload
        "lbl_csv":           "AutoSleep CSV",
        "lbl_csv_btn":       "CSV hochladen",
        "lbl_csv_tap":       "oder tippen",
        "lbl_csvs_btn":      "CSVs hochladen",
        "lbl_csvs_hint":     "mehrere möglich",
        # TP workouts
        "lbl_tp_tomorrow":   "TP Workouts morgen",
        "lbl_tp_today":      "TP Workouts heute",
        "lbl_tp_loading":    "wird geladen…",
        "tp_no_cfg":         "TP nicht konfiguriert",
        "tp_no_w_tomorrow":  "Keine Workouts in TP für morgen",
        "tp_no_w_today":     "Keine Workouts in TP für heute",
        "tp_no_w":           "Keine Workouts geplant",
        "tp_unreachable":    "TP nicht erreichbar",
        "tp_loading_text":   "Wird geladen…",
        # Weather
        "weather_n_a":       "Wetter nicht verfügbar",
        # Erholung tab
        "erholung_no_data":      "Noch keine Schlafdaten — lade eine AutoSleep CSV im Morgen-Check hoch.",
        "erholung_no_baseline":  "Noch keine Baseline — im Profil-Tab berechnen.",
        "erholung_index":        "Erholungsindex",
        "erholung_trend":        "HRV-Trend",
        "erholung_trend_up":     "↑ Steigend",
        "erholung_trend_stable": "→ Stabil",
        "erholung_trend_down":   "↓ Fallend",
        "erholung_legend_hrv":   "HRV (ms)",
        "erholung_legend_wach":  "WachBPM",
        "erholung_legend_ref":   "Flagschwelle",
        # Baseline warnings
        "baseline_warning":      "⚠️ Nur für längere Zeiträume (mind. 30 Nächte). Für den täglichen Check CSV im Morgen-Check hochladen.",
        "baseline_nights_warn":  "⚠️ Nur {n} Nächte — Baseline sollte auf mind. 30 Nächten basieren.",
        # CSV hint
        "csv_morgen_hint":       "Lade die CSV der letzten Nacht hoch (aus AutoSleep App exportieren)",
        # Muskelkater pills (label)
        "mk_keine":          "keine",
        "mk_waden":          "Waden",
        "mk_oberschenkel":   "Oberschenkel",
        "mk_beine":          "Beine",
        "mk_oberkoerper":    "Oberkörper",
        "mk_ganzkoerper":    "Ganzkörper",
        # Muskelkater data-values (sent to Claude)
        "mkv_keine":         "keine",
        "mkv_waden":         "Waden",
        "mkv_oberschenkel":  "Oberschenkel",
        "mkv_beine":         "Beine allgemein",
        "mkv_oberkoerper":   "Oberkörper",
        "mkv_ganzkoerper":   "Ganzkörper",
        # Symptome pill labels (display)
        "sym_keine":         "keine",
        "sym_besser":        "besser",
        "sym_gleich_leicht": "gleich leicht",
        "sym_schlechter":    "schlechter",
        "sym_neu_leicht":    "neu leicht",
        "sym_neu_mittel":    "neu mittel",
        "sym_neu_schwer":    "neu schwer",
        # Symptome data-values (sent to Claude)
        "symv_keine":        "keine",
        "symv_besser":       "besser",
        "symv_gleich_leicht":"gleich leicht (Schnupfen/Kopfdruck)",
        "symv_schlechter":   "schlechter",
        "symv_neu_leicht":   "neu leicht",
        "symv_neu_mittel":   "neu mittel (Halsschmerzen/Husten)",
        "symv_neu_schwer":   "neu schwer (Fieber/Körperschmerzen)",
        # Buttons
        "btn_abend":         "Abend-Check starten",
        "btn_morgen":        "Morgen-Check starten",
        "btn_save":          "Speichern",
        "btn_saved":         "✓ Gespeichert",
        "btn_baseline":      "Baseline neu berechnen",
        "btn_tp_apply":      "→ Empfehlung in TP anwenden",
        "btn_tp_load":       "→ TP Workouts laden",
        "btn_refresh_title": "Neu laden",
        "btn_refresh_aria":  "Daten neu laden",
        # Countdown / header
        "countdown_loading": "Laden…",
        # Profil labels
        "lbl_ftp":           "FTP",
        "lbl_ftp_unit":      "Watt",
        "lbl_weight":        "Gewicht",
        "lbl_weight_unit":   "kg",
        "lbl_run_thr":       "Laufschwelle",
        "lbl_run_thr_unit":  "/km",
        "lbl_css":           "CSS Schwimmen",
        "lbl_css_unit":      "/100m",
        "lbl_swim_min":      "Outdoor-Schwimmen ab",
        "lbl_swim_min_unit": "°C",
        # Baseline labels
        "lbl_hrv":           "SchlafHRV",
        "lbl_wach_bpm":      "WachBPM",
        "lbl_schlaf_bpm":    "SchlafBPM",
        "lbl_atmung":        "Atmung",
        "lbl_effizienz":     "Effizienz",
        # JS / dynamic strings
        "err_profile_load":  "Athleten-Profil konnte nicht geladen werden.",
        "err_save":          "Fehler beim Speichern",
        "claude_analyzing":  "Claude analysiert…",
        "tp_applying":       "Wird in TrainingPeaks übernommen…",
        # Claude prompts — system
        "prompt_system": (
            "Du bist KI Coach für {name}, Langdistanz-Triathlet.\n"
            "A-Rennen: {a_info} · {weight}kg · FTP {ftp}W · Lauf {run_thr}/km · CSS {css}/100m\n"
            "{b_text}"
            "KÖRPERSIGNALE — beurteile wie ein Sportmediziner, nicht nach starren Schwellen:\n"
            "KNIE: Leichte Steifigkeit/Müdigkeit → Umfang und Intensität reduzieren, kein Tempo, flacher Untergrund. "
            "Schmerz unter Last, beim Treppensteigen oder nach dem Training → Lauf STOP, Rad nur wenn schmerzfrei, Aquajogging als Alternative. "
            "Schwellung, Instabilität oder Schmerz in Ruhe → komplette Pause. "
            "Knie reagiert empfindlich auf Bergab-Lauf und hohe Kadenz — im Zweifel konservativ.\n"
            "ACHILLES: Morgendliche Steifigkeit die sich löst → angepasstes Training ok, kein Tempo, weicher Untergrund. "
            "Schmerz beim Zehenstand, unter Last oder der 'Knoten' wird dicker → Lauf STOP, Rad/Schwimmen ok. "
            "Achillesschmerz verschlechtert sich oft verzögert (12-24h) — deshalb bei Unsicherheit immer konservativ.\n"
            "WADEN: Vorläufer von Achillessehnen- und Soleus-Problemen. "
            "Verspannung die sich beim Aufwärmen löst → Lauf kürzen, kein Tempo. "
            "Schmerz der unter Last bleibt oder zunimmt → kein Lauf (Rad/Schwimmen ok). "
            "Hohe Waden + hohe Achilles kombiniert → Lauf STOP.\n"
            "MUSKELKATER: Beine leicht → Belastung reduzieren, kein Tempo, Z1–Z2 ok. "
            "Beine stark → nur lockeres Einrollen max 30min, kein Kraft-/Intervalltraining. "
            "Oberkörper → Schwimmen anpassen (Technik statt Kraft), Rad/Lauf nicht betroffen. "
            "Überall → Regenerationstag, höchstens sehr lockeres Schwimmen. "
            "Muskelkater ist kein Verletzungsrisiko, aber zeigt unvollständige Erholung — Intensität entsprechend drosseln.\n"
            "WETTER — Erfahrungswissen für alle drei Sportarten:\n"
            "GEWITTER: Alle Outdoor-Sportarten sofort STOP — Laufen ist genauso gefährlich wie Radfahren. "
            "Freiwasser-Schwimmen bei Gewitter extrem gefährlich (sofort raus). "
            "Rad → Zwift, Lauf → indoor/Laufband oder streichen, Schwimmen → Hallenbad wenn möglich, sonst SKIP.\n"
            "REGEN: Leichter Regen beim Laufen ok (Kühleffekt), Tempo-Erwartungen leicht senken, Schuhgriff beachten. "
            "Starker Regen beim Laufen → Verletzungsrisiko durch nasse Oberflächen, Sicht, Unterkühlung bei länger als 60min → kürzen oder indoor. "
            "Rad bei Regen: nasse Straßen = deutlich längere Bremswege, Kurven rutschig → Zwift empfehlen, besonders bei >60min oder Tempo-Einheiten. "
            "Schwimmen im Freibad bei Regen: ok (man ist sowieso nass), bei Gewitter sofort raus.\n"
            "HITZE >25°C: Laufen — Pace pro Grad über 20°C ca. 4-5% langsamer (physiologisch belegt), früh morgens oder abends trainieren, "
            "Einheiten >60min im Freien stark überdenken, keine harten Intervalle über Mittag. "
            "Rad — Herzfrequenz driftet bei Hitze nach oben (cardiac drift), nach HF/RPE steuern nicht nach Watt, "
            "Zwift bei >30°C ernsthaft erwägen. "
            "Schwimmen — profitiert von Hitze (Kühleffekt im Wasser), Freibad optimal; Wassertemperatur >28°C kann bei langen Einheiten belasten. "
            "Alle Sportarten: {fluid_heat}ml/h Wasser, {salt_heat} Saltstick/h, Hitzesymptome (Schwindel, Übelkeit, Orientierung) → sofort STOP.\n"
            "KÄLTE <10°C: Laufen — längeres Aufwärmen nötig (10-15min), Muskeln brauchen mehr Zeit, "
            "Verletzungsrisiko steigt wenn kalt gestartet wird, Atemwege schützen (<0°C Sturmhaube). "
            "Rad outdoor — <10°C Hände/Füße kühlen schnell aus (Neopren/Thermohandschuhe), bei <5°C Hypothermierisiko auf langen Abfahrten, "
            "Zwift ab <5°C oder Regen+Kälte klar empfehlen. "
            "Schwimmen — Freibad unter {swim_min}°C Wassertemperatur auf Hallenbad wechseln, "
            "unter 14°C Kälteschock-Risiko auch für trainierte Schwimmer.\n"
            "SONSTIGE GRENZEN: Symptome neu schwer→Ruhe\n"
            "WEICHE SIGNALE: Müdigkeit ≥4→Intensität raus · Schlafdauer ignorieren, primär HRV+WachBPM\n"
            "Ernährung ab 90min: {carbs}g/h+{salt} Saltstick/h; Hitze>{heat_thr}°C: {fluid_heat}ml+{salt_heat}x Saltstick/h\n"
            "ENTSCHEIDUNGSREGEL: Triff immer eine klare Entscheidung — GO, MOD oder STOP. "
            "Stelle keine Fragen an den Athleten. "
            "Wenn mehrere Optionen möglich sind, wähle die konservativere. "
            "Bei MOD: konkrete Anpassung nennen (Distanz, Zone, Alternative), nicht beide Optionen.\n\n"
            "WORKOUT-BESCHREIBUNG für TrainingPeaks (Feld 'beschreibung'):\n"
            "Bei GO: Übernimm die originale Workout-Beschreibung aus dem TrainingPeaks-Kontext exakt so wie sie ist — kein Wort ändern.\n"
            "Bei MOD mit vorhandener Original-Beschreibung: Nimm den EXAKTEN ORIGINALTEXT und ändere NUR die konkreten Werte die angepasst werden müssen. "
            "Behalte Satzstruktur, Format und alle anderen Zeilen des Originals bei. "
            "Füge am Ende eine kurze Zeile mit dem Anpassungsgrund + Maßnahmen an (z.B. 'HITZE: 750ml/h, 2× Saltstick/h — Zeitpunkt ≤09:00 oder ab 19:00 Uhr').\n"
            "Beispiel: Original '35 min ganz locker (6:15–6:45/km, HF-Deckel 150 bpm)' → "
            "MOD '35 min ganz locker (6:30–7:05/km, HF-Deckel 145 bpm) [Hitze-Anpassung]'\n"
            "Bei MOD ohne Original-Beschreibung (leeres description-Feld): Erstelle eine vollständige Trainingsstruktur basierend auf Titel, Sport und Dauer — direkt umsetzbar, ohne Platzhaltertext.\n"
            "Wenn die Anpassung so fundamental ist dass der Original-Inhalt komplett hinfällig ist "
            "(z.B. Intervall-Session → Regenerationstag): erste Zeile '⚠️ Einheit komplett umgestellt', dann neue Beschreibung.\n"
            "NIEMALS eine neue Aufwärmen/Hauptteil/Auslaufen-Struktur erfinden wenn das Original diese nicht hat.\n"
            "Sportspezifische Begriffe: Schwimmen → Einschwimmen/Ausschwimmen, Rad → Einrollen/Ausrollen, Laufen → Einlaufen/Auslaufen.\n"
            "Schwimmeinheiten (MOD): Berechne Gesamtdistanz als Summe ALLER Blöcke (Einschwimmen + Hauptteil-Meter + Ausschwimmen). "
            "Schreibe Gesamtdistanz als erste Zeile (z.B. 'Gesamt: ~1500m'). Alle Teilblöcke müssen zur Gesamtdistanz aufgehen.\n"
            "Lauf/Rad MOD ohne Original-Beschreibung: vollständige Struktur mit Einrollen/Einlaufen, Haupteinheit "
            "(Wiederholungen × Dauer/Distanz mit konkretem Pace/Watt-Ziel), Ausrollen/Auslaufen.\n"
            "Hitze/Kälte-Anpassung: Schreibe HITZE oder KÄLTE als erstes Wort in die Zeile mit Anpassungsdetails.\n\n"
            "TP-STRUKTUR (optionales Feld 'tp_struktur', nur bei MOD mit echten Intervall-Blöcken — NICHT bei reiner Ausdauer):\n"
            "Rad → primaryIntensityMetric:'percentOfFtp', Lauf/Schwimm → 'percentOfThresholdPace'\n"
            "Intensität % der Schwelle: WarmUp/CoolDown=50-60, Z1=55-65, Z2=65-75, Z3=80-90, Z4=95-105, Z5=106-120\n"
            "intensityClass-Werte: 'warmUp'|'active'|'rest'|'coolDown'\n"
            "Einzelschritt: {{\"name\":\"...\",\"duration_seconds\":N,\"intensity_min\":X,\"intensity_max\":Y,\"intensityClass\":\"active\"}}\n"
            "Wiederholungsblock: {{\"type\":\"repetition\",\"reps\":N,\"steps\":[...]}}\n"
            "Schwimm-MOD: Feld 'distanz_m' mit Gesamtdistanz in Metern setzen.\n\n"
            "Antworte NUR als JSON (kein Markdown):\n"
            '{{"status":"green","status_text":"Alles grün","sportarten":['
            '{{"sport":"Rad","badge":"MOD",'
            '"details":"1-2 Sätze Coach-Hinweis",'
            '"beschreibung":"Einrollen: 10min\\n- 4×8min FTP (95-105%), 2min Pause\\n- Ausrollen: 10min",'
            '"ernaehrung":"...",'
            '"tp_struktur":{{"steps":['
            '{{"name":"Einrollen","duration_seconds":600,"intensity_min":50,"intensity_max":60,"intensityClass":"warmUp"}},'
            '{{"type":"repetition","reps":4,"steps":['
            '{{"name":"FTP","duration_seconds":480,"intensity_min":95,"intensity_max":105,"intensityClass":"active"}},'
            '{{"name":"Pause","duration_seconds":120,"intensity_min":40,"intensity_max":50,"intensityClass":"rest"}}'
            ']}},'
            '{{"name":"Ausrollen","duration_seconds":600,"intensity_min":45,"intensity_max":55,"intensityClass":"coolDown"}}'
            '],"primaryIntensityMetric":"percentOfFtp"}}'
            '}}],"autosleep_summary":null,"wetter_hinweis":"...","prep":"..."}}'
        ),
        "prompt_system_baseline": (
            "\nBaseline ({nights} Nächte, Stand {updated}):"
            "\n  SchlafHRV: Median {hrv_med}ms, Flag ≤{hrv_flag}ms"
            "\n  WachBPM:   Median {wach_med}, Flag ≥{wach_flag}"
            "\n  SchlafBPM: Median {schlaf_med}, Flag ≥{schlaf_flag}"
        ),
        "prompt_abend_header":   "Abend-Check — Plan für morgen ({date}):",
        "prompt_morgen_header":  "Morgen-Check — Go/No-Go für heute ({date}):",
        "prompt_abend_units":    "Geplante Einheiten morgen: {units}",
        "prompt_abend_units_empty": "noch nicht festgelegt — bitte empfehlen",
        "prompt_morgen_units":   "Geplante Einheiten heute: {units}",
        "prompt_morgen_units_empty": "noch nicht festgelegt",
        "prompt_weather_label":  "Wetter morgen in {city}:",
        "prompt_weather_today":  "Wetter heute in {city}:",
        "prompt_weather_thunderstorm": "JA",
        "prompt_weather_no":     "nein",
        "prompt_weather_heat":   "JA",
        "prompt_autosleep_header": "AutoSleep (letzte Nacht):",
        "prompt_autosleep_flags_ok": "alle Marker ok",
        "prompt_autosleep_err":  "AutoSleep Fehler: {err}",
        "prompt_wasser":         "Wassertemperatur Freibad: {temp}°C",
        "prompt_tp_ctx":         "TrainingPeaks geplante Workouts morgen: {data}",
        "prompt_rain_peaks":     "Regenspitzen: {peaks}",
        "prompt_heat_alarm":     "Hitzealarm (>{threshold}°C): {val}",
        # TP apply prompts
        "tp_apply_prompt_intro":  "Apply the following changes to TrainingPeaks for '{name}' on {date}.",
        "tp_apply_prompt_sem":    (
            "Operation semantics:\n"
            "- rename_workout: Use workout_id (if provided) to find and rename; fallback to old_title match\n"
            "- create_workout: Create a new planned workout with title, sport, duration_min and note\n\n"
            "After completing all operations respond ONLY with a JSON array (no markdown):\n"
            '[{{"action":"rename_workout","status":"ok","detail":"Renamed to ↩️ Z2 Ausdauer (KI)"}}]\n'
            "Use status 'ok' or 'error'."
        ),
        "tp_workouts_prompt": (
            "Alle geplanten Workouts für {name} am {date} aus TrainingPeaks auflisten. "
            "Antworte NUR mit einem gültigen JSON-Array mit diesen Feldern: id, sport, title, duration_min, tss. "
            "Beispiel: "
            '[{{"id":"123","sport":"Swim","title":"Pool Z2","duration_min":45,"tss":30}}]'
        ),
        "tp_history_prompt": (
            "Liste alle Workouts (geplant und abgeschlossen) für {name} vom {start} bis {end} aus TrainingPeaks. "
            "Gruppiere nach Datum. Antworte NUR mit einem gültigen JSON-Array. Beispiel: "
            '[{{"date":"2026-06-20","workouts":[{{"id":"123","sport":"Swim","title":"Pool Z2","duration_min":45,"tss":30,"start_time":"2026-06-20T07:15:00"}}]}}] '
            "start_time ist die tatsächliche Startzeit des abgeschlossenen Workouts (ISO 8601, Lokalzeit), falls verfügbar — sonst weglassen. "
            "Nur Tage mit Workouts einbeziehen. Älteste Tage zuerst."
        ),
        "tp_completed_prompt": (
            "Rufe mit den verfügbaren TrainingPeaks-Tools das Workout \"{title}\" von {name} am {date} ab. "
            "Workout-ID: {workout_id}, Sport: {sport}. "
            "Nutze das Tool um ALLE verfügbaren Daten zu holen: geplante UND tatsächliche Ist-Daten. "
            "Gib danach eine detaillierte Zusammenfassung aller Felder aus, die das Tool geliefert hat: "
            "Dauer (geplant/tatsächlich), Distanz, Herzfrequenz (Ø, Max), "
            "Leistung (Ø, Max, nur Rad), Pace (Ø, nur Lauf/Schwimmen), TSS (geplant/tatsächlich), "
            "Zonenverteilung, Notizen, Status (abgeschlossen/geplant). "
            "Schreibe die rohen Tool-Daten vollständig auf Deutsch heraus — kein JSON, nur Fließtext mit allen Werten."
        ),
        "coach_analysis_prompt": (
            "Führe folgende zwei Schritte aus:\n\n"
            "SCHRITT 1: Rufe über die TrainingPeaks-Tools das Workout ab:\n"
            "- Titel: \"{title}\"\n"
            "- Datum: {date}\n"
            "- Sport: {sport}\n"
            "- Workout-ID: {workout_id}\n"
            "Hole alle verfügbaren Daten: Dauer, Distanz, HF (Ø/Max), Leistung (Ø/Max), "
            "Pace (Ø), TSS, Zonenverteilung, Notizen.\n\n"
            "SCHRITT 2: Analysiere als erfahrener Triathlon-Coach ({name}, FTP {ftp}W, "
            "Laufschwelle {run_threshold}/km, CSS {css}/100m, "
            "A-Rennen: {race_name} am {race_date}, Zielzeit {race_goal}h):\n"
            "War diese Einheit gut ausgeführt? Direkt, ehrlich, ohne Floskeln.\n\n"
            "Antworte NUR als JSON:\n"
            '{{"bewertung":"gut|ok|verbesserungsbedarf",'
            '"urteil":"3-4 direkte Sätze: Wie war die Einheit wirklich? Pace/HF/Leistung im Verhältnis zur Schwelle?",'
            '"naechster_schritt":"Was soll {name} morgen/übermorgen konkret tun?"}}'
        ),
        # TP op labels
        "tp_mod_renamed":       "↩️ {title} (KI)",
        "tp_mod_new_title":     "{title} – Angepasst (KI)",
        "tp_skip_renamed":      "❌ {title} (KI)",
        # Error messages (user-visible)
        "err_tp_url_missing":   "TP_MCP_URL nicht konfiguriert",
        "err_api_key_missing":  "ANTHROPIC_API_KEY nicht gesetzt",
        "err_no_baseline":      "Keine Baseline — bitte zuerst CSVs hochladen",
        "err_claude_json":      "Ungültiges JSON von Claude: {e}",
        "err_weather_na":       "Wetterdaten nicht verfügbar",
        "err_csv_empty":        "CSV ist leer",
    },

    "en": {
        # App
        "app_title":        "AI Coach",
        "splash_sub":       "Triathlon · Daily Coaching",
        # Loading states
        "loading":           "Loading…",
        "loading_data":      "Loading data…",
        "loading_weather":   "Loading weather…",
        "loading_workouts":  "Loading workouts…",
        "refreshing":        "Refreshing data…",
        "ready":             "Ready!",
        # Tabs
        "tab_abend":         "Evening",
        "tab_morgen":        "Morning",
        "tab_analyse":       "Analysis",
        "tab_erholung":      "Recovery",
        "tab_profil":        "Profile",
        "tab_about":         "Info",
        # Section titles
        "sec_tomorrow":      "Tomorrow",
        "sec_today":         "Today",
        "sec_body_evening":  "Body Status This Evening",
        "sec_body_morning":  "Body Status This Morning",
        "sec_athlete":       "Athlete Profile",
        "sec_races":         "Races",
        "sec_baseline":      "Sleep Baseline",
        "sec_baseline_recalc": "Recalculate Baseline",
        "sec_erholung_letzte": "Last Night",
        "sec_erholung_verlauf": "7-Day Trend",
        # Form labels
        "lbl_knie":          "Knee",
        "lbl_achilles_l":    "Achilles L",
        "lbl_achilles_r":    "Achilles R",
        "lbl_waden":         "Calves",
        "lbl_muedigkeit":    "Fatigue",
        "lbl_mud_hint":      "1 = fresh · 5 = exhausted",
        "lbl_muskelkater":   "Muscle Soreness",
        "lbl_symptome":      "Symptoms",
        "lbl_wasser_temp":   "Pool Water Temperature",
        "lbl_optional":      "optional",
        "lbl_no_pain":       "0 — no pain",
        "lbl_max":           "10 — max",
        # CSV upload
        "lbl_csv":           "AutoSleep CSV",
        "lbl_csv_btn":       "Upload CSV",
        "lbl_csv_tap":       "or tap",
        "lbl_csvs_btn":      "Upload CSVs",
        "lbl_csvs_hint":     "multiple possible",
        # TP workouts
        "lbl_tp_tomorrow":   "TP Workouts Tomorrow",
        "lbl_tp_today":      "TP Workouts Today",
        "lbl_tp_loading":    "loading…",
        "tp_no_cfg":         "TP not configured",
        "tp_no_w_tomorrow":  "No workouts in TP for tomorrow",
        "tp_no_w_today":     "No workouts in TP for today",
        "tp_no_w":           "No workouts planned",
        "tp_unreachable":    "TP not reachable",
        "tp_loading_text":   "Loading…",
        # Weather
        "weather_n_a":       "Weather not available",
        # Erholung tab
        "erholung_no_data":      "No sleep data yet — upload an AutoSleep CSV in Morning Check.",
        "erholung_no_baseline":  "No baseline yet — calculate in Profile tab.",
        "erholung_index":        "Recovery Index",
        "erholung_trend":        "HRV Trend",
        "erholung_trend_up":     "↑ Improving",
        "erholung_trend_stable": "→ Stable",
        "erholung_trend_down":   "↓ Declining",
        "erholung_legend_hrv":   "HRV (ms)",
        "erholung_legend_wach":  "AwakeBPM",
        "erholung_legend_ref":   "Flag threshold",
        # Baseline warnings
        "baseline_warning":      "⚠️ For longer periods only (min. 30 nights). For daily check upload CSV in Morning Check.",
        "baseline_nights_warn":  "⚠️ Only {n} nights — baseline should be based on at least 30 nights.",
        # CSV hint
        "csv_morgen_hint":       "Upload last night's CSV (export from AutoSleep app)",
        # Muskelkater pills (label)
        "mk_keine":          "none",
        "mk_waden":          "calves",
        "mk_oberschenkel":   "thighs",
        "mk_beine":          "legs",
        "mk_oberkoerper":    "upper body",
        "mk_ganzkoerper":    "full body",
        # Muskelkater data-values
        "mkv_keine":         "none",
        "mkv_waden":         "calves",
        "mkv_oberschenkel":  "thighs",
        "mkv_beine":         "legs general",
        "mkv_oberkoerper":   "upper body",
        "mkv_ganzkoerper":   "whole body",
        # Symptome pill labels (display)
        "sym_keine":         "none",
        "sym_besser":        "better",
        "sym_gleich_leicht": "same mild",
        "sym_schlechter":    "worse",
        "sym_neu_leicht":    "new mild",
        "sym_neu_mittel":    "new moderate",
        "sym_neu_schwer":    "new severe",
        # Symptome data-values (sent to Claude)
        "symv_keine":        "none",
        "symv_besser":       "better",
        "symv_gleich_leicht":"same mild (runny nose/pressure)",
        "symv_schlechter":   "worse",
        "symv_neu_leicht":   "new mild",
        "symv_neu_mittel":   "new moderate (sore throat/cough)",
        "symv_neu_schwer":   "new severe (fever/body aches)",
        # Buttons
        "btn_abend":         "Start Evening Check",
        "btn_morgen":        "Start Morning Check",
        "btn_save":          "Save",
        "btn_saved":         "✓ Saved",
        "btn_baseline":      "Recalculate Baseline",
        "btn_tp_apply":      "→ Apply to TrainingPeaks",
        "btn_tp_load":       "→ Load TP Workouts",
        "btn_refresh_title": "Refresh",
        "btn_refresh_aria":  "Refresh data",
        # Countdown / header
        "countdown_loading": "Loading…",
        # Profil labels
        "lbl_ftp":           "FTP",
        "lbl_ftp_unit":      "Watts",
        "lbl_weight":        "Weight",
        "lbl_weight_unit":   "kg",
        "lbl_run_thr":       "Run Threshold",
        "lbl_run_thr_unit":  "/km",
        "lbl_css":           "CSS Swimming",
        "lbl_css_unit":      "/100m",
        "lbl_swim_min":      "Outdoor swimming from",
        "lbl_swim_min_unit": "°C",
        # Baseline labels
        "lbl_hrv":           "SleepHRV",
        "lbl_wach_bpm":      "AwakeBPM",
        "lbl_schlaf_bpm":    "SleepBPM",
        "lbl_atmung":        "Breathing",
        "lbl_effizienz":     "Efficiency",
        # JS / dynamic strings
        "err_profile_load":  "Failed to load athlete profile.",
        "err_save":          "Error saving",
        "claude_analyzing":  "Claude is analysing…",
        "tp_applying":       "Applying to TrainingPeaks…",
        # Claude prompts — system
        "prompt_system": (
            "You are the AI Coach for {name}, a long-distance triathlete.\n"
            "A-Race: {a_info} · {weight}kg · FTP {ftp}W · Run {run_thr}/km · CSS {css}/100m\n"
            "{b_text}"
            "BODY SIGNALS — assess like a sports physician, not by rigid thresholds:\n"
            "KNEE: Mild stiffness/fatigue → reduce volume and intensity, no tempo, flat surface. "
            "Pain under load, on stairs or after training → no running, cycling only if pain-free, aquajogging as alternative. "
            "Swelling, instability or pain at rest → full rest. "
            "Knee is sensitive to downhill running and high cadence — when in doubt, be conservative.\n"
            "ACHILLES: Morning stiffness that resolves → adapted training ok, no tempo, soft surface. "
            "Pain on toe raise, under load or thickening of tendon → STOP running, cycling/swimming ok. "
            "Achilles pain often worsens delayed (12-24h) — always conservative when uncertain.\n"
            "CALVES: Precursor to Achilles and soleus issues. "
            "Tightness that resolves during warm-up → shorten run, no tempo. "
            "Pain that persists or worsens under load → no running (cycling/swimming ok). "
            "High calves + high Achilles combined → STOP running.\n"
            "MUSCLE SORENESS: Legs mild → reduce load, no tempo, Z1–Z2 ok. "
            "Legs severe → easy spin max 30min only, no strength/intervals. "
            "Upper body → adapt swimming (technique over power), cycling/running unaffected. "
            "Everywhere → recovery day, light swimming at most. "
            "Muscle soreness is not an injury risk but signals incomplete recovery — throttle intensity accordingly.\n"
            "WEATHER — experienced-trainer knowledge for all three sports:\n"
            "THUNDERSTORM: All outdoor sports stop immediately — running is just as dangerous as cycling. "
            "Open-water swimming during thunderstorm is extremely dangerous (get out immediately). "
            "Cycling → Zwift, running → treadmill/indoor or cancel, swimming → indoor pool if possible, otherwise SKIP.\n"
            "RAIN: Light rain while running ok (cooling effect), slightly lower pace expectations, watch shoe grip. "
            "Heavy rain while running → injury risk from wet surfaces, visibility, hypothermia for >60min → shorten or indoor. "
            "Cycling in rain: wet roads = significantly longer braking distances, slippery corners → recommend Zwift, especially for >60min or tempo sessions. "
            "Swimming in outdoor pool in rain: ok (already wet), during thunderstorm get out immediately.\n"
            "HEAT >25°C: Running — pace slows ~4-5% per degree above 20°C (physiologically proven), train early morning or evening, "
            "strongly reconsider sessions >60min outdoors, no hard intervals at midday. "
            "Cycling — heart rate drifts upward in heat (cardiac drift), regulate by HR/RPE not watts, "
            "seriously consider Zwift at >30°C. "
            "Swimming — benefits from heat (cooling effect in water), outdoor pool optimal; water temperature >28°C can strain during long sessions. "
            "All sports: {fluid_heat}ml/h water, {salt_heat} salt tabs/h, heat symptoms (dizziness, nausea, disorientation) → stop immediately.\n"
            "COLD <10°C: Running — longer warm-up needed (10-15min), muscles need more time, "
            "injury risk increases when starting cold, protect airways (<0°C balaclava). "
            "Cycling outdoor — <10°C hands/feet cool quickly (neoprene/thermal gloves), at <5°C hypothermia risk on long descents, "
            "clearly recommend Zwift at <5°C or rain+cold. "
            "Swimming — switch outdoor pool below {swim_min}°C water temperature to indoor pool, "
            "below 14°C cold shock risk even for trained swimmers.\n"
            "OTHER LIMITS: symptoms new severe→rest\n"
            "SOFT SIGNALS: fatigue ≥4→remove intensity · ignore sleep duration, use HRV+AwakeBPM\n"
            "Nutrition from 90min: {carbs}g/h+{salt} salt/h; heat>{heat_thr}°C: {fluid_heat}ml+{salt_heat}x salt/h\n"
            "DECISION RULE: Always make a clear decision — GO, MOD or STOP. "
            "Never ask the athlete questions. "
            "When multiple options are possible, choose the more conservative one. "
            "For MOD: name the concrete adjustment (distance, zone, alternative), do not list both options.\n\n"
            "WORKOUT DESCRIPTION for TrainingPeaks (field 'beschreibung'):\n"
            "For GO: Copy the original workout description from the TrainingPeaks context exactly as-is — do not change a word.\n"
            "For MOD with original description available: Take the EXACT ORIGINAL TEXT and change ONLY the specific values that need adjusting. "
            "Keep the sentence structure, format, and all other lines of the original. "
            "Append a short line at the end with the adjustment reason + measures (e.g. 'HEAT: 750ml/h, 2× Saltstick/h — timing ≤09:00 or from 19:00').\n"
            "Example: Original '35 min very easy (6:15–6:45/km, HR cap 150 bpm)' → "
            "MOD '35 min very easy (6:30–7:05/km, HR cap 145 bpm) [heat adjustment]'\n"
            "For MOD without original description (empty description field): Create a complete, immediately actionable workout structure based on title, sport and duration — no placeholder text.\n"
            "If the adjustment is so fundamental that the original content is completely obsolete "
            "(e.g. interval session → recovery day): first line '⚠️ Einheit komplett umgestellt', then new description.\n"
            "NEVER invent a new warm-up/main set/cool-down structure if the original does not have one.\n"
            "Sport-specific terms: Swimming → Einschwimmen/Ausschwimmen, Cycling → Einrollen/Ausrollen, Running → Einlaufen/Auslaufen.\n"
            "Swim workouts (MOD): calculate total distance as sum of ALL blocks (Einschwimmen + main set meters + Ausschwimmen). "
            "Write total as first line (e.g. 'Total: ~1500m'). All sub-blocks must add up to the total.\n"
            "Run/Bike MOD without original description: write complete structure with warm-up, main set "
            "(reps × duration/distance with specific pace/watt target), cool-down.\n"
            "Heat/cold adjustment: write HEAT or COLD as first word in the adjustment-detail line.\n\n"
            "TP STRUCTURE (optional field 'tp_struktur', only for MOD with real interval blocks — NOT for pure endurance):\n"
            "Bike → primaryIntensityMetric:'percentOfFtp', Run/Swim → 'percentOfThresholdPace'\n"
            "Intensity % of threshold: WarmUp/CoolDown=50-60, Z1=55-65, Z2=65-75, Z3=80-90, Z4=95-105, Z5=106-120\n"
            "intensityClass values: 'warmUp'|'active'|'rest'|'coolDown'\n"
            "Single step: {{\"name\":\"...\",\"duration_seconds\":N,\"intensity_min\":X,\"intensity_max\":Y,\"intensityClass\":\"active\"}}\n"
            "Repetition block: {{\"type\":\"repetition\",\"reps\":N,\"steps\":[...]}}\n"
            "Swim MOD: set field 'distanz_m' with total distance in meters.\n\n"
            "Respond ONLY as JSON (no markdown):\n"
            '{{"status":"green","status_text":"All clear","sportarten":['
            '{{"sport":"Bike","badge":"MOD",'
            '"details":"1-2 sentences coach hint",'
            '"beschreibung":"Einrollen: 10min\\n- 4×8min FTP (95-105%), 2min rest\\n- Ausrollen: 10min",'
            '"ernaehrung":"...",'
            '"tp_struktur":{{"steps":['
            '{{"name":"Warm-up","duration_seconds":600,"intensity_min":50,"intensity_max":60,"intensityClass":"warmUp"}},'
            '{{"type":"repetition","reps":4,"steps":['
            '{{"name":"FTP","duration_seconds":480,"intensity_min":95,"intensity_max":105,"intensityClass":"active"}},'
            '{{"name":"Rest","duration_seconds":120,"intensity_min":40,"intensity_max":50,"intensityClass":"rest"}}'
            ']}},'
            '{{"name":"Cool-down","duration_seconds":600,"intensity_min":45,"intensity_max":55,"intensityClass":"coolDown"}}'
            '],"primaryIntensityMetric":"percentOfFtp"}}'
            '}}],"autosleep_summary":null,"wetter_hinweis":"...","prep":"..."}}'
        ),
        "prompt_system_baseline": (
            "\nBaseline ({nights} nights, as of {updated}):"
            "\n  SleepHRV: Median {hrv_med}ms, flag ≤{hrv_flag}ms"
            "\n  AwakeBPM: Median {wach_med}, flag ≥{wach_flag}"
            "\n  SleepBPM: Median {schlaf_med}, flag ≥{schlaf_flag}"
        ),
        "prompt_abend_header":   "Evening Check — Plan for tomorrow ({date}):",
        "prompt_morgen_header":  "Morning Check — Go/No-Go for today ({date}):",
        "prompt_abend_units":    "Planned sessions tomorrow: {units}",
        "prompt_abend_units_empty": "not yet defined — please recommend",
        "prompt_morgen_units":   "Planned sessions today: {units}",
        "prompt_morgen_units_empty": "not yet defined",
        "prompt_weather_label":  "Weather tomorrow in {city}:",
        "prompt_weather_today":  "Weather today in {city}:",
        "prompt_weather_thunderstorm": "YES",
        "prompt_weather_no":     "no",
        "prompt_weather_heat":   "YES",
        "prompt_autosleep_header": "AutoSleep (last night):",
        "prompt_autosleep_flags_ok": "all markers ok",
        "prompt_autosleep_err":  "AutoSleep error: {err}",
        "prompt_wasser":         "Pool water temperature: {temp}°C",
        "prompt_tp_ctx":         "TrainingPeaks planned workouts tomorrow: {data}",
        "prompt_rain_peaks":     "Rain peaks: {peaks}",
        "prompt_heat_alarm":     "Heat alert (>{threshold}°C): {val}",
        # TP apply prompts (keep German for TP op details)
        "tp_apply_prompt_intro":  "Apply the following changes to TrainingPeaks for '{name}' on {date}.",
        "tp_apply_prompt_sem":    (
            "Operation semantics:\n"
            "- rename_workout: Use workout_id (if provided) to find and rename; fallback to old_title match\n"
            "- create_workout: Create a new planned workout with title, sport, duration_min and note\n\n"
            "After completing all operations respond ONLY with a JSON array (no markdown):\n"
            '[{{"action":"rename_workout","status":"ok","detail":"Renamed to ↩️ Z2 Endurance (AI)"}}]\n'
            "Use status 'ok' or 'error'."
        ),
        "tp_workouts_prompt": (
            "List all planned workouts for {name} on {date} from TrainingPeaks. "
            "Respond ONLY with a valid JSON array with these fields: id, sport, title, duration_min, tss. "
            "Example: "
            '[{{"id":"123","sport":"Swim","title":"Pool Z2","duration_min":45,"tss":30}}]'
        ),
        "tp_history_prompt": (
            "List all workouts (planned and completed) for {name} from {start} to {end} from TrainingPeaks. "
            "Group by date. Respond ONLY with a valid JSON array. Example: "
            '[{{"date":"2026-06-20","workouts":[{{"id":"123","sport":"Swim","title":"Pool Z2","duration_min":45,"tss":30,"start_time":"2026-06-20T07:15:00"}}]}}] '
            "start_time is the actual start time of the completed workout (ISO 8601, local time) if available — omit if not. "
            "Only include days that have workouts. Oldest date first."
        ),
        "tp_completed_prompt": (
            "Use the available TrainingPeaks tools to retrieve the workout \"{title}\" for {name} on {date}. "
            "Workout ID: {workout_id}, Sport: {sport}. "
            "Use the tool to fetch ALL available data: both planned and actual execution data. "
            "Then output a detailed summary of all fields the tool returned: "
            "duration (planned/actual), distance, heart rate (avg, max), "
            "power (avg, max, cycling only), pace (avg, run/swim only), TSS (planned/actual), "
            "zone distribution, notes, status (completed/planned). "
            "Write out the raw tool data completely in plain text with all values — no JSON."
        ),
        "coach_analysis_prompt": (
            "Execute the following two steps:\n\n"
            "STEP 1: Use the TrainingPeaks tools to retrieve the workout:\n"
            "- Title: \"{title}\"\n"
            "- Date: {date}\n"
            "- Sport: {sport}\n"
            "- Workout ID: {workout_id}\n"
            "Fetch all available data: duration, distance, HR (avg/max), power (avg/max), "
            "pace (avg), TSS, zone distribution, notes.\n\n"
            "STEP 2: Analyze as an experienced triathlon coach ({name}, FTP {ftp}W, "
            "run threshold {run_threshold}/km, CSS {css}/100m, "
            "A-race: {race_name} on {race_date}, goal {race_goal}h):\n"
            "Was this session well executed? Direct, honest, no platitudes.\n\n"
            "Respond ONLY as JSON:\n"
            '{{"bewertung":"gut|ok|verbesserungsbedarf",'
            '"urteil":"3-4 direct sentences: How was the session really? Pace/HR/power vs threshold?",'
            '"naechster_schritt":"What should {name} concretely do tomorrow/the day after?"}}'
        ),
        # TP op labels
        "tp_mod_renamed":       "↩️ {title} (AI)",
        "tp_mod_new_title":     "{title} – Adjusted (AI)",
        "tp_skip_renamed":      "❌ {title} (AI)",
        # Error messages (user-visible)
        "err_tp_url_missing":   "TP_MCP_URL not configured",
        "err_api_key_missing":  "ANTHROPIC_API_KEY not set",
        "err_no_baseline":      "No baseline — please upload CSVs first",
        "err_claude_json":      "Invalid JSON from Claude: {e}",
        "err_weather_na":       "Weather data unavailable",
        "err_csv_empty":        "CSV is empty",
    },
}
