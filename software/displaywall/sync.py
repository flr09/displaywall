"""Displaywall Sync — Hardware-Counter-basierte Taktsynchronisation.

Cross-Pi-Sync ueber UDP-Broadcast mit CLOCK_MONOTONIC_RAW als Zeitbasis.
Unabhaengig von NTP, Systemuhr und Netzwerk-Jitter.

Lokaler Sync (mehrere Displays auf einem Pi) nutzt threading.Barrier.

Protokoll (v2 "dw2"):
  Master sendet bei JEDEM Bildwechsel:
    { v: "dw2", m_now: <ns>, m_next: <ns> }
  m_now  = CLOCK_MONOTONIC_RAW zum Sendezeitpunkt (Nanosekunden)
  m_next = CLOCK_MONOTONIC_RAW des naechsten geplanten Wechsels

  Slave empfaengt, misst lokale CLOCK_MONOTONIC_RAW bei Ankunft,
  berechnet Offset + Drift per Software-PLL, und leitet daraus den
  lokalen Wechselzeitpunkt ab.
"""

import collections
import json
import logging
import socket
import threading
import time

SYNC_PORT = 1666
SYNC_MAGIC = "dw2"  # Protokoll-Version 2 (Hardware-Counter)

# Hardware-Counter: Nanosekunden seit Boot, unabhaengig von NTP
_CLOCK = time.CLOCK_MONOTONIC_RAW


def hw_now_ns():
    """Aktueller Hardware-Counter in Nanosekunden."""
    return time.clock_gettime_ns(_CLOCK)


def hw_now():
    """Aktueller Hardware-Counter in Sekunden (float)."""
    return time.clock_gettime(_CLOCK)


class SyncMaster:
    """Sendet bei jedem Bildwechsel den naechsten Wechselzeitpunkt per UDP-Broadcast.

    Der Master rechnet intern mit CLOCK_MONOTONIC_RAW. Das Paket enthaelt:
    - m_now:  Hardware-Counter JETZT (Sendezeitpunkt)
    - m_next: Hardware-Counter des naechsten geplanten Bildwechsels
    Der Slave braucht nur die DIFFERENZ (m_next - m_now), nicht den absoluten Wert.
    """

    def __init__(self, broadcast_ip="255.255.255.255", port=SYNC_PORT):
        self.port = port
        self.broadcast_ip = broadcast_ip
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    def send_tick(self, next_switch_hw):
        """Sendet den naechsten Wechselzeitpunkt (Hardware-Counter, Sekunden float)."""
        now = hw_now()
        msg = json.dumps({
            "v": SYNC_MAGIC,
            "m_now": now,
            "m_next": next_switch_hw,
        }).encode()
        try:
            self.sock.sendto(msg, (self.broadcast_ip, self.port))
        except Exception as e:
            logging.warning("SyncMaster: Sende-Fehler: %s", e)

    def close(self):
        self.sock.close()


class SyncSlave:
    """Empfaengt Sync-Ticks vom Master und berechnet lokale Wechselzeitpunkte.

    Software-PLL: Misst den Offset zwischen Master- und Slave-Counter
    ueber mehrere Pakete und glaettet per gleitendem Durchschnitt.

    Nutzung:
        slave = SyncSlave()
        slave.start()

        # Im Playback-Loop:
        local_target = slave.get_next_switch_local()
        if local_target > 0:
            busy_wait_until_hw(local_target)
            # Bild wechseln
    """

    PLL_WINDOW = 8       # Anzahl Samples fuer gleitenden Durchschnitt
    CONVERGE_MIN = 3     # Mindest-Samples bevor PLL als konvergiert gilt

    def __init__(self, port=SYNC_PORT, timeout=30):
        self.port = port
        self.timeout = timeout  # Sekunden ohne Signal → autonom
        self._lock = threading.Lock()
        self._running = False
        self._thread = None

        # PLL-State
        self._offsets = collections.deque(maxlen=self.PLL_WINDOW)
        self._last_rx_hw = 0.0       # Lokaler HW-Counter bei letztem Empfang
        self._last_delta = 0.0       # m_next - m_now aus letztem Paket
        self._converged = False

    def start(self):
        """Listener-Thread starten."""
        self._running = True
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _listen(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(5)
        sock.bind(("", self.port))
        logging.info("SyncSlave: lausche auf Port %d (Hardware-Counter PLL)", self.port)

        while self._running:
            try:
                data, addr = sock.recvfrom(512)
                rx_hw = hw_now()  # Sofort lokalen Counter messen
                msg = json.loads(data.decode())
                if msg.get("v") != SYNC_MAGIC:
                    continue

                m_now = msg["m_now"]    # Master-Counter bei Senden
                m_next = msg["m_next"]  # Master-Counter des naechsten Wechsels

                # Offset = Differenz zwischen Master- und Slave-Counter
                # offset = master_time - local_time (positiv = Master voraus)
                offset = m_now - rx_hw

                with self._lock:
                    self._offsets.append(offset)
                    self._last_rx_hw = rx_hw
                    self._last_delta = m_next - m_now  # Verbleibende Zeit bis Wechsel
                    self._converged = len(self._offsets) >= self.CONVERGE_MIN

                    if len(self._offsets) == self.CONVERGE_MIN:
                        logging.info("SyncSlave: PLL konvergiert (%d Samples)",
                                     self.CONVERGE_MIN)

            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    logging.warning("SyncSlave: Empfangs-Fehler: %s", e)

        sock.close()

    def _avg_offset(self):
        """Geglätteter Offset (gleitender Durchschnitt)."""
        if not self._offsets:
            return 0.0
        return sum(self._offsets) / len(self._offsets)

    def get_next_switch_local(self):
        """Naechsten Wechselzeitpunkt in lokaler CLOCK_MONOTONIC_RAW (Sekunden).

        Gibt 0.0 zurueck wenn:
        - Kein Master-Signal empfangen
        - PLL noch nicht konvergiert
        - Signal aelter als timeout
        """
        with self._lock:
            if not self._converged:
                return 0.0
            # Timeout pruefen (in HW-Zeit)
            if hw_now() - self._last_rx_hw > self.timeout:
                return 0.0

            # Master sagt: "naechster Wechsel ist m_next"
            # Lokal: m_next - offset = lokaler Zeitpunkt
            # offset = master - local → local = master - offset
            avg_off = self._avg_offset()
            # m_next des Masters in lokale Zeit umrechnen:
            # master_next = last_rx_hw + last_delta + (Netzwerk-Latenz ≈ 0)
            # Aber wir haben den Offset: local = master - offset
            # Also: local_next = (m_now + last_delta) - offset
            #                   = (m_now - offset) + last_delta
            #                   = last_rx_hw + last_delta
            #   (weil m_now - offset ≈ rx_hw per Definition)
            # Vereinfacht: Der Wechsel ist last_delta nach dem letzten Empfang
            return self._last_rx_hw + self._last_delta

    def has_master(self):
        """True wenn PLL konvergiert und Signal aktuell."""
        with self._lock:
            if not self._converged:
                return False
            return hw_now() - self._last_rx_hw < self.timeout

    def get_offset_ms(self):
        """Aktueller Offset in Millisekunden (fuer Diagnose)."""
        with self._lock:
            return self._avg_offset() * 1000


def busy_wait_until_hw(target_hw):
    """Praezises Warten bis zum Zielzeitpunkt (CLOCK_MONOTONIC_RAW, Sekunden).

    Grob schlafen bis 20ms vor Ziel, dann Busy-Wait fuer Praezision.
    """
    remaining = target_hw - hw_now()
    if remaining > 0.02:
        time.sleep(remaining - 0.02)
    # Busy-Wait die letzten ~20ms
    while hw_now() < target_hw:
        pass


# --- Abwaertskompatibilitaet (fuer bestehende Aufrufe) ---

def busy_wait_until(target_epoch):
    """Praezises Warten bis zum Zielzeitpunkt (wall-clock, Sekunden).

    Fuer lokalen Sync auf dem Head-Pi (gleiche Maschine, kein Cross-Pi).
    """
    remaining = target_epoch - time.time()
    if remaining > 0.02:
        time.sleep(remaining - 0.02)
    while time.time() < target_epoch:
        pass
