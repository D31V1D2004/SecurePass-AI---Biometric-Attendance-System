# lidar_engine.py  —  Rulează pe Laptop (client TCP)
# =====================================================
# Se conectează la lidar_server.py de pe Raspberry Pi 5
# și primește date LiDAR în timp real prin rețea.
#
# Configurare: setează LIDAR_SERVER_IP cu IP-ul RPi5.
# Rulează pe RPi: hostname -I  pentru a vedea IP-ul.

import socket
import threading
import json
import time
import logging

logging.basicConfig(
    level=logging.INFO,
    format="[LIDAR-ENGINE] %(asctime)s — %(message)s",
    datefmt="%H:%M:%S"
)

# Configurare conexiune
LIDAR_SERVER_IP   = "192.168.1.132"   # <-- INLOCUIESTE cu IP-ul RPi5 (hostname -I)
LIDAR_SERVER_PORT = 65432
RECONNECT_DELAY   = 3.0               # secunde intre incercari de reconectare

# Limite validare prezenta
MIN_DISTANCE = 0.1   # metri — prea aproape
MAX_DISTANCE = 1.0   # metri — prea departe


class LidarEngine:
    """
    Client LiDAR pentru aplicația de marcare a prezenței.

    Primește date de la lidar_server.py (Raspberry Pi 5) prin TCP.
    Rulează un thread de background care menține conexiunea și
    actualizează continuu datele de scan.

    Utilizare în main.py:
        self.lidar = LidarEngine()
        self.lidar.connect()          # pornește thread-ul de fundal

        # în _update():
        dist = self.lidar.get_distance()
        ok   = self.lidar.validate_presence()
        pts  = self.lidar.get_points()
    """

    def __init__(self):
        self._lock           = threading.Lock()
        self._points         = []       # lista de puncte din ultimul scan
        self._front_distance = None     # distanta frontala in metri
        self._sigma_mm       = None     # deviatia standard a profunzimii (liveness)
        self._is_valid       = False    # validare completa (distanta + liveness) de pe server
        self._reason         = "no_object"  # motivul validarii/invalidarii
        self._speed          = 0.0      # viteza de rotatie grade/sec
        self._timestamp      = 0        # ms, timestamp ultimul pachet
        self._connected      = False
        self._running        = False
        self._thread         = None

    # API Public

    def connect(self):
        """Porneste thread-ul de background si incearca conectarea la RPi5."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._recv_loop,
            daemon=True,
            name="LidarRecvThread"
        )
        self._thread.start()
        logging.info(f"LidarEngine pornit — tinta: {LIDAR_SERVER_IP}:{LIDAR_SERVER_PORT}")

    def disconnect(self):
        """Oprește thread-ul de background."""
        self._running = False
        logging.info("LidarEngine oprit.")

    def get_distance(self) -> float | None:
        """
        Returnează distanța frontală minimă în metri (sau None dacă nu există date).
        Aceasta este distanța față de obiectul cel mai apropiat din sectorul
        frontal al senzorului (±20° față de 0°).
        """
        with self._lock:
            return self._front_distance

    def get_points(self) -> list:
        """
        Returnează lista de puncte din ultimul scan complet (360°).
        Fiecare punct: {"angle": float, "distance": float, "intensity": int}
        """
        with self._lock:
            return list(self._points)

    def get_liveness_sigma(self) -> float | None:
        """
        Returnează deviația standard (σ, în mm) a distanțelor din sectorul
        frontal — folosită pentru anti-spoofing prin liveness detection.

        O față reală (relief 3D) produce σ ≥ 15mm.
        O suprafață plată (telefon/poză/ecran) produce σ < 10mm.
        """
        with self._lock:
            return self._sigma_mm

    def get_speed(self) -> float:
        """Returnează viteza de rotație a senzorului în grade/sec."""
        with self._lock:
            return self._speed

    def is_connected(self) -> bool:
        """True dacă există conexiune activă cu RPi5."""
        with self._lock:
            return self._connected

    def validate_presence(self) -> bool:
        """
        Validează prezența fizică a unei persoane în fața senzorului.

        Combină două criterii calculate pe server (RPi5):
          1. Distanța frontală este în intervalul [0.2m, 1.0m]
          2. Clasificatorul de liveness (σ) confirmă relief 3D real
             (σ ≥ 15mm), nu o suprafață plată precum un telefon sau o
             poză folosită pentru a păcăli camera.

        Returnează True doar dacă ambele condiții sunt satisfăcute.
        """
        with self._lock:
            dist  = self._front_distance
            valid_on_server = self._is_valid

        if dist is None:
            return False

        in_range = MIN_DISTANCE <= dist <= MAX_DISTANCE
        return in_range and valid_on_server

    def get_invalid_reason(self) -> str:
        """
        Returnează motivul pentru care validarea a eșuat (debugging/UI):
          - "no_object"            — nimic detectat în sectorul frontal
          - "flat_surface_detected" — suprafață plată (posibil spoofing)
          - "liveness_uncertain"    — σ în zona ambiguă (10-15mm)
          - "insufficient_data"     — prea puține puncte pentru estimare
          - "out_of_range"          — distanță în afara intervalului 0.2m-1.0m
          - "ok"                    — validare trecută
        """
        with self._lock:
            dist   = self._front_distance
            reason = self._reason

        if dist is not None and reason == "ok":
            if not (MIN_DISTANCE <= dist <= MAX_DISTANCE):
                return "out_of_range"
        return reason

    def get_status_text(self) -> tuple[str, str]:
        """
        Returnează (text_status, culoare_hex) pentru afișare în UI.
        Culorile corespund paletei din main.py.
        """
        if not self.is_connected():
            return "LiDAR: OFFLINE", "#64748B"

        dist = self.get_distance()
        if dist is None:
            return "LiDAR: Waiting...", "#64748B"

        reason = self.get_invalid_reason()

        if self.validate_presence():
            return f"LiDAR: {dist:.2f}m OK", "#00FF88"
        elif reason == "flat_surface_detected":
            return f"LiDAR: {dist:.2f}m (FLAT SURFACE)", "#FF4D6D"
        elif reason == "liveness_uncertain":
            return f"LiDAR: {dist:.2f}m (UNCERTAIN)", "#FFA500"
        elif dist < MIN_DISTANCE:
            return f"LiDAR: {dist:.2f}m (TOO CLOSE)", "#FFA500"
        elif dist > MAX_DISTANCE:
            return f"LiDAR: {dist:.2f}m (TOO FAR)", "#FFA500"
        else:
            return f"LiDAR: {dist:.2f}m (INVALID)", "#FFA500"

    # Thread Intern

    def _recv_loop(self):
        """
        Loop de background: menține conexiunea TCP cu RPi5 și
        parsează pachetele JSON primite.
        Se reconectează automat dacă conexiunea pică.
        """
        while self._running:
            sock = None
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5.0)
                sock.connect((LIDAR_SERVER_IP, LIDAR_SERVER_PORT))
                sock.settimeout(3.0)

                with self._lock:
                    self._connected = True
                logging.info(f"Conectat la RPi5 ({LIDAR_SERVER_IP}:{LIDAR_SERVER_PORT})")

                buf = ""
                while self._running:
                    try:
                        chunk = sock.recv(4096).decode("utf-8", errors="ignore")
                        if not chunk:
                            break   # server a închis conexiunea

                        buf += chunk

                        # Proceseaza toate pachetele complete (separate prin \n)
                        while "\n" in buf:
                            line, buf = buf.split("\n", 1)
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                data = json.loads(line)
                                with self._lock:
                                    self._points         = data.get("points", [])
                                    self._front_distance = data.get("front_distance")
                                    self._sigma_mm        = data.get("sigma_mm")
                                    self._is_valid         = data.get("is_valid", False)
                                    self._reason           = data.get("reason", "no_object")
                                    self._speed             = data.get("speed", 0.0)
                                    self._timestamp          = data.get("ts", 0)
                            except json.JSONDecodeError:
                                pass  # pachet corupt, ignorăm

                    except socket.timeout:
                        # Timeout normal — verificam daca mai rulam
                        continue

            except (ConnectionRefusedError, socket.timeout, OSError) as e:
                logging.warning(f"Conexiune eșuată: {e} — reîncerc în {RECONNECT_DELAY}s")
            finally:
                with self._lock:
                    self._connected      = False
                    self._front_distance = None
                    self._points         = []
                if sock:
                    try:
                        sock.close()
                    except:
                        pass

            if self._running:
                time.sleep(RECONNECT_DELAY)

        logging.info("Thread LidarEngine oprit.")