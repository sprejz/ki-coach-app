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
        "tab_abend":         "Abend-Check",
        "tab_morgen":        "Morgen-Check",
        "tab_profil":        "Profil",
        # Section titles
        "sec_tomorrow":      "Morgen",
        "sec_today":         "Heute",
        "sec_body_evening":  "Körperzustand heute Abend",
        "sec_body_morning":  "Körperzustand heute Morgen",
        "sec_athlete":       "Athletenprofil",
        "sec_races":         "Rennen",
        "sec_baseline":      "Schlaf-Baseline",
        "sec_baseline_recalc": "Baseline neu berechnen",
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
            "{pain_rules}\n"
            "SONSTIGE GRENZEN: Symptome neu schwer→Ruhe · Gewitter→kein Outdoor-Rad (Zwift 75%)\n"
            "WEICHE SIGNALE: Müdigkeit ≥4→Intensität raus · Schlafdauer ignorieren, primär HRV+WachBPM\n"
            "Ernährung ab 90min: {carbs}g/h+{salt} Saltstick/h; Hitze>{heat_thr}°C: {fluid_heat}ml+{salt_heat}x Saltstick/h\n\n"
            "Antworte NUR als JSON (kein Markdown):\n"
            '{{"status":"green","status_text":"Alles grün","sportarten":[{{"sport":"Schwimmen","badge":"GO","details":"...","ernaehrung":"..."}}],"autosleep_summary":null,"wetter_hinweis":"...","prep":"..."}}'
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
            "Antworte NUR mit einem gültigen JSON-Array. Beispiel: "
            '[{{"id":"123","sport":"Rad","title":"Z2 Ausdauer","duration_min":90,"tss":65,"description":"60-70% FTP"}}]'
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
        "tab_abend":         "Evening Check",
        "tab_morgen":        "Morning Check",
        "tab_profil":        "Profile",
        # Section titles
        "sec_tomorrow":      "Tomorrow",
        "sec_today":         "Today",
        "sec_body_evening":  "Body Status This Evening",
        "sec_body_morning":  "Body Status This Morning",
        "sec_athlete":       "Athlete Profile",
        "sec_races":         "Races",
        "sec_baseline":      "Sleep Baseline",
        "sec_baseline_recalc": "Recalculate Baseline",
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
            "{pain_rules}\n"
            "OTHER LIMITS: symptoms new severe→rest · thunderstorm→no outdoor cycling (Zwift 75%)\n"
            "SOFT SIGNALS: fatigue ≥4→remove intensity · ignore sleep duration, use HRV+AwakeBPM\n"
            "Nutrition from 90min: {carbs}g/h+{salt} salt/h; heat>{heat_thr}°C: {fluid_heat}ml+{salt_heat}x salt/h\n\n"
            "Respond ONLY as JSON (no markdown):\n"
            '{{"status":"green","status_text":"All clear","sportarten":[{{"sport":"Schwimmen","badge":"GO","details":"...","ernaehrung":"..."}}],"autosleep_summary":null,"wetter_hinweis":"...","prep":"..."}}'
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
            "Respond ONLY with a valid JSON array. Example: "
            '[{{"id":"123","sport":"Rad","title":"Z2 Endurance","duration_min":90,"tss":65,"description":"60-70% FTP"}}]'
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
