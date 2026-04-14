"""Displaywall Sync — UDP-basierte Taktsynchronisation zwischen Pis.

Der Head-Pi ist Sync-Master und sendet per UDP-Broadcast den Zeitpunkt
des naechsten Bildwechsels. Slaves empfangen den Takt und steuern ihre
lokalen mpv-Instanzen entsprechend.

Voraussetzung: Systemuhren aller Pis sind per NTP synchronisiert (<1ms).
Fallback: Slaves laufen autonom weiter wenn kein Sync-Signal kommt.
"""

import json
import logging
import socket
import threading
import time

SYNC_PORT = 1666
SYNC_MAGIC = "dw1"  # Protokoll-Version


class SyncMaster:
    """Sendet den Zeitpunkt des naechsten Bildwechsels per UDP-Broadcast."""

    def __init__(self, broadcast_ip="255.255.255.255", port=SYNC_PORT):
        self.port = port
        self.broadcast_ip = broadcast_ip
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    def send_tick(self, next_switch_epoch):
        """Sendet den naechsten Wechselzeitpunkt (epoch float) an alle Slaves."""
        msg = json.dumps({
            "v": SYNC_MAGIC,
            "t": next_switch_epoch,   # Wann naechster Wechsel (epoch)
            "now": time.time(),       # Absende-Zeitpunkt (fuer Latenz-Check)
        }).encode()
        try:
            self.sock.sendto(msg, (self.broadcast_ip, self.port))
        except Exception as e:
            logging.warning("SyncMaster: Sende-Fehler: %s", e)

    def close(self):
        self.sock.close()


class SyncSlave:
    """Empfaengt Sync-Ticks vom Master und stellt den naechsten Wechselzeitpunkt bereit.

    Nutzung:
        slave = SyncSlave()
        slave.start()
        # Im Playback-Loop:
        t = slave.get_next_switch()
        if t > 0:
            # Warte bis t, dann Bild wechseln
    """

    def __init__(self, port=SYNC_PORT, timeout=30):
        self.port = port
        self.timeout = timeout  # Nach N Sekunden ohne Signal: autonom
        self.next_switch = 0.0
        self.last_received = 0.0
        self._lock = threading.Lock()
        self._running = False
        self._thread = None

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
        logging.info("SyncSlave: lausche auf Port %d", self.port)

        while self._running:
            try:
                data, addr = sock.recvfrom(512)
                msg = json.loads(data.decode())
                if msg.get("v") != SYNC_MAGIC:
                    continue
                with self._lock:
                    self.next_switch = msg["t"]
                    self.last_received = time.time()
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    logging.warning("SyncSlave: Empfangs-Fehler: %s", e)

        sock.close()

    def get_next_switch(self):
        """Gibt den naechsten Wechselzeitpunkt zurueck (epoch), oder 0 wenn kein Signal."""
        with self._lock:
            # Pruefen ob Signal noch aktuell
            if time.time() - self.last_received > self.timeout:
                return 0.0
            return self.next_switch

    def has_master(self):
        """True wenn innerhalb des Timeouts ein Sync-Signal empfangen wurde."""
        with self._lock:
            return time.time() - self.last_received < self.timeout


def busy_wait_until(target_epoch):
    """Praezises Warten bis zum Zielzeitpunkt. Grob schlafen + Busy-Wait."""
    remaining = target_epoch - time.time()
    if remaining > 0.02:
        time.sleep(remaining - 0.02)
    # Busy-Wait die letzten ~20ms
    while time.time() < target_epoch:
        pass
