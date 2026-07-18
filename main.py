import customtkinter as ctk
import cv2
from PIL import Image
import datetime
import sqlite3
import hashlib
import numpy as np
import os
import shutil
import tkinter.filedialog as fd
import tkinter.messagebox as mb

from vision_core import VisionEngine
from lidar_engine import LidarEngine

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

# Fulouri de culori (Cyberpunk / Slate Tech)
C = {
    "bg": "#050A0E",  # Fundalul principal ultra-dark
    "panel": "#0D1117",  # Panouri secundare
    "card": "#111827",  # Carduri interioare
    "border": "#1F2D3D",  # Margini și separatori
    "primary": "#00FF88",  # Verde Neon (Sistem Activ / Profesor)
    "primary_dim": "#00CC6A",
    "blue": "#38BDF8",  # Albastru Cyber (Student / Info)
    "purple": "#A78BFA",  # LiDAR / Efecte speciale
    "danger": "#FF4D6D",  # Erori / Alerte
    "warn": "#FFA500",  # Avertismente
    "text": "#E2E8F0",  # Text principal
    "text_dim": "#64748B",  # Text secundar / Muted
    "input": "#0D1117",  # Câmpuri text
    "sidebar": "#080D12",  # Sidebar fundal
}

FONT_MONO = ("Courier New", 11)
FONT_TITLE = ("Courier New", 20, "bold")
FONT_BTN = ("Courier New", 13, "bold")
FONT_SMALL = ("Courier New", 10)

DATASET_PATH = "dataset"


# Baza de date & functii helper
def init_db():
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        name  TEXT NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS laboratoare (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        profesor_email TEXT NOT NULL,
        nume_materie TEXT NOT NULL,
        ziua TEXT NOT NULL,
        ora_inceput TEXT NOT NULL,
        ora_sfarsit TEXT NOT NULL
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS prezente (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_email TEXT NOT NULL,
        laborator_id INTEGER NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (laborator_id) REFERENCES laboratoare(id)
    )''')
    conn.commit()
    conn.close()


def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()


def register_user(email, name, password, role):
    try:
        conn = sqlite3.connect("users.db")
        conn.execute("INSERT INTO users VALUES (NULL,?,?,?,?)",
                     (email, name, hash_pw(password), role))
        conn.commit();
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False


def login_user(email, password):
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute("SELECT name, role FROM users WHERE email=? AND password=?",
                (email, hash_pw(password)))
    row = cur.fetchone();
    conn.close()
    return row


def get_student_stats(email):
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute('''SELECT l.nume_materie, p.timestamp
                   FROM prezente p JOIN laboratoare l ON p.laborator_id=l.id
                   WHERE p.student_email=? ORDER BY p.timestamp DESC''', (email,))
    data = cur.fetchall();
    conn.close()
    return data


def save_prezenta(student_email, lab_id):
    conn = sqlite3.connect("users.db")
    conn.execute("INSERT INTO prezente (student_email, laborator_id) VALUES (?,?)",
                 (student_email, lab_id))
    conn.commit();
    conn.close()


def get_labs_for_prof(prof_email):
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute("SELECT id, nume_materie, ziua, ora_inceput FROM laboratoare WHERE profesor_email=?",
                (prof_email,))
    rows = cur.fetchall();
    conn.close()
    return rows


def count_student_photos(email):
    folder = os.path.join(DATASET_PATH, email)
    if not os.path.isdir(folder):
        return 0
    return len([f for f in os.listdir(folder)
                if f.lower().endswith((".jpg", ".jpeg", ".png"))])


def sep(parent):
    ctk.CTkFrame(parent, height=1, fg_color=C["border"]).pack(fill="x", pady=8)


def tlabel(parent, text, color=None, font=None, **kw):
    return ctk.CTkLabel(parent, text=text,
                        text_color=color or C["text_dim"],
                        font=font or FONT_SMALL, **kw)


# Login
class LoginFrame(ctk.CTkFrame):
    def __init__(self, master, controller):
        super().__init__(master, fg_color=C["bg"])
        self.controller = controller

        # HUD elemente decorative
        tlabel(self, "> SYSTEM ONLINE", color=C["border"], font=("Courier New", 9)).place(x=12, y=12)
        tlabel(self, f"> {datetime.datetime.now().strftime('%Y-%m-%d')}",
               color=C["border"], font=("Courier New", 9)).place(x=12, y=28)

        # Fereastra centrala (Card tip Login)
        card = ctk.CTkFrame(self, width=420, height=560,
                            fg_color=C["panel"], corner_radius=4,
                            border_width=1, border_color=C["border"])
        card.place(relx=0.5, rely=0.5, anchor="center")
        card.pack_propagate(False)

        # Header card
        hdr = ctk.CTkFrame(card, fg_color=C["card"], corner_radius=0, height=70)
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text="SECUREPASS  AI", font=FONT_TITLE, text_color=C["primary"]).pack(pady=18)

        info = ctk.CTkFrame(card, fg_color="transparent")
        info.pack(fill="x", padx=28, pady=(16, 4))
        tlabel(info, "> BIOMETRIC ATTENDANCE SYSTEM v2.0").pack(anchor="w")
        tlabel(info, "> AUTHENTICATE TO CONTINUE").pack(anchor="w")

        sep(card)

        # Inputuri
        inp = ctk.CTkFrame(card, fg_color="transparent")
        inp.pack(fill="x", padx=28)

        tlabel(inp, "EMAIL").pack(anchor="w", pady=(0, 3))
        self.email_e = ctk.CTkEntry(inp, placeholder_text="user@university.ro", height=42, corner_radius=3,
                                    fg_color=C["input"], border_color=C["border"], border_width=1,
                                    font=FONT_MONO, text_color=C["primary"])
        self.email_e.pack(fill="x", pady=(0, 12))

        tlabel(inp, "PASSWORD").pack(anchor="w", pady=(0, 3))
        self.pass_e = ctk.CTkEntry(inp, placeholder_text="••••••••", show="•", height=42, corner_radius=3,
                                   fg_color=C["input"], border_color=C["border"], border_width=1,
                                   font=FONT_MONO, text_color=C["primary"])
        self.pass_e.pack(fill="x")
        self.pass_e.bind("<Return>", lambda e: self._login())

        sep(card)

        # Butoane
        btn_f = ctk.CTkFrame(card, fg_color="transparent")
        btn_f.pack(fill="x", padx=28, pady=(0, 16))

        ctk.CTkButton(btn_f, text="[ LOGIN ]", height=44, corner_radius=3,
                      fg_color=C["primary"], hover_color=C["primary_dim"],
                      text_color=C["bg"], font=FONT_BTN, command=self._login).pack(fill="x")

        ctk.CTkButton(btn_f, text="CREATE ACCOUNT", height=34, corner_radius=3,
                      fg_color="transparent", border_width=1, border_color=C["border"],
                      text_color=C["text_dim"], font=FONT_SMALL, hover_color=C["card"],
                      command=lambda: controller.show_frame("SignupFrame")).pack(fill="x", pady=(8, 0))

        self.msg = ctk.CTkLabel(card, text="", font=FONT_SMALL, text_color=C["danger"])
        self.msg.pack(pady=(4, 8))

    def _login(self):
        email = self.email_e.get().strip()
        pwd = self.pass_e.get()
        data = login_user(email, pwd)
        if data:
            name, role = data
            self.controller.current_user = {"email": email, "name": name, "role": role}
            self.msg.configure(text="AUTH OK — REDIRECTING...", text_color=C["primary"])
            target = "ProfessorDashboard" if role == "Professor" else "StudentDashboard"
            self.after(600, lambda: self.controller.show_frame(target))
        else:
            self.msg.configure(text="! INVALID CREDENTIALS", text_color=C["danger"])


# Signup
class SignupFrame(ctk.CTkFrame):
    def __init__(self, master, controller):
        super().__init__(master, fg_color=C["bg"])
        self.controller = controller

        card = ctk.CTkFrame(self, width=420, height=610,
                            fg_color=C["panel"], corner_radius=4,
                            border_width=1, border_color=C["border"])
        card.place(relx=0.5, rely=0.5, anchor="center")
        card.pack_propagate(False)

        hdr = ctk.CTkFrame(card, fg_color=C["card"], corner_radius=0, height=70)
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text="NEW  ACCOUNT", font=FONT_TITLE, text_color=C["blue"]).pack(pady=18)

        info = ctk.CTkFrame(card, fg_color="transparent")
        info.pack(fill="x", padx=28, pady=(12, 4))
        tlabel(info, "> REGISTER TO SECUREPASS SYSTEM").pack(anchor="w")

        sep(card)

        frm = ctk.CTkFrame(card, fg_color="transparent")
        frm.pack(fill="x", padx=28)

        def field(lbl, ph, show=None):
            tlabel(frm, lbl).pack(anchor="w", pady=(0, 3))
            e = ctk.CTkEntry(frm, placeholder_text=ph, height=40, corner_radius=3,
                             fg_color=C["input"], border_color=C["border"], border_width=1,
                             font=FONT_MONO, text_color=C["text"], show=show or "")
            e.pack(fill="x", pady=(0, 10))
            return e

        self.name_e = field("FULL NAME", "Ion Popescu")
        self.email_e = field("EMAIL", "ion@student.ro")
        self.pass_e = field("PASSWORD", "min 4 chars", show="•")

        tlabel(frm, "ROLE").pack(anchor="w", pady=(0, 6))
        self.role_var = ctk.StringVar(value="Student")
        ctk.CTkSegmentedButton(frm, values=["Student", "Professor"], variable=self.role_var,
                               height=38, corner_radius=3, selected_color=C["purple"],
                               selected_hover_color=C["purple"], unselected_color=C["card"],
                               font=FONT_BTN).pack(fill="x")

        sep(card)

        btn_f = ctk.CTkFrame(card, fg_color="transparent")
        btn_f.pack(fill="x", padx=28, pady=(0, 12))

        ctk.CTkButton(btn_f, text="[ CREATE ACCOUNT ]", height=44, corner_radius=3,
                      fg_color=C["blue"], hover_color="#1E90C0", text_color=C["bg"], font=FONT_BTN,
                      command=self._do_register).pack(fill="x")

        ctk.CTkButton(btn_f, text="BACK TO LOGIN", height=32, corner_radius=3,
                      fg_color="transparent", border_width=1, border_color=C["border"],
                      text_color=C["text_dim"], hover_color=C["card"], font=FONT_SMALL,
                      command=lambda: controller.show_frame("LoginFrame")).pack(fill="x", pady=(6, 0))

        self.msg = ctk.CTkLabel(card, text="", font=FONT_SMALL, text_color=C["danger"])
        self.msg.pack(pady=4)

    def _do_register(self):
        name = self.name_e.get().strip()
        email = self.email_e.get().strip()
        pwd = self.pass_e.get()
        role = self.role_var.get()
        if not name or not email or len(pwd) < 4:
            self.msg.configure(text="! ALL FIELDS REQUIRED  (PASSWORD >= 4)", text_color=C["danger"])
            return
        if register_user(email, name, pwd, role):
            self.msg.configure(text="ACCOUNT CREATED — REDIRECTING...", text_color=C["primary"])
            self.after(1200, lambda: self.controller.show_frame("LoginFrame"))
        else:
            self.msg.configure(text="! EMAIL ALREADY REGISTERED", text_color=C["warn"])


# Dashboard Profesor
class ProfessorDashboard(ctk.CTkFrame):
    def __init__(self, master, controller):
        super().__init__(master, fg_color=C["bg"])
        self.controller = controller
        self.cap = None
        self.is_running = False
        self.prezenti = set()
        self.lab_ids = {}
        self._rgb_ref = None
        self._lidar_ref = None

        # Grid Layout structural curat (sidebar fix, zona centrala dinamica)
        self.grid_columnconfigure(0, minsize=300, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_main()
        self.vision = VisionEngine()
        self.lidar = LidarEngine()
        self.lidar.connect()

    # Sidebar Control Panel
    def _build_sidebar(self):
        outer = ctk.CTkFrame(self, fg_color=C["sidebar"], corner_radius=0)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.grid_rowconfigure(1, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        # Sidebar Title
        brand = ctk.CTkFrame(outer, fg_color=C["card"], corner_radius=0, height=56)
        brand.grid(row=0, column=0, sticky="ew")
        brand.grid_propagate(False)
        ctk.CTkLabel(brand, text="SECUREPASS  AI", font=("Courier New", 14, "bold"), text_color=C["primary"]).place(
            relx=0.5, rely=0.5, anchor="center")

        sb = ctk.CTkScrollableFrame(outer, fg_color="transparent", scrollbar_button_color=C["border"],
                                    scrollbar_button_hover_color=C["primary"])
        sb.grid(row=1, column=0, sticky="nsew")

        # System Badge Statuses
        spill = ctk.CTkFrame(sb, fg_color=C["card"], corner_radius=20, height=30)
        spill.pack(fill="x", padx=14, pady=(12, 6))
        spill.pack_propagate(False)
        self.status_lbl = ctk.CTkLabel(spill, text="● SYSTEM OFFLINE", font=FONT_SMALL, text_color=C["text_dim"])
        self.status_lbl.place(relx=0.5, rely=0.5, anchor="center")

        lpill = ctk.CTkFrame(sb, fg_color=C["card"], corner_radius=20, height=30)
        lpill.pack(fill="x", padx=14, pady=(0, 8))
        lpill.pack_propagate(False)
        self.lidar_status_lbl = ctk.CTkLabel(lpill, text="📡 LiDAR: STANDBY", font=FONT_SMALL, text_color=C["text_dim"])
        self.lidar_status_lbl.place(relx=0.5, rely=0.5, anchor="center")

        # Card: Management Laboratoare
        lc = ctk.CTkFrame(sb, fg_color=C["card"], corner_radius=4, border_width=1, border_color=C["border"])
        lc.pack(fill="x", padx=12, pady=4)

        tlabel(lc, "// LAB MANAGEMENT", font=("Courier New", 10, "bold")).pack(anchor="w", padx=10, pady=(8, 6))

        grid_f = ctk.CTkFrame(lc, fg_color="transparent")
        grid_f.pack(fill="x", padx=8, pady=(0, 4))
        grid_f.grid_columnconfigure(0, weight=1)
        grid_f.grid_columnconfigure(1, weight=1)

        def se(ph, r, c):
            e = ctk.CTkEntry(grid_f, placeholder_text=ph, height=32, corner_radius=3,
                             fg_color=C["input"], border_color=C["border"], border_width=1,
                             font=FONT_SMALL, text_color=C["text"])
            e.grid(row=r, column=c, padx=2, pady=2, sticky="ew")
            return e

        self.e_materie = se("Materie", 0, 0)
        self.e_ziua = se("Ziua", 0, 1)
        self.e_ora_inc = se("Ora start", 1, 0)
        self.e_ora_sf = se("Ora stop", 1, 1)

        ctk.CTkButton(lc, text="+ ADD LAB", height=32, corner_radius=3,
                      fg_color=C["primary"], hover_color=C["primary_dim"], text_color=C["bg"], font=FONT_SMALL,
                      command=self._save_lab).pack(fill="x", padx=8, pady=(4, 10))

        # Card: Sesiune Activa selector
        ac = ctk.CTkFrame(sb, fg_color=C["card"], corner_radius=4, border_width=1, border_color=C["border"])
        ac.pack(fill="x", padx=12, pady=4)

        tlabel(ac, "// ACTIVE SESSION", font=("Courier New", 10, "bold")).pack(anchor="w", padx=10, pady=(8, 4))

        self.lab_var = ctk.StringVar(value="— select lab —")
        self.lab_menu = ctk.CTkOptionMenu(ac, variable=self.lab_var, values=["No labs yet"],
                                          height=34, corner_radius=3, fg_color=C["input"],
                                          button_color=C["border"], button_hover_color=C["primary"],
                                          font=FONT_SMALL, text_color=C["text"])
        self.lab_menu.pack(fill="x", padx=8, pady=(0, 10))

        # Butoane mari Acțiune Sesiune
        ctrl = ctk.CTkFrame(sb, fg_color="transparent")
        ctrl.pack(fill="x", padx=12, pady=8)

        self.btn_start = ctk.CTkButton(ctrl, text="▶  START MONITORING", height=44, corner_radius=3,
                                       fg_color=C["primary"], hover_color=C["primary_dim"], text_color=C["bg"],
                                       font=FONT_BTN, command=self._start)
        self.btn_start.pack(fill="x", pady=(0, 6))

        self.btn_stop = ctk.CTkButton(ctrl, text="⏹  STOP", height=44, corner_radius=3,
                                      fg_color=C["danger"], hover_color="#CC2244", text_color="white",
                                      font=FONT_BTN, command=self._stop)
        self.btn_stop.pack(fill="x")

        # Ieșire cont
        ctk.CTkButton(sb, text="LOGOUT", height=34, corner_radius=3,
                      fg_color="transparent", border_width=1, border_color=C["border"],
                      text_color=C["text_dim"], font=FONT_SMALL, hover_color=C["card"],
                      command=self._logout).pack(fill="x", padx=12, pady=(16, 20))

    # Zona centrala monitoare video
    def _build_main(self):
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        main.grid_rowconfigure(1, weight=1)
        main.grid_columnconfigure(0, weight=1)
        main.grid_columnconfigure(1, weight=1)

        # Top Bar Info
        top = ctk.CTkFrame(main, fg_color="transparent")
        top.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 14))
        ctk.CTkLabel(top, text="LIVE  BIOMETRIC  STREAM", font=("Courier New", 18, "bold"), text_color=C["text"]).pack(
            side="left")
        self.clock_lbl = ctk.CTkLabel(top, text="", font=FONT_MONO, text_color=C["text_dim"])
        self.clock_lbl.pack(side="right")
        self._tick_clock()

        # Rezoluție Video Flux 1: RGB
        rgb_card = ctk.CTkFrame(main, fg_color=C["panel"], corner_radius=4, border_width=1, border_color=C["border"])
        rgb_card.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        rgb_hdr = ctk.CTkFrame(rgb_card, fg_color=C["card"], corner_radius=0, height=36)
        rgb_hdr.pack(fill="x")
        ctk.CTkLabel(rgb_hdr, text="📷  RGB CAMERA FEED", font=("Courier New", 11, "bold"), text_color=C["blue"]).pack(
            side="left", padx=12, pady=8)
        self.lbl_rgb = ctk.CTkLabel(rgb_card, text="[ OFFLINE ]", font=("Courier New", 14), text_color=C["text_dim"])
        self.lbl_rgb.pack(expand=True, fill="both", padx=6, pady=6)

        # Rezoluție Video Flux 2: LiDAR HUD Simulator
        lid_card = ctk.CTkFrame(main, fg_color=C["panel"], corner_radius=4, border_width=1, border_color=C["border"])
        lid_card.grid(row=1, column=1, sticky="nsew", padx=(10, 0))
        lid_hdr = ctk.CTkFrame(lid_card, fg_color=C["card"], corner_radius=0, height=36)
        lid_hdr.pack(fill="x")
        ctk.CTkLabel(lid_hdr, text="📡  LiDAR  DEPTH  MAP", font=("Courier New", 11, "bold"),
                     text_color=C["purple"]).pack(side="left", padx=12, pady=8)
        self.lbl_lidar = ctk.CTkLabel(lid_card, text="[ NO DATA ]", font=("Courier New", 14), text_color=C["text_dim"])
        self.lbl_lidar.pack(expand=True, fill="both", padx=6, pady=6)

        # Sistem consola evenimente inferioara (inlocuieste popup-urile clasice UX)
        evbar = ctk.CTkFrame(main, fg_color=C["panel"], corner_radius=3, border_width=1, border_color=C["border"],
                             height=44)
        evbar.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        evbar.grid_propagate(False)
        self.event_lbl = ctk.CTkLabel(evbar, text="> Waiting for session to start...", font=FONT_MONO,
                                      text_color=C["text_dim"])
        self.event_lbl.place(relx=0.02, rely=0.5, anchor="w")

    def _tick_clock(self):
        self.clock_lbl.configure(text=datetime.datetime.now().strftime("%Y-%m-%d  %H:%M:%S"))
        self.after(1000, self._tick_clock)

    def tkraise(self, *args, **kwargs):
        super().tkraise(*args, **kwargs)
        self._load_labs()

    def _prof_email(self):
        return self.controller.current_user["email"] if self.controller.current_user else "prof@test.com"

    def _save_lab(self):
        materie = self.e_materie.get().strip()
        ziua = self.e_ziua.get().strip()
        ora_inc = self.e_ora_inc.get().strip()
        ora_sf = self.e_ora_sf.get().strip()
        if not all([materie, ziua, ora_inc, ora_sf]):
            self._set_event("! FILL ALL FIELDS BEFORE ADDING LAB", C["warn"])
            return
        conn = sqlite3.connect("users.db")
        conn.execute(
            "INSERT INTO laboratoare (profesor_email,nume_materie,ziua,ora_inceput,ora_sfarsit) VALUES (?,?,?,?,?)",
            (self._prof_email(), materie, ziua, ora_inc, ora_sf))
        conn.commit();
        conn.close()
        for e in [self.e_materie, self.e_ziua, self.e_ora_inc, self.e_ora_sf]:
            e.delete(0, "end")
        self._load_labs()
        self._set_event(f"> Lab '{materie}' added successfully", C["primary"])

    def _load_labs(self):
        self.lab_ids = {}
        rows = get_labs_for_prof(self._prof_email())
        if rows:
            options = []
            for lab_id, name, day, start in rows:
                txt = f"{name} | {day} {start}"
                options.append(txt)
                self.lab_ids[txt] = lab_id
            self.lab_menu.configure(values=options)
            if self.lab_var.get() not in options:
                self.lab_var.set(options[-1])
        else:
            self.lab_menu.configure(values=["No labs yet"])
            self.lab_var.set("No labs yet")

    # Logica camera si procesare matrice
    def _start(self):
        if self.is_running: return
        self.prezenti.clear()
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            self._set_event("! CAMERA NOT FOUND", C["danger"])
            return
        self.is_running = True
        self.status_lbl.configure(text="● SYSTEM ONLINE", text_color=C["primary"])
        lidar_text, lidar_color = self.lidar.get_status_text()
        self.lidar_status_lbl.configure(text=lidar_text, text_color=lidar_color)
        self._set_event("> Session started — scanning...", C["primary"])
        self._update()

    def _stop(self):
        self.is_running = False
        if self.cap:
            self.cap.release()
            self.cap = None
        blank = Image.new("RGB", (640, 480), (13, 17, 23))
        ref = ctk.CTkImage(blank, size=(480, 340))
        self._rgb_ref = ref
        self._lidar_ref = ref
        try:
            self.lbl_rgb.configure(image=ref, text="")
            self.lbl_lidar.configure(image=ref, text="")
        except:
            pass
        self.status_lbl.configure(text="● SYSTEM OFFLINE", text_color=C["text_dim"])
        self.lidar_status_lbl.configure(text="📡 LiDAR: STANDBY", text_color=C["text_dim"])
        self._set_event("> Session stopped.", C["text_dim"])

    def _make_lidar_frame(self, _base_frame=None):
        """
        Genereaza un radar polar real cu datele primite de la senzorul LD06
        prin Raspberry Pi 5.

        Afiseaza:
          - Cercuri concentrice de distanta (0.5m, 1.0m, 1.5m, 2.0m)
          - Punctele de scan reale colorate dupa distanta
          - Sectorul frontal evidentiat (±20°)
          - Distanta frontala si statusul de validare
          - Viteza de rotatie a senzorului
        """
        W, H = 640, 480
        panel = np.zeros((H, W, 3), dtype=np.uint8)
        panel[:] = (10, 13, 18)   # fundal ultra-dark

        cx, cy   = W // 2, H // 2
        MAX_DIST = 3.0            # metri — distanța maxima afisata
        SCALE    = min(cx, cy) - 30   # pixeli per MAX_DIST metri
        font     = cv2.FONT_HERSHEY_SIMPLEX

        # Grid cercuri concentrice
        ring_distances = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
        for d in ring_distances:
            r = int((d / MAX_DIST) * SCALE)
            is_validation_limit = d in (0.5, 2.0)
            color = (0, 120, 60) if not is_validation_limit else (0, 80, 160)
            thickness = 2 if is_validation_limit else 1
            cv2.circle(panel, (cx, cy), r, color, thickness)
            # Eticheta distanța
            lx = cx + r + 4
            ly = cy - 4
            cv2.putText(panel, f"{d:.1f}m", (lx, ly), font, 0.32,
                        (0, 160, 80), 1, cv2.LINE_AA)

        # Linii de axe
        cv2.line(panel, (cx, cy - SCALE - 10), (cx, cy + SCALE + 10), (0, 80, 40), 1)
        cv2.line(panel, (cx - SCALE - 10, cy), (cx + SCALE + 10, cy), (0, 80, 40), 1)

        # Sector frontal evidențiat (±20°)
        import math
        FOV_HALF = 20.0
        r_max_px = int((2.0 / MAX_DIST) * SCALE)  # zona verde = zona valida
        pts_sector = []
        for ang_deg in range(int(-FOV_HALF), int(FOV_HALF) + 1, 2):
            ang_rad = math.radians(ang_deg - 90)  # 0° = sus pe ecran
            px = int(cx + r_max_px * math.cos(ang_rad))
            py = int(cy + r_max_px * math.sin(ang_rad))
            pts_sector.append([px, py])
        pts_sector.insert(0, [cx, cy])
        pts_sector.append([cx, cy])
        sector_arr = np.array(pts_sector, dtype=np.int32)
        overlay = panel.copy()
        cv2.fillPoly(overlay, [sector_arr], (0, 40, 20))
        cv2.addWeighted(overlay, 0.4, panel, 0.6, 0, panel)

        # Puncte de scan reale
        points = self.lidar.get_points()
        for p in points:
            angle_deg = p["angle"]
            dist_m    = p["distance"]

            if dist_m > MAX_DIST:
                continue

            # Conventie: 0° = fata (sus pe radar), rotatie orara
            # LD06: 0° = fata, creste in sens orar
            ang_rad = math.radians(angle_deg - 90)
            r_px    = int((dist_m / MAX_DIST) * SCALE)
            px      = int(cx + r_px * math.cos(ang_rad))
            py      = int(cy + r_px * math.sin(ang_rad))

            if not (0 <= px < W and 0 <= py < H):
                continue

            # Culoare dupa distanta: verde (aproape) → albastru (departe)
            t = min(dist_m / MAX_DIST, 1.0)
            b = int(50  + t * 200)
            g = int(255 - t * 180)
            cv2.circle(panel, (px, py), 2, (b, g, 30), -1)

        # Punct central (origine senzor)
        cv2.circle(panel, (cx, cy), 5, (0, 255, 136), -1)
        cv2.circle(panel, (cx, cy), 10, (0, 180, 80), 1)

        # HUD: distanta frontala si validare liveness (σ)
        front_dist = self.lidar.get_distance()
        sigma_mm   = self.lidar.get_liveness_sigma()
        connected  = self.lidar.is_connected()
        reason     = self.lidar.get_invalid_reason()

        if not connected:
            status_text  = "LiDAR: OFFLINE"
            status_color = (100, 100, 100)
        elif front_dist is None:
            status_text  = "LiDAR: No object in range"
            status_color = (80, 180, 255)
        elif self.lidar.validate_presence():
            sigma_str = f"{sigma_mm:.1f}mm" if sigma_mm is not None else "N/A"
            status_text  = f"LiDAR: {front_dist:.2f}m  sigma={sigma_str} — VALID (LIVE)"
            status_color = (0, 255, 136)
            # Desenează distanța frontală pe radar
            r_front = int((front_dist / MAX_DIST) * SCALE)
            cv2.circle(panel, (cx, cy - r_front), 8, (0, 255, 136), 2)
            cv2.line(panel, (cx, cy), (cx, cy - r_front), (0, 200, 100), 1)
        elif reason == "flat_surface_detected":
            sigma_str = f"{sigma_mm:.1f}mm" if sigma_mm is not None else "N/A"
            status_text  = f"LiDAR: {front_dist:.2f}m  sigma={sigma_str} — FLAT SURFACE (spoof?)"
            status_color = (109, 77, 255)
        elif reason == "liveness_uncertain":
            sigma_str = f"{sigma_mm:.1f}mm" if sigma_mm is not None else "N/A"
            status_text  = f"LiDAR: {front_dist:.2f}m  sigma={sigma_str} — UNCERTAIN"
            status_color = (255, 165, 0)
        elif front_dist < 0.2:
            status_text  = f"LiDAR: {front_dist:.2f}m — TOO CLOSE"
            status_color = (0, 165, 255)
        else:
            status_text  = f"LiDAR: {front_dist:.2f}m — TOO FAR"
            status_color = (0, 165, 255)

        # Banner status jos
        cv2.rectangle(panel, (0, H - 56), (W, H), (15, 20, 28), cv2.FILLED)
        cv2.putText(panel, status_text, (16, H - 30), font, 0.55,
                    status_color, 1, cv2.LINE_AA)

        # Viteza rotatie
        speed = self.lidar.get_speed()
        if speed > 0:
            cv2.putText(panel, f"{speed:.0f} deg/s", (W - 120, H - 30),
                        font, 0.4, (0, 120, 60), 1, cv2.LINE_AA)

        # Titlu
        cv2.putText(panel, "LD06  LIDAR  RADAR", (16, 28), font, 0.5,
                    (0, 200, 100), 1, cv2.LINE_AA)
        cv2.putText(panel, f"POINTS: {len(points)}", (W - 130, 28),
                    font, 0.4, (0, 120, 60), 1, cv2.LINE_AA)

        return panel

    def _update(self):
        if not self.is_running or not self.cap: return
        ret, frame = self.cap.read()
        if ret and frame is not None:
            # Flux 1: RGB prin VisionEngine
            processed, emails = self.vision.process_frame(frame.copy())
            sm = cv2.resize(processed, (640, 480))
            rgb = cv2.cvtColor(sm, cv2.COLOR_BGR2RGB)
            tk_img = ctk.CTkImage(Image.fromarray(rgb), size=(480, 340))
            self._rgb_ref = tk_img
            self.lbl_rgb.configure(image=tk_img, text="")

            # Flux 2: LiDAR Radar real (date de la RPi5)
            lidar_panel = self._make_lidar_frame()
            lidar_rgb = cv2.cvtColor(lidar_panel, cv2.COLOR_BGR2RGB)
            tk_img2 = ctk.CTkImage(Image.fromarray(lidar_rgb), size=(480, 340))
            self._lidar_ref = tk_img2
            self.lbl_lidar.configure(image=tk_img2, text="")

            # Actualizare status LiDAR in sidebar
            lidar_text, lidar_color = self.lidar.get_status_text()
            self.lidar_status_lbl.configure(text=lidar_text, text_color=lidar_color)

            # Salvare automata prezente cu validare LiDAR
            sel = self.lab_var.get()
            if sel in self.lab_ids:
                lab_id = self.lab_ids[sel]
                for email in emails:
                    if email == "Necunoscut":
                        continue
                    if email in self.prezenti:
                        continue

                    # Validare LiDAR: persoana trebuie sa fie fizic prezenta (0.2m–1.0m)
                    # si clasificatorul de liveness (σ) trebuie sa confirme relief 3D
                    # real (anti-spoofing — elimina telefoane/poze/ecrane plate)
                    if not self.lidar.validate_presence():
                        dist = self.lidar.get_distance()
                        if dist is None and not self.lidar.is_connected():
                            # LiDAR offline — inregistram doar pe baza camerei (fallback)
                            pass
                        else:
                            reason = self.lidar.get_invalid_reason()
                            if reason == "flat_surface_detected":
                                msg = f"! {email.split('@')[0].upper()} — FLAT SURFACE DETECTED (SPOOFING BLOCKED)"
                            elif reason == "liveness_uncertain":
                                msg = f"! {email.split('@')[0].upper()} — LIVENESS UNCERTAIN, RETRYING"
                            else:
                                msg = f"! {email.split('@')[0].upper()} DETECTED — LIDAR VALIDATION FAILED"
                            self._set_event(msg, C["warn"])
                            continue

                    self.prezenti.add(email)
                    save_prezenta(email, lab_id)
                    name = email.split("@")[0]
                    self._set_event(f"✓ ATTENDANCE RECORDED — {name.upper()}", C["primary"])
                    self.after(4000, lambda: self._set_event("> Scanning...", C["text_dim"]))

        self.after(30, self._update)

    def _set_event(self, msg, color):
        self.event_lbl.configure(text=msg, text_color=color)

    def _logout(self):
        self._stop()
        self.controller.current_user = None
        self.controller.show_frame("LoginFrame")


# Dashboard student
class StudentDashboard(ctk.CTkFrame):
    def __init__(self, master, controller):
        super().__init__(master, fg_color=C["bg"])
        self.controller = controller

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Top Navigation Bar curat
        topbar = ctk.CTkFrame(self, fg_color=C["sidebar"], corner_radius=0, height=56)
        topbar.grid(row=0, column=0, sticky="ew")
        topbar.grid_propagate(False)

        left = ctk.CTkFrame(topbar, fg_color="transparent")
        left.place(relx=0.02, rely=0.5, anchor="w")
        ctk.CTkLabel(left, text="SECUREPASS AI", font=("Courier New", 14, "bold"), text_color=C["primary"]).pack(
            side="left", padx=(0, 16))
        ctk.CTkLabel(left, text="/ STUDENT PORTAL", font=FONT_MONO, text_color=C["text_dim"]).pack(side="left")

        ctk.CTkButton(topbar, text="LOGOUT", width=90, height=30, corner_radius=3,
                      fg_color="transparent", border_width=1, border_color=C["border"],
                      text_color=C["text_dim"], font=FONT_SMALL, hover_color=C["card"],
                      command=self._logout).place(relx=0.97, rely=0.5, anchor="e")

        # Scrollable Body Container
        body = ctk.CTkScrollableFrame(self, fg_color="transparent", scrollbar_button_color=C["border"])
        body.grid(row=1, column=0, sticky="nsew", padx=40, pady=24)

        # Profile Greetings
        self.welcome = ctk.CTkLabel(body, text="", font=("Courier New", 24, "bold"), text_color=C["text"])
        self.welcome.pack(anchor="w")
        self.sub = ctk.CTkLabel(body, text="", font=FONT_MONO, text_color=C["text_dim"])
        self.sub.pack(anchor="w", pady=(2, 24))

        # Randul cu KPI Cards (Statistici mari stilizate)
        self.stats_row = ctk.CTkFrame(body, fg_color="transparent")
        self.stats_row.pack(fill="x", pady=(0, 28))

        # Panou Biometric Enrollment (Management imagini personale)
        enroll_hdr = ctk.CTkFrame(body, fg_color="transparent")
        enroll_hdr.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(enroll_hdr, text="FACE  ENROLLMENT", font=("Courier New", 13, "bold"),
                     text_color=C["text_dim"]).pack(side="left")

        enroll_card = ctk.CTkFrame(body, fg_color=C["panel"], corner_radius=4, border_width=1, border_color=C["border"])
        enroll_card.pack(fill="x", pady=(0, 28))

        info_row = ctk.CTkFrame(enroll_card, fg_color="transparent")
        info_row.pack(fill="x", padx=20, pady=(16, 0))

        left_info = ctk.CTkFrame(info_row, fg_color="transparent")
        left_info.pack(side="left", fill="both", expand=True)

        tlabel(left_info, "> Upload clear, front-facing photos of your face for recognition.", color=C["text"]).pack(
            anchor="w")
        tlabel(left_info, "> Recommended: 10–20 photos in different lighting conditions.", color=C["text_dim"]).pack(
            anchor="w", pady=(2, 0))
        tlabel(left_info, "> Supported formats: JPG, JPEG, PNG", color=C["text_dim"]).pack(anchor="w", pady=(2, 8))

        # Counter mare pe dreapta cardului
        self.enroll_count_frame = ctk.CTkFrame(info_row, fg_color=C["card"], corner_radius=4, width=120, height=70)
        self.enroll_count_frame.pack(side="right", padx=(20, 0))
        self.enroll_count_frame.pack_propagate(False)
        self.enroll_count_val = ctk.CTkLabel(self.enroll_count_frame, text="0", font=("Courier New", 28, "bold"),
                                             text_color=C["blue"])
        self.enroll_count_val.place(relx=0.5, rely=0.38, anchor="center")
        ctk.CTkLabel(self.enroll_count_frame, text="PHOTOS", font=("Courier New", 9), text_color=C["text_dim"]).place(
            relx=0.5, rely=0.78, anchor="center")

        sep(enroll_card)

        # Zona actiuni incarcare
        ctrl_row = ctk.CTkFrame(enroll_card, fg_color="transparent")
        ctrl_row.pack(fill="x", padx=20, pady=(0, 16))

        ctk.CTkButton(ctrl_row, text="📂  SELECT PHOTOS", height=42, corner_radius=3,
                      fg_color=C["blue"], hover_color="#1E90C0", text_color=C["bg"], font=FONT_BTN,
                      command=self._upload_photos).pack(side="left", padx=(0, 10))

        ctk.CTkButton(ctrl_row, text="🗑  CLEAR MY PHOTOS", height=42, corner_radius=3,
                      fg_color="transparent", border_width=1, border_color=C["danger"], text_color=C["danger"],
                      font=FONT_SMALL, hover_color=C["card"], command=self._clear_photos).pack(side="left")

        self.enroll_msg = ctk.CTkLabel(ctrl_row, text="", font=FONT_SMALL, text_color=C["primary"])
        self.enroll_msg.pack(side="left", padx=16)

        # SECTIUNE NOUA UX: Previzualizarea miniaturilor din dataset
        self.preview_frame = ctk.CTkFrame(enroll_card, fg_color=C["card"], corner_radius=3, height=100)
        self.preview_frame.pack(fill="x", padx=20, pady=(0, 16))
        self.preview_frame.pack_propagate(False)
        self._preview_label = ctk.CTkLabel(self.preview_frame, text="> No photos uploaded yet.", font=FONT_SMALL,
                                           text_color=C["text_dim"])
        self._preview_label.place(relx=0.5, rely=0.5, anchor="center")
        self._preview_refs = []  # Previne curățarea automată Garbage Collector a pozelor din RAM

        # Sectiune istoric Log-uri prezențe
        ctk.CTkLabel(body, text="ATTENDANCE  LOG", font=("Courier New", 13, "bold"), text_color=C["text_dim"]).pack(
            anchor="w", pady=(0, 8))

        # Cap de tabel curat
        th = ctk.CTkFrame(body, fg_color=C["card"], corner_radius=3, border_width=1, border_color=C["border"],
                          height=36)
        th.pack(fill="x")
        th.pack_propagate(False)
        for txt, w in [("SUBJECT", 260), ("DATE & TIME", 220), ("STATUS", 100)]:
            ctk.CTkLabel(th, text=txt, width=w, anchor="w", font=("Courier New", 10, "bold"),
                         text_color=C["text_dim"]).pack(side="left", padx=14)

        # Container dinamic pentru randuri
        self.rows_frame = ctk.CTkFrame(body, fg_color="transparent")
        self.rows_frame.pack(fill="x", pady=4)

    def _get_student_folder(self):
        email = self.controller.current_user["email"]
        folder = os.path.join(DATASET_PATH, email)
        os.makedirs(folder, exist_ok=True)
        return folder

    def _upload_photos(self):
        paths = fd.askopenfilenames(
            title="Select face photos",
            filetypes=[("Image files", "*.jpg *.jpeg *.png"), ("All files", "*.*")]
        )
        if not paths: return

        folder = self._get_student_folder()
        existing = count_student_photos(self.controller.current_user["email"])
        copied = 0
        skipped = 0

        for src in paths:
            ext = os.path.splitext(src)[1].lower()
            dest = os.path.join(folder, f"{existing + copied + 1:03d}{ext}")
            try:
                # Validare OpenCV de baza ca fisierul nu e corupt
                test = cv2.imread(src)
                if test is None:
                    skipped += 1
                    continue
                shutil.copy2(src, dest)
                copied += 1
            except Exception as e:
                print(f"[UPLOAD FAIL] {e}")
                skipped += 1

        total = count_student_photos(self.controller.current_user["email"])
        self.enroll_count_val.configure(text=str(total))

        if copied > 0:
            msg = f"✓ {copied} photo(s) uploaded successfully."
            if skipped > 0: msg += f" ({skipped} corrupted skipped)"
            self.enroll_msg.configure(text=msg, text_color=C["primary"])
        else:
            self.enroll_msg.configure(text="! No valid images were loaded.", text_color=C["danger"])

        self._refresh_preview()

    def _clear_photos(self):
        email = self.controller.current_user["email"]
        n = count_student_photos(email)
        if n == 0:
            self.enroll_msg.configure(text="> No photos to delete.", text_color=C["text_dim"])
            return

        confirm = mb.askyesno("Clear Photos",
                              f"Delete all {n} biometric photo(s) for {email}?\n\nThe model will auto-adapt to changes.")
        if not confirm: return

        folder = self._get_student_folder()
        for f in os.listdir(folder):
            if f.lower().endswith((".jpg", ".jpeg", ".png")):
                try:
                    os.remove(os.path.join(folder, f))
                except:
                    pass

        self.enroll_count_val.configure(text="0")
        self.enroll_msg.configure(text="✓ Dataset cleared successfully.", text_color=C["warn"])
        self._refresh_preview()

    def _refresh_preview(self):
        """Reîncarcă dinamic o bară orizontală cu primele 10 poze din folder ca thumbnails."""
        for w in self.preview_frame.winfo_children():
            w.destroy()
        self._preview_refs = []

        email = self.controller.current_user["email"]
        folder = os.path.join(DATASET_PATH, email)
        if not os.path.isdir(folder):
            self._preview_label = ctk.CTkLabel(self.preview_frame, text="> No photos uploaded yet.", font=FONT_SMALL,
                                               text_color=C["text_dim"])
            self._preview_label.place(relx=0.5, rely=0.5, anchor="center")
            return

        files = sorted([f for f in os.listdir(folder) if f.lower().endswith((".jpg", ".jpeg", ".png"))])

        if not files:
            lbl = ctk.CTkLabel(self.preview_frame, text="> No photos uploaded yet.", font=FONT_SMALL,
                               text_color=C["text_dim"])
            lbl.place(relx=0.5, rely=0.5, anchor="center")
            return

        thumb_size = 80
        x_offset = 10
        for fname in files[:10]:
            path = os.path.join(folder, fname)
            try:
                img = Image.open(path).convert("RGB")
                img.thumbnail((thumb_size, thumb_size))
                ctk_img = ctk.CTkImage(img, size=(thumb_size, thumb_size))
                lbl = ctk.CTkLabel(self.preview_frame, image=ctk_img, text="")
                lbl.place(x=x_offset, y=10)
                self._preview_refs.append(ctk_img)
                x_offset += thumb_size + 6
            except:
                pass

        if len(files) > 10:
            ctk.CTkLabel(self.preview_frame, text=f"+{len(files) - 10} more", font=FONT_SMALL,
                         text_color=C["text_dim"]).place(x=x_offset + 4, y=40)

    def _stat_card(self, title, value, color):
        card = ctk.CTkFrame(self.stats_row, fg_color=C["panel"], corner_radius=4, border_width=1,
                            border_color=C["border"], width=170, height=76)
        card.pack(side="left", padx=(0, 14))
        card.pack_propagate(False)
        ctk.CTkLabel(card, text=value, font=("Courier New", 26, "bold"), text_color=color).place(relx=0.5, rely=0.38,
                                                                                                 anchor="center")
        ctk.CTkLabel(card, text=title, font=("Courier New", 9), text_color=C["text_dim"]).place(relx=0.5, rely=0.75,
                                                                                                anchor="center")

    def refresh_data(self):
        user = self.controller.current_user
        if not user: return
        first = user["name"].split()[0]
        self.welcome.configure(text=f"HELLO,  {first.upper()}")
        self.sub.configure(text=f"> {user['email']}  //  ROLE: STUDENT")

        # Refresh KPI cards
        for w in self.stats_row.winfo_children(): w.destroy()
        records = get_student_stats(user["email"])
        total = len(records)
        subjects = len({r[0] for r in records})
        self._stat_card("TOTAL ATTENDED", str(total), C["primary"])
        self._stat_card("SUBJECTS", str(subjects), C["blue"])

        n_photos = count_student_photos(user["email"])
        self.enroll_count_val.configure(text=str(n_photos))
        self._refresh_preview()

        self.enroll_msg.configure(text="")

        # Refresh log rows
        for w in self.rows_frame.winfo_children(): w.destroy()
        if not records:
            ctk.CTkLabel(self.rows_frame, text="> No attendance records yet.", font=FONT_MONO,
                         text_color=C["text_dim"]).pack(anchor="w", pady=16)
            return

        for sub, ts in records:
            row = ctk.CTkFrame(self.rows_frame, fg_color=C["panel"], corner_radius=3, border_width=1,
                               border_color=C["border"], height=46)
            row.pack(fill="x", pady=2)
            row.pack_propagate(False)
            ctk.CTkLabel(row, text=sub, width=260, anchor="w", font=FONT_MONO, text_color=C["text"]).pack(side="left",
                                                                                                          padx=14)
            ctk.CTkLabel(row, text=str(ts).split(".")[0], width=220, anchor="w", font=FONT_SMALL,
                         text_color=C["text_dim"]).pack(side="left")

            # Badge stilizat de prezenta
            badge = ctk.CTkFrame(row, width=70, height=24, corner_radius=3, fg_color=C["primary"])
            badge.pack(side="left")
            badge.pack_propagate(False)
            ctk.CTkLabel(badge, text="PRESENT", font=("Courier New", 9, "bold"), text_color=C["bg"]).place(relx=0.5,
                                                                                                           rely=0.5,
                                                                                                           anchor="center")

    def tkraise(self, *args, **kwargs):
        super().tkraise(*args, **kwargs)
        self.refresh_data()

    def _logout(self):
        self.controller.current_user = None
        self.controller.show_frame("LoginFrame")


# FUNDAȚIE CONTEXT APPLICAȚIE
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("SecurePass AI — Biometric Attendance System")
        self.geometry("1400x860")
        self.minsize(1100, 700)
        self.current_user = None

        container = ctk.CTkFrame(self, fg_color=C["bg"])
        container.pack(fill="both", expand=True)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self.frames = {}
        for F in (LoginFrame, SignupFrame, ProfessorDashboard, StudentDashboard):
            f = F(master=container, controller=self)
            self.frames[F.__name__] = f
            f.grid(row=0, column=0, sticky="nsew")

        self.show_frame("LoginFrame")

    def show_frame(self, name):
        self.frames[name].tkraise()


if __name__ == "__main__":
    init_db()
    app = App()
    app.mainloop()