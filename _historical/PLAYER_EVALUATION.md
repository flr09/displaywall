# Player-Evaluation: Dual-Display auf Raspberry Pi 5

Stand: 2026-04-10

## Problem

Anthias (Screenly OSE) kann nur **ein Display pro Pi** ansteuern. Fuer 6 Monitore an 3 Pis brauchen wir eine Loesung, die 2 Displays pro Pi mit unterschiedlichem Inhalt bespielen kann.

## Technische Analyse: Warum Anthias nur 1 Display kann

Anthias nutzt auf dem Pi 5 zwei Rendering-Pfade:
- **Bilder/Web:** `ScreenlyWebview` (Qt5/Qt6 WebView) — ein einzelnes Vollbild-Fenster
- **Video:** `mpv --no-terminal --vo=drm` — Direct Rendering Manager, schreibt direkt auf den Framebuffer

Das Problem liegt bei `--vo=drm`: DRM-Output umgeht den Compositor (labwc) komplett und kann nur **ein CRTC/Display** gleichzeitig nutzen.

**Aber:** mpv im Anthias-Container unterstuetzt auch:
- `--vo=gpu --gpu-context=wayland` (Wayland-faehig, Window-Rules moeglich)
- `--vo=dmabuf-wayland` (effizienter Wayland DMA-Buffer)
- `--fs-screen=N` (Fullscreen auf bestimmtem Display)

Das heisst: Die Hardware und Software **kann** Dual-Display — es ist eine Konfigurationsfrage, kein fundamentales Limit.

## Bewertete Optionen

### Option A: Anthias modifizieren (2x Viewer-Instanz)

**Konzept:** Zwei Anthias-Viewer-Container parallel starten, jeden auf ein anderes Display pinnen.

**Aenderungen noetig:**
1. `media_player.py`: `--vo=drm` ersetzen durch `--vo=gpu --gpu-context=wayland`
2. `docker-compose.yml`: Zweiten Viewer-Container mit eigener Konfiguration
3. labwc `rc.xml`: Window-Rules um ScreenlyWebview und mpv auf HDMI-A-1 bzw. HDMI-A-2 zu pinnen
4. Anthias-Server: Zweite Playlist/Asset-Zuweisung pro Display

**Risiko:** Labwc Window-Rules fuer mpv funktionieren laut Community-Berichten, fuer VLC nicht. Da Anthias auf Pi 5 mpv nutzt, sollte es gehen. Aber: ungetestet, kein offizieller Support.

**Aufwand:** Mittel. Fork von Anthias, Docker-Anpassung, Testing.

**Vorteil:** Kostenlos, bestehende Infrastruktur wiederverwendbar.

### Option B: Screenly (kommerziell)

**Website:** https://www.screenly.io/

Screenly ist die kommerzielle Version hinter Anthias. Nutzt die gleiche Codebasis, aber gehostet.

- **Dual-Display:** Nein. Screenly erfordert explizit **1 Player pro Screen**.
- **Kosten:** $17-27/Screen/Monat. Bei 6 Screens: $102-162/Monat laufend.
- **Self-Hosted:** Nein, nur Cloud.
- **Vorteil:** Professioneller Support, 4K, zentrale Verwaltung.
- **Fazit:** Loest das Dual-Display-Problem nicht, und ist teuer. Nur relevant wenn man bereit ist, 6 Pis zu verwenden.

### Option C: PiSignage

- **Website:** https://pisignage.com/
- **GitHub:** https://github.com/colloqi/piSignage (Player), https://github.com/colloqi/pisignage-server (Server)
- **Dual-Display:** Ja, ab Version 5.3.2. Pi 5 unterstuetzt. Zwei Displays koennen unterschiedliche Inhalte zeigen ("Tile Configuration").
- **ARM64:** Ja, Version 5.4.3 basiert auf 64-bit Raspberry Pi OS (Dez 2025).
- **Zentrale Verwaltung:** Ja. Open-Source-Server (Node.js + MongoDB) self-hosted. Head-Pi kann den Server hosten.
- **Kosten:** 3 Player-Lizenzen gratis bei Registrierung. Weitere einmalig $25/Stueck. Self-Hosted-Server kostenlos.
- **Gruppen:** Ja, Displays koennen in Gruppen organisiert werden.
- **Offline-faehig:** Ja, cached Inhalte lokal.
- **Einschraenkung:** UI des Open-Source-Servers einfacher als Cloud-Version.

### Option D: info-beamer

- **Website:** https://info-beamer.com/
- **Dual-Display:** Ja, auch Video-Wall-Sync ueber mehrere Pis.
- **ARM64:** Ja, Pi 5 unterstuetzt.
- **Zentrale Verwaltung:** Nur ueber info-beamer Cloud.
- **Kosten:** 1 Geraet gratis. Danach 0.25 EUR/Tag/Geraet. Bei 6 Displays: ~45 EUR/Monat.
- **Self-Hosted:** Nein.
- **Sync:** Perfekter Frame-Sync — bestes Sync-Feature aller Optionen.
- **Einschraenkung:** Laufende Kosten, Cloud-Abhaengigkeit.

### Option E: Arexibo (Xibo-Player in Rust)

- **GitHub:** https://github.com/birkenfeld/arexibo
- **Status:** "Still incomplete." Letzte Commits Mai 2025.
- **Dual-Display:** Nicht dokumentiert.
- **Fazit:** Nicht produktionsreif.

## Empfehlung

### Fuer den Kunden (kommerziell, zuverlaessig)

**PiSignage (Option C):** Einzige Loesung mit nativem Dual-Display, Self-Hosted-Server, und ueberschaubaren Einmalkosten ($75 max). Sofort einsatzbereit.

Falls Frame-Sync ueber die Wand kritisch ist: **info-beamer (Option D)**, aber mit laufenden Kosten.

Falls Budget fuer 6 Pis vorhanden: **Screenly (Option B)**, professioneller Cloud-Service.

### Fuer uns (experimentell, kostenlos)

**Anthias modifizieren (Option A):** Die Codebasis erlaubt es. mpv kann Wayland, labwc kann Window-Rules. Der Aufwand ist ueberschaubar:
1. `media_player.py` Zeile mit `--vo=drm` aendern
2. Zweiten Viewer-Container konfigurieren
3. labwc Window-Rules testen

Das waere ein spannender Test, der bei Erfolg die kostenlose Loesung fuer Dual-Display liefert.

## Verworfene Ansaetze

| Option | Grund | Geprueft |
|--------|-------|----------|
| Xibo CMS + Snap Player | Player nicht fuer ARM64 verfuegbar | `snap info xibo-player` April 2026 |
| Arexibo | Experimentell, unvollstaendig, kein Multi-Display | GitHub README April 2026 |
| Screenly (kommerziell) | 1 Player pro Screen Pflicht, kein Dual-Display, teuer | screenly.io/pricing April 2026 |
| DIY Chromium Kiosk | labwc Window-Rules fuer Chromium unzuverlaessig laut Community | RPi Forums 2025/2026 |

## Quellen

- Anthias Viewer Source: `/home/head/screenly/viewer/media_player.py` (Pi, geprueft per SSH)
- mpv Capabilities: `docker exec screenly-anthias-viewer-1 mpv --vo=help` (geprueft per SSH)
- PiSignage Dual-Display: https://help.pisignage.com/hc/en-us/articles/21655587985433
- Screenly Pricing: https://www.screenly.io/pricing/
- Anthias Multi-Screen Issue: https://forums.screenly.io/t/multiscreen-output/1402
- Anthias Dual Screen Bug: https://github.com/Screenly/Anthias/issues/1539
- info-beamer Pricing: https://info-beamer.com/pricing
- RPi Forum Wayfire Dual Display: https://forums.raspberrypi.com/viewtopic.php?t=370279
- RPi Forum mpv Multi-Monitor: https://forums.raspberrypi.com/viewtopic.php?t=384876
