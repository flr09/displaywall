# Video Wall Synchronisation (Sync-Optionen)

Ein kritischer Aspekt bei einer Videowall aus mehreren Bildschirmen ist die synchrone Wiedergabe der Video-Inhalte, sodass schnelle Bewegungen nicht an den Monitorgrenzen "zerreißen" (Tearing/Frame-Drop).

Da wir 3 unabhängige Raspberry Pi 5 Systeme nutzen, müssen diese über das Netzwerk sekundengenau synchronisiert werden.

## Warum alte Tools (`omxplayer-sync`) nicht mehr funktionieren

Früher war das Tool [omxplayer-sync](https://github.com/turingmachine/omxplayer-sync) der Goldstandard für Raspberry Pi Installationen in Museen.
**Dieses Tool ist auf dem Raspberry Pi 5 nicht mehr lauffähig:**
1. **Kein OpenMAX (omx):** Der Pi 5 besitzt die alte Hardware-Schnittstelle `OpenMAX IL` nicht mehr im Grafikchip.
2. **Kein `omxplayer`:** Der Player lässt sich unter dem aktuellen Debian "Bookworm" Betriebssystem nicht installieren.
3. **Wayland statt X11/Framebuffer:** Die direkte, rohe Bildausgabe auf den Framebuffer wird vom neuen Wayland-Compositor blockiert. Standard ist nun GStreamer oder VLC.

## Unsere Lösungsansätze

### 1. Xibo Sync Groups (Die gewählte Software-Lösung)
Wir nutzen die integrierte Funktion von **Xibo CMS (v4+)**.
* **Konzept:** Das Master-Video wird am PC in 3 Teile geschnitten (für jeden Pi ein Video). Im CMS wird eine "Sync Group" erstellt. Der "Head-Pi" wird als Lead (Master) definiert, die beiden Client-Pis als Follower (Slaves).
* **Technik:** Der Xibo-Player nutzt unter der Haube GStreamer und koordiniert den Start-Timestamp über das lokale Netzwerk (via TCP und NTP).
* **Vorteil:** Kostenlos, direkt in unser Setup integriert.
* **Nachteil:** Software-Sync über Netzwerk hat immer minimale Latenzen (sub-8ms). Bei extrem schnellen Kameraschwenks kann es zu winzigen Rucklern an den Bildrändern kommen.
* **WICHTIG:** Für bestmögliche Ergebnisse müssen alle Pis per **LAN-Kabel** an denselben Gigabit-Switch angeschlossen sein. WLAN ist für perfekten Sync oft zu unzuverlässig (Jitter).

### 2. Hardware Video Wall Controller (Der Plan B)
Falls die Software-Lösung von Xibo visuell nicht ausreicht.
* **Konzept:** Wir verwerfen die beiden Client-Pis. Der "Head-Pi" spielt ein einziges, riesiges 4K-Video ab. Das HDMI-Kabel geht in einen externen Hardware-Controller (z.B. 2x3 Video Wall Controller, ca. 100-200 €).
* **Technik:** Die Hardware-Box zerschneidet das Bildsignal in Echtzeit und verteilt es auf die 6 Monitore.
* **Vorteil:** Perfekter, Frame-genauer Sync (0 ms Versatz). Es sieht aus wie aus einem Guss (ähnlich MadMapper).
* **Nachteil:** Zusätzliche Hardware-Kosten.

### 3. Spezifische Signage-OS (z.B. info-beamer)
* **Konzept:** Ein komplett eigenes, minimales Betriebssystem (ersetzt Raspberry Pi OS und Xibo), das extrem tiefgreifend auf Pi-Hardware-Sync optimiert ist.
* **Nachteil:** Laufende Lizenzkosten (Abo-Modell).
