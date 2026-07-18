#!/usr/bin/env python3
"""
lidar_server.py  —  Ruleaza pe Raspberry Pi 5
================================================
Citeste senzorul LD06 prin UART GPIO (ttyAMA0, 230400 baud),
parseaza pachetele binare, si trimite datele prin TCP socket
catre aplicatia de pe laptop.

Pornire:
    python3 lidar_server.py

Portul TCP implicit: 65432
"""

import serial
import socket
import threading
import json
import time
import struct
import math
import logging

logging.basicConfig(
    level=logging.INFO,
    format="[LIDAR-SERVER] %(asctime)s — %(message)s",
    datefmt="%H:%M:%S"
)

# Constante Protocol LD06
LD06_START_BYTE  = 0x54
LD06_DATA_LEN    = 0x2C         # valoare reala descoperita pe senzorul fizic LD06
PACKET_SIZE      = 47           # dimensiunea totala a unui pachet LD06
BAUD_RATE        = 230400
UART_PORT        = "/dev/ttyAMA0"  # UART principal GPIO pe RPi5

# Constante Server
TCP_HOST         = "0.0.0.0"   # asculta pe toate interfetele
TCP_PORT         = 65432
MAX_CLIENTS      = 4

# CRC-8 (polinomul LD06: 0x4D)
CRC_TABLE = []

def _build_crc_table():
    for i in range(256):
        crc = i
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x4D) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
        CRC_TABLE.append(crc)

_build_crc_table()

def crc8(data: bytes) -> int:
    """Calculeaza CRC-8 pentru validarea pachetelor LD06."""
    crc = 0
    for byte in data:
        crc = CRC_TABLE[(crc ^ byte) & 0xFF]
    return crc


# Parser Pachet LD06
def parse_packet(raw: bytes) -> dict | None:
    """
    Parseaza un pachet binar LD06 de 47 bytes.

    Structura pachet:
      [0]     start_byte  = 0x54
      [1]     data_len    = 0x0E (12 puncte)
      [2-3]   speed       (grade/sec, little-endian uint16)
      [4-5]   start_angle (0.01 grade, little-endian uint16)
      [6-41]  12 x 3 bytes per punct:
                  [0-1] distance (mm, uint16 little-endian)
                  [2]   intensity (uint8)
      [42-43] end_angle   (0.01 grade, little-endian uint16)
      [44-45] timestamp   (ms, little-endian uint16)
      [46]    crc8
    """
    if len(raw) != PACKET_SIZE:
        return None

    if raw[0] != LD06_START_BYTE or raw[1] != LD06_DATA_LEN:
        return None

    # Validare CRC — primii 46 bytes, CRC la byte 46
    if crc8(raw[:46]) != raw[46]:
        return None

    speed       = struct.unpack_from('<H', raw, 2)[0] / 100.0   # grade/sec
    start_angle = struct.unpack_from('<H', raw, 4)[0] / 100.0   # grade
    end_angle   = struct.unpack_from('<H', raw, 42)[0] / 100.0  # grade
    timestamp   = struct.unpack_from('<H', raw, 44)[0]          # ms

    # Interpolare unghiuri pentru cele 12 puncte
    if end_angle > start_angle:
        angle_span = end_angle - start_angle
    else:
        angle_span = (360.0 - start_angle) + end_angle

    points = []
    for i in range(12):
        offset = 6 + i * 3
        distance_mm  = struct.unpack_from('<H', raw, offset)[0]
        intensity    = raw[offset + 2]

        angle = (start_angle + (angle_span / 11.0) * i) % 360.0

        # Filtrare puncte invalide (distanta 0 sau intensitate prea mica)
        if distance_mm == 0 or intensity < 10:
            continue

        points.append({
            "angle":     round(angle, 2),
            "distance":  round(distance_mm / 1000.0, 4),  # conversie in metri
            "intensity": intensity
        })

    return {
        "speed":       round(speed, 1),
        "start_angle": round(start_angle, 2),
        "end_angle":   round(end_angle, 2),
        "timestamp":   timestamp,
        "points":      points
    }


# Thread citire UART
class LidarReader(threading.Thread):
    """
    Thread dedicat citirii continue de la LD06 prin UART.
    Ultimul scan complet (360°) este disponibil in self.latest_scan.
    """

    def __init__(self):
        super().__init__(daemon=True)
        self.latest_scan   = []      # lista de puncte din ultimul tur complet
        self.latest_speed  = 0.0
        self._lock         = threading.Lock()
        self._running      = False
        self._ser          = None
        self._buffer       = bytearray()
        self._current_scan = []      # acumulare tur curent

    def connect(self):
        try:
            self._ser = serial.Serial(
                port=UART_PORT,
                baudrate=BAUD_RATE,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1.0
            )
            logging.info(f"Serial deschis: {UART_PORT} @ {BAUD_RATE} baud")
            return True
        except serial.SerialException as e:
            logging.error(f"Nu pot deschide {UART_PORT}: {e}")
            return False

    def run(self):
        if not self._ser or not self._ser.is_open:
            logging.error("Serial nedeschis — opresc thread-ul.")
            return

        self._running = True
        logging.info("Thread citire LD06 pornit.")

        last_end_angle = None

        while self._running:
            try:
                chunk = self._ser.read(PACKET_SIZE * 2)
                if not chunk:
                    continue

                self._buffer.extend(chunk)

                # Cauta si proceseaza toate pachetele complete din buffer
                while len(self._buffer) >= PACKET_SIZE:
                    # Gaseste start byte
                    idx = self._buffer.find(bytes([LD06_START_BYTE]))
                    if idx == -1:
                        self._buffer.clear()
                        break
                    if idx > 0:
                        del self._buffer[:idx]

                    if len(self._buffer) < PACKET_SIZE:
                        break

                    # Verifica si al doilea byte inainte de parsare
                    if self._buffer[1] != LD06_DATA_LEN:
                        del self._buffer[0]
                        continue

                    raw = bytes(self._buffer[:PACKET_SIZE])
                    del self._buffer[:PACKET_SIZE]

                    packet = parse_packet(raw)
                    if packet is None:
                        continue

                    # Detectare tur complet: când unghiul scade (trecem de 360→0)
                    if last_end_angle is not None:
                        if packet["start_angle"] < last_end_angle - 10:
                            # Tur complet finalizat — publica scanul
                            with self._lock:
                                self.latest_scan  = list(self._current_scan)
                                self.latest_speed = packet["speed"]
                            self._current_scan = []

                    self._current_scan.extend(packet["points"])
                    last_end_angle = packet["end_angle"]

            except serial.SerialException as e:
                logging.error(f"Eroare serial: {e}")
                time.sleep(0.5)
            except Exception as e:
                logging.error(f"Eroare neasteptata in reader: {e}")
                time.sleep(0.1)

    def get_scan(self):
        with self._lock:
            return list(self.latest_scan), self.latest_speed

    def stop(self):
        self._running = False
        if self._ser and self._ser.is_open:
            self._ser.close()
            logging.info("Serial inchis.")


# Calcul distanta frontala
def compute_front_distance(points: list, fov_deg: float = 40.0) -> float | None:
    """
    Calculeaza distanta minima din sectorul frontal al LiDAR-ului.

    Sectorul frontal = unghiurile din jurul lui 0° (sau 360°),
    cu o fereastra de ±fov_deg/2 (implicit ±20°).

    Returneaza distanta in metri sau None daca nu exista puncte valide.
    """
    half = fov_deg / 2.0
    front_distances = []

    for p in points:
        angle = p["angle"]
        dist  = p["distance"]

        # Unghi frontal: 0° ± half SAU echivalent 360° - half → 360°
        in_front = (angle <= half) or (angle >= 360.0 - half)

        if in_front and 0.05 <= dist <= 3.0:
            front_distances.append(dist)

    if not front_distances:
        return None

    return round(min(front_distances), 3)


# Clasificator Liveness — Discriminare Topologica (σ)
# O fata reala are relief 3D (nas, obraji, frunte la distante usor diferite),
# in timp ce un telefon/poza este o suprafata plata — toate punctele din
# sectorul frontal au aproape exact aceeasi distanta (variatie doar din
# zgomotul senzorului, sub 10mm). Calculam media (μ) si deviatia standard (σ)
# a distantelor din sectorul frontal pentru a distinge cele doua cazuri.
SIGMA_FRAUD_MM = 10.0   # sub acest prag → suprafata plana (frauda/spoofing)
SIGMA_LIVE_MM  = 15.0   # peste acest prag → relief 3D real (persoana vie)

def compute_liveness_sigma(points: list, fov_deg: float = 40.0,
                             cluster_tolerance_m: float = 0.10) -> dict:
    """
    Calculeaza μ (media) si σ (deviatia standard) a distantelor DOAR pentru
    clusterul obiectului cel mai apropiat din sectorul frontal — nu pentru
    tot fundalul vizibil in con (pereti, mobila etc., care ar intinde
    artificial σ la sute de mm).

    Pas 1: gasim toate punctele din sectorul frontal (±fov_deg/2)
    Pas 2: izolam doar punctele apropiate de distanta minima (clustering
           simplu — punctele de pe fata/telefon, nu fundalul din spate)
    Pas 3: calculam μ si σ doar pe acest cluster

        μ = (1/N) * Σ d_i
        σ = sqrt( (1/N) * Σ (d_i - μ)² )

    Interpretare:
        σ < 10.0mm  → FRAUDĂ (suprafata plana — telefon/poza/display)
        σ ≥ 15.0mm  → LIVE   (relief facial tridimensional real)
        10-15mm     → zona ambigua, tratata conservator ca FRAUDĂ

    Returneaza dict cu: mu_m, sigma_mm, n_points (ale clusterului, nu ale
    intregului sector frontal).
    """
    half = fov_deg / 2.0
    distances = []

    for p in points:
        angle = p["angle"]
        dist  = p["distance"]
        in_front = (angle <= half) or (angle >= 360.0 - half)
        if in_front and 0.05 <= dist <= 3.0:
            distances.append(dist)

    if not distances:
        return {"mu_m": None, "sigma_mm": None, "n_points": 0}

    # Izolam doar clusterul obiectului cel mai apropiat (ex: fata/telefonul),
    # excluzând fundalul (pereti, mobila) care ar intinde artificial σ
    nearest = min(distances)
    cluster = [d for d in distances if d - nearest <= cluster_tolerance_m]

    n = len(cluster)
    if n < 5:
        # Date insuficiente pentru o estimare statistica fiabila
        return {"mu_m": None, "sigma_mm": None, "n_points": n}

    mu = sum(cluster) / n
    variance = sum((d - mu) ** 2 for d in cluster) / n
    sigma_m  = math.sqrt(variance)
    sigma_mm = sigma_m * 1000.0

    return {
        "mu_m":     round(mu, 4),
        "sigma_mm": round(sigma_mm, 2),
        "n_points": n
    }


def validate_presence_with_volume(points: list) -> dict:
    """
    Validare combinata: distanta frontala minima + clasificator liveness (σ).

    Returneaza un dict cu toate informatiile relevante pentru debugging
    si pentru a fi trimis catre client (laptop):
        {
            "distance":   float | None,   (distanta minima frontala, m)
            "sigma_mm":   float | None,    (deviatia standard a profunzimii, mm)
            "is_valid":   bool,
            "reason":     str   (motivul validarii/invalidarii)
        }
    """
    dist = compute_front_distance(points)

    if dist is None:
        return {"distance": None, "sigma_mm": None, "is_valid": False,
                "reason": "no_object"}

    liveness = compute_liveness_sigma(points)
    sigma_mm = liveness["sigma_mm"]

    if sigma_mm is None:
        return {"distance": dist, "sigma_mm": None, "is_valid": False,
                "reason": "insufficient_data"}

    if sigma_mm < SIGMA_FRAUD_MM:
        return {"distance": dist, "sigma_mm": sigma_mm, "is_valid": False,
                "reason": "flat_surface_detected"}

    # Zona 10-15mm e ambigua — o tratam conservator, cerem sigma >= 15mm
    if sigma_mm < SIGMA_LIVE_MM:
        return {"distance": dist, "sigma_mm": sigma_mm, "is_valid": False,
                "reason": "liveness_uncertain"}

    return {"distance": dist, "sigma_mm": sigma_mm, "is_valid": True,
            "reason": "ok"}


# Server TCP
class LidarServer:
    """
    Server TCP care trimite datele LiDAR la clienti (laptopul cu UI).
    Fiecare client primeste câte un JSON per scan, terminat cu newline.

    Format JSON trimis:
    {
        "points":   [...],       // lista de puncte {angle, distance, intensity}
        "front_distance": 1.23,  // distanta minima frontala in metri (sau null)
        "speed":    4.5,         // viteza de rotatie grade/sec
        "ts":       1234567890   // timestamp Unix
    }
    """

    def __init__(self, reader: LidarReader):
        self._reader  = reader
        self._clients = []
        self._lock    = threading.Lock()
        self._running = False

    def _handle_client(self, conn, addr):
        logging.info(f"Client conectat: {addr}")
        with self._lock:
            self._clients.append(conn)
        try:
            # Ține conexiunea deschisa; clientul poate trimite orice (ignoram)
            while self._running:
                time.sleep(1)
                try:
                    conn.recv(1)  # detectare deconectare
                except:
                    break
        finally:
            with self._lock:
                if conn in self._clients:
                    self._clients.remove(conn)
            conn.close()
            logging.info(f"Client deconectat: {addr}")

    def _broadcast_loop(self):
        """Trimite scan-ul curent la toti clientii la ~10 Hz."""
        while self._running:
            points, speed = self._reader.get_scan()

            validation = validate_presence_with_volume(points)

            payload = {
                "points":         points,
                "front_distance": validation["distance"],
                "sigma_mm":       validation["sigma_mm"],
                "is_valid":       validation["is_valid"],
                "reason":         validation["reason"],
                "speed":          speed,
                "ts":             int(time.time() * 1000)
            }
            data = (json.dumps(payload) + "\n").encode("utf-8")

            with self._lock:
                dead = []
                for conn in self._clients:
                    try:
                        conn.sendall(data)
                    except:
                        dead.append(conn)
                for conn in dead:
                    self._clients.remove(conn)

            time.sleep(0.1)  # 10 Hz

    def start(self):
        self._running = True
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((TCP_HOST, TCP_PORT))
        srv.listen(MAX_CLIENTS)
        srv.settimeout(1.0)

        logging.info(f"Server TCP pornit pe {TCP_HOST}:{TCP_PORT}")

        broadcast_t = threading.Thread(target=self._broadcast_loop, daemon=True)
        broadcast_t.start()

        try:
            while self._running:
                try:
                    conn, addr = srv.accept()
                    t = threading.Thread(
                        target=self._handle_client,
                        args=(conn, addr),
                        daemon=True
                    )
                    t.start()
                except socket.timeout:
                    continue
        except KeyboardInterrupt:
            logging.info("Oprire server (KeyboardInterrupt).")
        finally:
            self._running = False
            srv.close()


# Entry Point
if __name__ == "__main__":
    reader = LidarReader()

    if not reader.connect():
        logging.error("Nu pot conecta LD06. Verifica pinii GPIO si ttyAMA0.")
        exit(1)

    reader.start()

    # Asteapta primul scan (maxim 5 secunde)
    logging.info("Astept primul scan de la LD06...")
    for _ in range(50):
        pts, _ = reader.get_scan()
        if pts:
            logging.info(f"Primul scan primit: {len(pts)} puncte.")
            break
        time.sleep(0.1)
    else:
        logging.warning("Nu am primit date de la LD06 in 5 secunde. Continui oricum.")

    server = LidarServer(reader)
    server.start()