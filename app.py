"""
Safe ROAD v2 - educational driving platform (single-file Streamlit app).

HOW TO RUN
    pip install streamlit pandas          (Streamlit 1.40 or newer)
    python -m streamlit run app_v2.py

OPTIONAL: set the ANTHROPIC_API_KEY environment variable (and `pip install anthropic`) so the assistant
orb can answer ANY question with Claude. Without it, the orb answers about the app using built-in logic.

FILES (put them in the SAME folder as app_v2.py, or in a sub-folder called "datos"):
    Usuarios.csv, Cursos_y_Videos.csv, Partes_Coche.csv, Misiones.csv,
    Registro_Diario_Rachas.csv, Asistente_IA_Guias.csv
    Optional: img/partes/*.png  (part pictures, the paths come from Partes_Coche.csv)

Your CSV files are only READ. Each user's progress (XP, streak, course progress,
medals, contacts, notes...) is saved in "saveroad_estado.json" next to this file.
Delete that file to reset everybody.
"""

import base64
import hashlib
import html as htmllib
import json
import math
import mimetypes
import os
import random
import re
import unicodedata
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Safe ROAD", page_icon="🚗", layout="centered",
                   initial_sidebar_state="collapsed")

# ----------------------------------------------------------------------------
# 1. CONSTANTS
# ----------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIRS = [os.path.join(BASE_DIR, "datos"), BASE_DIR]
STATE_FILE = os.path.join(BASE_DIR, "saveroad_estado.json")

FILES = {
    "usuarios": "Usuarios.csv",
    "cursos": "Cursos_y_Videos.csv",
    "partes": "Partes_Coche.csv",
    "misiones": "Misiones.csv",
    "rachas": "Registro_Diario_Rachas.csv",
    "guias": "Asistente_IA_Guias.csv",
}

CORAL, AQUA, SLATE = "#FF6349", "#49E0FF", "#1E293B"
MAX_WIDTH = 780                       # page width in px (original brief: ~700)
PAGES = ["Inicio", "Cursos", "Mantenimiento", "Misiones", "Perfil"]
PARTS_UNLOCK_LEVEL = 15
XP_PER_LEVEL = 100
MAX_CONTACTS = 5
PHONE_RE = re.compile(r"^\+?[0-9 ()-]{7,18}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

TIERS = {  # medal -> (emoji, colour)
    "Oro": ("🥇", "#F5B301"), "Plata": ("🥈", "#94A3B8"),
    "Bronce": ("🥉", "#CD7F32"), "Bloqueada": ("🔒", "#94A3B8"),
}
MISSION_XP = {"Bronce": 50, "Plata": 100, "Oro": 200}
PARKING_LINK = ("Mision_02", "CRS_102")   # mission progress follows this course
PARTS_MISSION = "Mision_04"               # +10% for each new part you open
ASSISTANT_MODEL = "claude-haiku-5-5"      # model used when ANTHROPIC_API_KEY is set
VEHICLE_TYPES = {"Urbana": "🚗 Urbana", "SUV": "🚙 SUV familiar", "Aventura": "🏕️ Aventura",
                 "Pickup": "🛻 Pickup (tipo F-150)", "4x4": "🏔️ 4x4 todoterreno", "Deportivo": "🏎️ Deportivo (supercar)"}
QUICK_QUESTIONS = ["¿Cómo compro algo?", "¿Qué curso me recomiendas?", "¿Cómo agrego un contacto SOS?", "¿Qué significa un testigo rojo?"]
MAINT_COURSE = "CRS_104"                  # maintenance video shown inside part pages

# Editable extras (your CSVs do not have these columns).
COURSE_LEVEL = {"CRS_101": "Principiante", "CRS_102": "Principiante", "CRS_103": "Avanzado",
                "CRS_104": "Todos", "CRS_105": "Avanzado", "CRS_106": "Avanzado"}

# DEMO values (category, emoji, difficulty, minutes, location, price MXN). Replace freely.
PARTS_META = {
    "Neumatico_de_repuesto": ("Llantas y frenos", "🛞", "Fácil", 15, "Cajuela, bajo el piso", 1200),
    "Bateria_de_12V": ("Eléctrico", "🔋", "Media", 20, "Compartimento del motor", 1850),
    "Filtro_de_aire_del_motor": ("Motor", "🌬️", "Fácil", 10, "Caja de aire del motor", 260),
    "Varilla_de_nivel_de_aceite": ("Motor", "🛢️", "Fácil", 5, "Motor, mango de color", 90),
    "Deposito_de_liquido_de_frenos": ("Llantas y frenos", "🛑", "Fácil", 5, "Compartimento del motor", 150),
    "Fusibles_automotrices": ("Eléctrico", "⚡", "Fácil", 10, "Caja de fusibles", 60),
    "Parachoques": ("Carrocería", "🚗", "Difícil", 90, "Frente y parte trasera", 2400),
    "Intermitentes": ("Luces y visibilidad", "💡", "Fácil", 10, "Esquinas del vehículo", 120),
    "Rines": ("Llantas y frenos", "⚙️", "Media", 25, "Ruedas", 3200),
    "Pistones": ("Motor", "🔩", "Difícil", 480, "Interior del motor", 1900),
    "Testigos": ("Tablero", "🚨", "Fácil", 5, "Tablero de instrumentos", 0),
    "Palanca_de_cambios": ("Transmisión", "🕹️", "Media", 30, "Consola central", 800),
    "Espejos": ("Luces y visibilidad", "🪞", "Media", 20, "Puertas", 450),
    "Faros_delanteros": ("Luces y visibilidad", "🔦", "Media", 25, "Frente del vehículo", 1600),
    "Radiadores": ("Motor", "🌡️", "Media", 45, "Frente del compartimento del motor", 2800),
}
CAT_COLORS = {
    "Motor": ("#FF6349", "#FF9472"), "Eléctrico": ("#49E0FF", "#7C83FD"),
    "Llantas y frenos": ("#1E293B", "#475569"), "Carrocería": ("#F5B301", "#FFD86B"),
    "Luces y visibilidad": ("#A78BFA", "#F0ABFC"), "Tablero": ("#EF4444", "#FB923C"),
    "Transmisión": ("#10B981", "#6EE7B7"), "General": ("#64748B", "#94A3B8"),
}

# Words that lose their accents in the CSV files (underscores are also turned into spaces).
ACCENTS = {
    "Senalizacion": "Señalización", "Senales": "Señales", "Transito": "Tránsito", "Tecnicas": "Técnicas",
    "Conduccion": "Conducción", "Automovil": "Automóvil", "Revision": "Revisión", "liquidos": "líquidos",
    "Prevencion": "Prevención", "Capitan": "Capitán", "Neumatico": "Neumático", "Bateria": "Batería",
    "Deposito": "Depósito", "liquido": "líquido", "hidraulico": "hidráulico", "espanola": "española",
    "torquimetro": "torquímetro", "Escaner": "Escáner", "Mision": "Misión", "Mecanico": "Mecánico",
    "Guardian": "Guardián", "Via": "Vía", "Vision": "Visión", "Dias": "Días", "Dia": "Día", "Cupon": "Cupón",
    "cupon": "cupón", "Maximo": "Máximo", "Maxima": "Máxima", "Expres": "Exprés", "tecnico": "técnico",
    "Diagnostico": "Diagnóstico", "Rapido": "Rápido", "menu": "menú", "Menu": "Menú", "pestana": "pestaña",
    "numero": "número", "Numero": "Número", "telefonico": "telefónico", "articulo": "artículo",
    "codigo": "código", "Simulacion": "Simulación", "transaccion": "transacción", "Transaccion": "Transacción",
    "Mecanica": "Mecánica", "mecanica": "mecánica", "boton": "botón", "Boton": "Botón", "Asegurese": "Asegúrese",
    "medicion": "medición", "unicamente": "únicamente", "patron": "patrón", "arnes": "arnés",
    "Toxico": "Tóxico", "detencion": "detención", "inspeccion": "inspección", "Automaticamente": "Automáticamente",
    "basicas": "básicas", "Basico": "Básico", "basico": "básico", "opcion": "opción", "Opcion": "Opción",
    "seccion": "sección", "Seccion": "Sección", "Espanola": "Española", "vehiculo": "vehículo", "Vehiculo": "Vehículo", "Multimetro": "Multímetro", "mecanico": "mecánico", "Ing": "Ing.", "Dra": "Dra.", "Mec": "Mec.", "Garza": "Garza", "Lopez": "López", "Roberto": "Roberto",
}

QUIZ = [
    {"q": "¿Qué distancia mínima de seguimiento se recomienda en condiciones normales?",
     "o": ["1 segundo", "3 segundos", "Medio segundo", "No importa si voy atento"], "a": 1},
    {"q": "El semáforo cambia a ámbar y puedes frenar con seguridad. ¿Qué haces?",
     "o": ["Acelero para pasar", "Me detengo", "Toco el claxon", "Cambio de carril"], "a": 1},
    {"q": "Se enciende la luz roja de presión de aceite. Lo correcto es:",
     "o": ["Seguir hasta llegar", "Ignorarla de noche", "Orillarme y apagar el motor", "Subir el aire acondicionado"], "a": 2},
    {"q": "Con lluvia fuerte, lo más seguro es:",
     "o": ["Reducir velocidad y aumentar distancia", "Usar luces altas", "Frenar de golpe", "Pegarme al auto de adelante"], "a": 0},
    {"q": "¿Quién debe usar el cinturón de seguridad?",
     "o": ["Solo el conductor", "Solo en carretera", "Todos los ocupantes, siempre", "Solo los de adelante"], "a": 2},
]
ONBOARDING_STEPS = [
    ("👋 Bienvenido a Safe ROAD", "Aprende a conducir con seguridad paso a paso: cursos en video, clases en vivo y misiones divertidas."),
    ("🔥 Rachas y medallas", "Practica cada día para mantener tu racha, gana XP, sube de nivel y desbloquea medallas y cupones."),
    ("🔧 Mantenimiento y emergencias", "Catálogo de refacciones (nivel 15), guías, un asistente paso a paso y tus contactos de emergencia."),
]
LIVE_SESSIONS = [
    {"id": "L01", "tema": "Q&A: tu primer examen de manejo", "instructor": "Ing. Roberto Garza", "hora": "Hoy · 18:00", "en_vivo": True},
    {"id": "L02", "tema": "Mantenimiento en 15 minutos", "instructor": "Mec. Javier López", "hora": "Mañana · 19:00", "en_vivo": False},
    {"id": "L03", "tema": "Frenado ABS en la práctica", "instructor": "Dra. Laura Andrade", "hora": "Sábado · 11:00", "en_vivo": False},
]
GUIDES = {
    "🛞 Revisar la presión de las llantas": ["Hazlo con las llantas frías.", "Consulta la presión en la etiqueta de la puerta.", "Revisa las cuatro llantas y la de refacción."],
    "🛢️ Revisar el nivel de aceite": ["Estaciona en plano y espera 10 minutos con el motor apagado.", "Saca la varilla, límpiala, insértala y vuelve a sacarla.", "El nivel debe estar entre MIN y MAX."],
    "🛑 Señales de frenos desgastados": ["Chillido metálico al frenar o pedal muy bajo.", "Vibración en el volante al frenar.", "Ante cualquiera de estas señales, acude a un taller."],
}
GUIDE_KEYWORDS = {
    "GUA_01": ["sos", "contacto", "emergencia", "numero", "número", "ajustes"],
    "GUA_02": ["compra", "tienda", "carrito", "cupon", "cupón", "descuento", "comprar", "pagar"],
    "GUA_03": ["falla", "testigo", "luz", "tablero", "mecanica", "mecánica", "motor", "diagnostico", "diagnóstico"],
}


# ----------------------------------------------------------------------------
# 2. TEXT HELPERS
# ----------------------------------------------------------------------------
def pretty(text) -> str:
    """'Estacionamiento_en_Reversa' -> 'Estacionamiento en Reversa' (+ accents)."""
    return " ".join(ACCENTS.get(w, w) for w in str(text).replace("_", " ").split())


def sentence(text) -> str:
    t = pretty(text)
    t = t[:1].upper() + t[1:]
    return t if t.endswith((".", "!", "?")) else t + "."


def esc(v) -> str:
    return htmllib.escape(str(v))


def ints(text) -> list:
    return [int(n) for n in re.findall(r"\d+", str(text))]


def yt_id(url: str) -> str:
    m = re.search(r"(?:v=|youtu\.be/|embed/)([\w-]{11})", str(url))
    return m.group(1) if m else ""


def money(x) -> str:
    return f"MXN {int(x):,}"


def initials_color(name: str) -> str:
    palette = [CORAL, "#0891B2", "#7C3AED", "#059669", "#D97706", "#DB2777"]
    return palette[sum(ord(c) for c in str(name)) % len(palette)]


def phone_digits(tel: str) -> str:
    return re.sub(r"[^\d+]", "", tel)


# ----------------------------------------------------------------------------
# 3. CATALOG LOADING (read-only CSVs)
# ----------------------------------------------------------------------------
def _norm(filename: str) -> str:
    """'Cursos_y_Videos (1).csv' -> 'cursos_y_videos' (ignores case, spaces/dashes and download suffixes)."""
    stem = re.sub(r"\s*\(\d+\)$", "", os.path.splitext(filename)[0])
    return re.sub(r"[\s-]+", "_", stem.strip()).lower()


def find_file(name: str):
    ext = os.path.splitext(name)[1].lower()
    for folder in DATA_DIRS:
        if not os.path.isdir(folder):
            continue
        for f in sorted(os.listdir(folder)):
            if os.path.splitext(f)[1].lower() == ext and _norm(f) == _norm(name):
                return os.path.join(folder, f)
    return None


def find_xlsx() -> list:
    out = []
    for folder in DATA_DIRS:
        if os.path.isdir(folder):
            out += [os.path.join(folder, f) for f in sorted(os.listdir(folder))
                    if f.lower().endswith(".xlsx") and not f.startswith("~$")]
    return out


def read_table(key: str):
    """Read one table from its CSV, or from a sheet of any .xlsx next to the app (needs openpyxl)."""
    path = find_file(FILES[key])
    if path:
        return read_csv(path)
    sheet = os.path.splitext(FILES[key])[0]
    for xlsx in find_xlsx():
        try:
            return pd.read_excel(xlsx, sheet_name=sheet, dtype=str).fillna("")
        except Exception:
            continue
    return None


def read_csv(path: str) -> pd.DataFrame:
    for enc in ("utf-8-sig", "latin-1"):
        try:
            return pd.read_csv(path, dtype=str, keep_default_na=False, encoding=enc)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"No se pudo leer {path}")


@st.cache_data(show_spinner=False)
def load_catalog(signature: tuple) -> dict:
    """Parse the six CSV files into plain Python structures. `signature` busts the cache when files change."""
    d = {k: read_table(k) for k in FILES}
    missing = [FILES[k] for k, t in d.items() if t is None]
    if missing:
        found = []
        for folder in DATA_DIRS:
            if os.path.isdir(folder):
                found += [f for f in sorted(os.listdir(folder)) if f.lower().endswith((".csv", ".xlsx"))]
        return {"missing": missing, "found": found}

    usuarios = [{"id": r["Identificacion"], "nombre": r["Nombre_usuario"], "email": r["Correo_electronico"],
                 "contacto_tel": pretty(r["Numero_de_contacto_de_emergencia"]),
                 "contacto_nombre": pretty(r["Nombre_del_contacto_de_emergencia"]),
                 "coche": pretty(r["Modelo_de_coche"])} for _, r in d["usuarios"].iterrows()]

    cursos = []
    for _, r in d["cursos"].iterrows():
        mins = (ints(r["Tiempo_del_video"]) or [15])[0]
        cursos.append({"id": r["ID_Curso"], "titulo": pretty(r["Curso"]), "instructor": pretty(r["Maestro"]),
                       "base_prog": min(100, (ints(r["Progreso"]) or [0])[0]), "minutos": mins,
                       "url": r["Enlace_del_video"].strip(), "vid": yt_id(r["Enlace_del_video"]),
                       "tema": pretty(r["Tema_del_video"]), "nivel": COURSE_LEVEL.get(r["ID_Curso"], "Todos")})

    partes = []
    for _, r in d["partes"].iterrows():
        key = r["Nombre_de_la_parte"]
        cat, emoji, dif, mins, ubic, precio = PARTS_META.get(key, ("General", "🔧", "Media", 15, "Consulta el manual", 0))
        herr = [sentence(h)[:-1] for h in re.split(r"_y_", r["Herramienta"]) if h]
        partes.append({"key": key, "nombre": pretty(key), "herramientas": herr,
                       "advertencia": sentence(r["Advertencia_de_seguridad"]), "imagen": r["Imagen_de_la_parte"].strip(),
                       "cat": cat, "emoji": emoji, "dif": dif, "min": mins, "ubic": ubic, "precio": precio})

    misiones = [{"id": r["Misiones"], "nombre": pretty(r["Nombre_de_la_mision"]),
                 "base_prog": min(100, (ints(r["Progreso_de_la_mision"]) or [0])[0]),
                 "medalla": r["Medalla"].strip(), "medalla_nombre": pretty(r["Nombre_de_la_medalla"])}
                for _, r in d["misiones"].iterrows()]

    rachas = []
    for _, r in d["rachas"].iterrows():
        nums = ints(r["Dias_de_Racha_Consecutivos"])
        rachas.append({"lo": nums[0], "hi": nums[1] if len(nums) > 1 else 10 ** 6, "nivel": pretty(r["Nivel_de_Racha"]),
                       "recompensa": pretty(r["Recompensa_Obtenida"]), "pct": (ints(r["Porcentaje_Descuento_Maximo"]) or [0])[0],
                       "estado": pretty(r["Estado_Recompensa"]), "doble": "Doble_XP" in r["Recompensa_Obtenida"]})

    guias = {}
    for _, r in d["guias"].iterrows():
        g = guias.setdefault(r["ID_Guia"], {"modulo": pretty(r["Modulo_Asistente"]), "pasos": []})
        g["pasos"].append((sentence(r["Instruccion_Paso_a_Paso"]), sentence(r["Accion_Requerida_Usuario"])))

    return {"missing": [], "usuarios": usuarios, "cursos": cursos, "partes": partes,
            "misiones": misiones, "rachas": rachas, "guias": guias}


def get_catalog() -> dict:
    paths = [find_file(f) for f in FILES.values()] + find_xlsx()
    return load_catalog(tuple(os.path.getmtime(p) for p in paths if p))


@st.cache_data(show_spinner=False)
def img_data_uri(rel_path: str, signature: float = 0.0):
    """Embed a local image so it can be shown inside HTML cards."""
    if not rel_path:
        return None
    for folder in DATA_DIRS:
        p = os.path.join(folder, rel_path)
        if os.path.isfile(p):
            mime = mimetypes.guess_type(p)[0] or "image/png"
            with open(p, "rb") as fh:
                return f"data:{mime};base64,{base64.b64encode(fh.read()).decode()}"
    return None


# ----------------------------------------------------------------------------
# 4. PER-USER STATE (saved in saveroad_estado.json)
# ----------------------------------------------------------------------------
def is_demo_user(uid: str) -> bool:
    return any(u["id"] == uid for u in st.session_state.cat["usuarios"])


def new_state(cat: dict, fresh: bool = False) -> dict:
    """Demo users start from the CSV progress; accounts created in the app start from zero."""
    xp = 0 if fresh else sum(c["base_prog"] for c in cat["cursos"]) + sum(m["base_prog"] for m in cat["misiones"])
    return {"xp": xp, "puntos": xp, "quiz_done": False, "nivel_experiencia": "Principiante",
            "vehiculo_tipo": "Urbana", "vehiculo_color": CORAL, "contactos": [],
            "curso_prog": {c["id"]: 0 for c in cat["cursos"]} if fresh else {},
            "mision_prog": {m["id"]: 0 for m in cat["misiones"]} if fresh else {}, "mision_reclamada": [], "mision_fecha": {}, "partes_vistas": [],
            "racha": {"dias": 0, "ultimo": ""}, "notas": {}, "historial": [], "cupones_usados": [],
            "ultimo_curso": ""}


def read_all_state() -> dict:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def S() -> dict:
    return st.session_state.state


def write_all_state(allst: dict) -> None:
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as fh:
            json.dump(allst, fh, ensure_ascii=False, indent=1)
    except OSError as exc:
        st.warning(f"No se pudo guardar el progreso: {exc}")


def save_state() -> None:
    allst = read_all_state()
    allst[st.session_state.user_id] = st.session_state.state
    write_all_state(allst)


# ---- accounts created with "Crear cuenta" (stored in the state file, password hashed)
def accounts() -> list:
    return read_all_state().get("_cuentas", [])


def hash_pw(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 120_000).hex()


def validate_signup(nombre, email, pw, pw2, coche, ctel, existing_emails) -> list:
    errors = []
    if len(nombre.strip()) < 3:
        errors.append("El nombre de usuario debe tener al menos 3 caracteres.")
    if not EMAIL_RE.match(email.strip()):
        errors.append("Escribe un correo electrónico válido.")
    elif email.strip().lower() in existing_emails:
        errors.append("Ese correo ya tiene una cuenta. Usa «Iniciar sesión».")
    if len(pw) < 6:
        errors.append("La contraseña debe tener al menos 6 caracteres.")
    elif pw != pw2:
        errors.append("Las contraseñas no coinciden.")
    if not coche.strip():
        errors.append("Escribe el modelo de tu coche.")
    if ctel.strip() and not PHONE_RE.match(ctel.strip()):
        errors.append("El teléfono del contacto no es válido.")
    return errors


def create_account(nombre, email, pw, coche, cnombre, ctel) -> str:
    cuentas = accounts()
    salt = os.urandom(16).hex()
    uid = f"USR_{101 + len(cuentas)}"
    cuentas.append({"id": uid, "nombre": nombre.strip(), "email": email.strip(), "coche": coche.strip(),
                    "contacto_nombre": cnombre.strip(), "contacto_tel": ctel.strip(), "salt": salt, "hash": hash_pw(pw, salt)})
    allst = read_all_state()
    allst["_cuentas"] = cuentas
    write_all_state(allst)
    return uid


def check_login(email: str, pw: str):
    for a in accounts():
        if a["email"].lower() == email.strip().lower() and hash_pw(pw, a["salt"]) == a["hash"]:
            return a["id"]
    return None


def init_session(cat: dict) -> None:
    ss = st.session_state
    defaults = {"user_id": None, "state": None, "page": "Inicio", "ctx": None, "onb_step": 0, "quiz_result": None,
                "cart": [], "cart_coupon": "", "order_done": "", "family_seed": 1, "guide_step": 0,
                "chat": [], "guide_last": None, "guide_sel": next(iter(cat["guias"]), None)}
    for k, v in defaults.items():
        ss.setdefault(k, v)


def cur_user() -> dict:
    uid = st.session_state.user_id
    found = next((u for u in st.session_state.cat["usuarios"] if u["id"] == uid), None)
    return found or next(a for a in accounts() if a["id"] == uid)


# ----------------------------------------------------------------------------
# 5. GAME LOGIC
# ----------------------------------------------------------------------------
def level() -> int:
    return int(S()["xp"]) // XP_PER_LEVEL + 1


def log(text: str) -> None:
    S()["historial"].insert(0, {"ts": datetime.now().strftime("%d/%m %H:%M"), "texto": text})
    del S()["historial"][40:]


def add_xp(amount: int) -> int:
    mult = streak_multiplier()
    gained = amount * mult
    S()["xp"] += gained
    S()["puntos"] += gained
    save_state()
    st.toast(f"+{gained} XP" + (" · Doble XP 🔥" if mult > 1 else ""), icon="⭐")
    return gained


# ---- courses
def cprog(c: dict) -> int:
    return int(S()["curso_prog"].get(c["id"], c["base_prog"]))


def cstatus(p: int) -> str:
    return "Completado" if p >= 100 else "En progreso" if p > 0 else "No iniciado"


def set_course_progress(c: dict, new: int) -> None:
    before = cprog(c)
    new = max(0, min(100, new))
    S()["curso_prog"][c["id"]] = new
    S()["ultimo_curso"] = c["id"]
    if new >= 100 > before:
        log(f"Completaste «{c['titulo']}» (+50 XP)")
        add_xp(50)
    else:
        log(f"Avanzaste en «{c['titulo']}» ({new}%)")
        save_state()


def find_course(cid: str):
    return next((c for c in st.session_state.cat["cursos"] if c["id"] == cid), None)


def recommended(n: int = 3) -> list:
    cursos = st.session_state.cat["cursos"]
    lvl = S()["nivel_experiencia"]
    pend = [c for c in cursos if cprog(c) < 100]
    last = [c for c in pend if c["id"] == S()["ultimo_curso"]]
    inprog = [c for c in pend if cprog(c) > 0]
    fit = [c for c in pend if c["nivel"] in (lvl, "Todos")]
    out, seen = [], set()
    for c in last + inprog + fit + pend:
        if c["id"] not in seen:
            seen.add(c["id"])
            out.append(c)
    return out[:n]


# ---- missions
def mission_progress(m: dict) -> int:
    p = int(S()["mision_prog"].get(m["id"], m["base_prog"]))
    if m["id"] == PARKING_LINK[0]:
        c = find_course(PARKING_LINK[1])
        if c:
            p = max(p, cprog(c))
    return min(100, p)


def mission_index(m: dict) -> int:
    return st.session_state.cat["misiones"].index(m)


def mission_locked(m: dict) -> bool:
    i = mission_index(m)
    return m["medalla"] == "Bloqueada" and i > 0 and mission_progress(st.session_state.cat["misiones"][i - 1]) < 100


def mission_tier(m: dict) -> str:
    return "Bronce" if m["medalla"] == "Bloqueada" else m["medalla"]


def mission_done(m: dict) -> bool:
    return not mission_locked(m) and mission_progress(m) >= 100


def bump_mission(mid: str, amount: int) -> None:
    m = next((x for x in st.session_state.cat["misiones"] if x["id"] == mid), None)
    if m and not mission_locked(m):
        S()["mision_prog"][mid] = min(100, mission_progress(m) + amount)
        save_state()


def sync_unlocks() -> None:
    changed = False
    for m in st.session_state.cat["misiones"]:
        if mission_done(m) and m["id"] not in S()["mision_fecha"]:
            S()["mision_fecha"][m["id"]] = date.today().isoformat()
            changed = True
    if changed:
        save_state()


# ---- streak & coupons
def effective_days() -> int:
    r = S()["racha"]
    if r["ultimo"] in (date.today().isoformat(), (date.today() - timedelta(days=1)).isoformat()):
        return r["dias"]
    return 0


def tier_for(days: int):
    return next((t for t in st.session_state.cat["rachas"] if t["lo"] <= days <= t["hi"]), None)


def streak_multiplier() -> int:
    t = tier_for(effective_days())
    return 2 if t and t["doble"] else 1


def current_coupon():
    t = tier_for(effective_days())
    if t and t["pct"] > 0:
        code = f"RACHA{t['pct']}"
        if code not in S()["cupones_usados"]:
            return code, t["pct"]
    return None


def do_checkin() -> None:
    r, today = S()["racha"], date.today().isoformat()
    if r["ultimo"] == today:
        return
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    r["dias"] = r["dias"] + 1 if r["ultimo"] == yesterday else 1
    r["ultimo"] = today
    log(f"Racha diaria: día {r['dias']}")
    add_xp(10)


# ----------------------------------------------------------------------------
# 6. NAVIGATION CALLBACKS
# ----------------------------------------------------------------------------
def nav_to(page: str) -> None:
    st.session_state.page, st.session_state.ctx = page, None


def open_ctx(kind: str, item_id=None) -> None:
    st.session_state.ctx = (kind, item_id)


def go_back() -> None:
    st.session_state.ctx = None


def goto_part(key: str) -> None:
    st.session_state.page = "Mantenimiento"
    st.session_state.ctx = ("parte", key)


def login(uid: str) -> None:
    ss = st.session_state
    base = new_state(ss.cat, fresh=not is_demo_user(uid))
    ss.state = {**base, **read_all_state().get(uid, {})}
    ss.user_id, ss.page, ss.ctx = uid, "Inicio", None
    ss.onb_step, ss.quiz_result, ss.cart = 0, None, []


def logout() -> None:
    ss = st.session_state
    ss.user_id, ss.state, ss.ctx, ss.page = None, None, None, "Inicio"


# ----------------------------------------------------------------------------
# 7. STYLING + HTML HELPERS
# ----------------------------------------------------------------------------
def build_css() -> str:
    return """
<style>
.stApp { background: #F8F9FA; color: #1E293B; }
header[data-testid="stHeader"] { display: none; }
#MainMenu, footer { visibility: hidden; }
.block-container { max-width: %(w)spx; padding-top: 0.5rem; padding-bottom: 4rem; }
h1, h2, h3, h4, p, label { color: #1E293B; }

/* Sticky navbar */
.st-key-navbar { position: sticky; top: 0; z-index: 999; background: #FFFFFF; border: 1px solid #E2E8F0;
  border-radius: 0 0 18px 18px; padding: .6rem .8rem .3rem; box-shadow: 0 4px 14px rgba(30,41,59,.08); margin-bottom: 1rem; }
.st-key-navbar [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: .3rem; }
.st-key-navbar [data-testid="stColumn"] { min-width: 0 !important; }
.st-key-navbar .stButton > button { padding: .2rem .1rem; font-size: .78rem; min-height: 2rem; }
.sr-logo { font-weight: 800; font-size: 1.25rem; letter-spacing: -.5px; }
.sr-logo span { color: #FF6349; }
.sr-points { text-align: center; font-weight: 700; font-size: .9rem; padding-top: .25rem; }
.sr-avatar { width: 36px; height: 36px; border-radius: 50%%; background: #FF6349; color: #fff; display: flex;
  align-items: center; justify-content: center; font-weight: 700; margin-left: auto; }

/* Buttons */
.stButton > button, .stLinkButton > a { border-radius: 12px; font-weight: 600; border: 1px solid #E2E8F0; background: #fff;
  color: #1E293B; transition: transform .15s ease, box-shadow .15s ease; }
.stButton > button:hover, .stLinkButton > a:hover { transform: translateY(-2px); box-shadow: 0 6px 14px rgba(30,41,59,.12);
  border-color: #FF6349; color: #FF6349; }
.stButton > button[kind="primary"], .stButton > button[data-testid="stBaseButton-primary"] { background: #FF6349; border-color: #FF6349; color: #fff; }
.stButton > button[kind="primary"]:hover, .stButton > button[data-testid="stBaseButton-primary"]:hover { background: #e8523a; color: #fff; }

/* Generic cards / chips / bars */
.sr-card { background: #fff; border: 1px solid #E8ECF1; border-radius: 18px; padding: 1rem 1.1rem;
  box-shadow: 0 2px 10px rgba(30,41,59,.06); margin-bottom: .6rem; }
.sr-hero { background: linear-gradient(135deg, #FF6349 0%%, #ff8a73 100%%); color: #fff; border-radius: 20px; padding: 1.2rem 1.3rem;
  margin-bottom: 1rem; box-shadow: 0 8px 22px rgba(255,99,73,.3); }
.sr-hero h2, .sr-hero div { color: #fff !important; margin: 0; }
.sr-sub { opacity: .9; font-size: .85rem; }
.sr-title { font-weight: 700; font-size: 1rem; margin-bottom: .15rem; }
.sr-muted { color: #64748B; font-size: .82rem; }
.sr-chip { display: inline-block; padding: .12rem .6rem; border-radius: 999px; font-size: .72rem; font-weight: 700; margin: 0 .3rem .25rem 0; }
.sr-chip.coral { background: #FFE9E5; color: #FF6349; } .sr-chip.aqua { background: #DDF8FF; color: #0891B2; }
.sr-chip.gray { background: #EEF2F6; color: #64748B; } .sr-chip.white { background: rgba(255,255,255,.25); color: #fff; }
.sr-bar { width: 100%%; height: 9px; background: #EEF2F6; border-radius: 99px; overflow: hidden; margin: .4rem 0 .2rem; }
.sr-bar > span { display: block; height: 100%%; border-radius: 99px; transition: width .4s ease; }
.sr-tile { text-align: center; background: #fff; border: 2px solid #E8ECF1; border-radius: 18px; padding: .9rem .5rem;
  box-shadow: 0 2px 10px rgba(30,41,59,.06); margin-bottom: .4rem; }
.sr-tile .icon { font-size: 2.2rem; }
.sr-tile.locked { border-color: #E8ECF1 !important; }
.sr-tile.locked .icon { filter: grayscale(1); opacity: .45; }
.sr-video-ph { background: #1E293B; color: #fff; border-radius: 16px; padding: 2.5rem 1rem; text-align: center; margin-bottom: .6rem; }
.sr-locked { text-align: center; padding: 1.5rem 1rem; }

/* YouTube-style cards */
div[class*="st-key-card_"] { position: relative; margin-bottom: .9rem; }
div[class*="st-key-card_"] .stButton button { font-size: .8rem; padding: .15rem .5rem; min-height: 2rem; margin-top: .1rem; }
.vc-thumb { position: relative; width: 100%%; padding-top: 56.25%%; border-radius: 14px; overflow: hidden; background: #1E293B;
  box-shadow: 0 2px 10px rgba(30,41,59,.12); }
.vc-thumb img { position: absolute; inset: 0; width: 100%%; height: 100%%; object-fit: cover; transition: transform .3s ease; }
.vc-ph { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; font-size: 3rem; }
div[class*="st-key-card_"]:hover .vc-thumb img, div[class*="st-key-card_"]:hover .vc-ph { transform: scale(1.06); }
div[class*="st-key-card_"]:hover .vc-thumb { box-shadow: 0 10px 24px rgba(30,41,59,.22); }
.vc-dur { position: absolute; right: 8px; bottom: 12px; background: rgba(0,0,0,.82); color: #fff; font-size: .72rem; font-weight: 700;
  padding: .1rem .4rem; border-radius: 6px; }
.vc-tag { position: absolute; left: 8px; top: 8px; background: rgba(255,255,255,.92); color: #1E293B; font-size: .68rem; font-weight: 700;
  padding: .1rem .45rem; border-radius: 6px; }
.vc-prog { position: absolute; left: 0; right: 0; bottom: 0; height: 4px; background: rgba(255,255,255,.35); }
.vc-prog span { display: block; height: 100%%; background: #FF6349; }
.vc-prog.done span { background: #49E0FF; }
.vc-meta { display: flex; gap: .6rem; margin-top: .55rem; }
.vc-ava { width: 36px; height: 36px; flex: none; border-radius: 50%%; color: #fff; font-weight: 700; display: flex; align-items: center; justify-content: center; }
.vc-title { font-weight: 700; font-size: .92rem; line-height: 1.25; color: #1E293B; }
.vc-sub { color: #64748B; font-size: .78rem; margin-top: .1rem; }
.vr { display: flex; gap: .7rem; align-items: flex-start; }
.vr .vc-thumb { width: 42%%; flex: none; }
.vr .vc-meta { margin-top: 0; flex-direction: column; gap: 0; }

/* Assistant orb (floating, bottom-right) */
.st-key-orb { position: fixed; right: 18px; bottom: 18px; z-index: 1000; width: auto !important; }
.st-key-orb button { width: 64px; height: 64px; border-radius: 50%%; border: none; font-size: 1.7rem; color: #fff;
  background: radial-gradient(circle at 30%% 28%%, #ffffff 0%%, #49E0FF 30%%, #FF6349 100%%);
  box-shadow: 0 8px 22px rgba(255,99,73,.45); animation: orbpulse 2.4s infinite; transition: transform .2s ease; }
.st-key-orb button:hover { transform: scale(1.1); }
.st-key-orb button svg, .st-key-orb button [data-testid="stIconMaterial"] { display: none; }
@keyframes orbpulse {
  0%% { box-shadow: 0 0 0 0 rgba(73,224,255,.6), 0 8px 22px rgba(255,99,73,.45); }
  70%% { box-shadow: 0 0 0 18px rgba(73,224,255,0), 0 8px 22px rgba(255,99,73,.45); }
  100%% { box-shadow: 0 0 0 0 rgba(73,224,255,0), 0 8px 22px rgba(255,99,73,.45); }
}

/* Chat bubbles + light popover (readable even if the browser is in dark mode) */
.cb-user, .cb-bot { padding: .55rem .75rem; border-radius: 14px; margin: .3rem 0; font-size: .88rem; line-height: 1.4; color: #1E293B !important; }
.cb-user { background: #FFE9E5; margin-left: 1.5rem; }
.cb-bot { background: #EEF2F6; margin-right: 1.5rem; }
[data-testid="stPopoverBody"] { background: #FFFFFF !important; width: min(92vw, 400px); }
[data-testid="stPopoverBody"], [data-testid="stPopoverBody"] p, [data-testid="stPopoverBody"] label, [data-testid="stPopoverBody"] li,
[data-testid="stPopoverBody"] span, [data-testid="stPopoverBody"] div, [data-testid="stPopoverBody"] summary { color: #1E293B; }
[data-testid="stPopoverBody"] input { background: #F1F5F9 !important; color: #1E293B !important; }
[data-testid="stPopoverBody"] [data-baseweb="select"] > div { background: #F1F5F9 !important; }
[data-testid="stPopoverBody"] [data-testid="stAlert"] { background: #E8F6FF !important; }
[data-testid="stPopoverBody"] .stButton > button[kind="primary"] *, [data-testid="stPopoverBody"] [data-testid="stFormSubmitButton"] button[kind="primaryFormSubmit"] * { color: #fff !important; }
.stTabs [aria-selected="true"] p { color: #FF6349 !important; }

/* Tabs */
.stTabs [aria-selected="true"] { color: #FF6349 !important; }
.stTabs [data-baseweb="tab-highlight"] { background-color: #FF6349 !important; }
</style>
""" % {"w": MAX_WIDTH}


def H(s: str) -> str:
    """Strip indentation and blank lines so Markdown never turns HTML into a code block."""
    return "\n".join(line.strip() for line in s.splitlines() if line.strip())


def render(html_str: str) -> None:
    st.markdown(H(html_str), unsafe_allow_html=True)


def bar(pct, color: str = CORAL) -> str:
    pct = max(0, min(100, int(pct)))
    return f'<div class="sr-bar"><span style="width:{pct}%;background:{color}"></span></div>'


def chip(text: str, kind: str = "coral") -> str:
    return f'<span class="sr-chip {kind}">{esc(text)}</span>'


def video_card(thumb_inner: str, dur: str, title: str, sub: str, sub2: str = "", prog=None, tag: str = "",
               avatar: str = "S", color: str = CORAL, row: bool = False) -> str:
    prog_html = ""
    if prog is not None:
        prog_html = f'<div class="vc-prog {"done" if prog >= 100 else ""}"><span style="width:{max(0, min(100, prog))}%"></span></div>'
    tag_html = f'<span class="vc-tag">{esc(tag)}</span>' if tag else ""
    ava = "" if row else f'<div class="vc-ava" style="background:{color}">{esc(avatar)}</div>'
    sub2_html = f'<div class="vc-sub">{sub2}</div>' if sub2 else ""
    return H(f"""
    <div class="vc {'vr' if row else ''}">
      <div class="vc-thumb">{thumb_inner}{tag_html}<span class="vc-dur">{esc(dur)}</span>{prog_html}</div>
      <div class="vc-meta">{ava}<div><div class="vc-title">{esc(title)}</div><div class="vc-sub">{esc(sub)}</div>{sub2_html}</div></div>
    </div>""")


def clickable(key: str, html_block: str, callback, args: tuple, label: str = "Abrir") -> None:
    """A card with a visible button right under it."""
    with st.container(key=f"card_{key}"):
        render(html_block)
        st.button(label, key=f"go_{key}", on_click=callback, args=args, use_container_width=True)


def grid(items: list, draw, cols: int = 2) -> None:
    for i in range(0, len(items), cols):
        for col, item in zip(st.columns(cols), items[i:i + cols]):
            with col:
                draw(item)


def pills(label: str, options: list, key: str, default: str) -> str:
    if hasattr(st, "pills"):
        return st.pills(label, options, default=default, key=key, label_visibility="collapsed") or default
    return st.radio(label, options, horizontal=True, key=key, label_visibility="collapsed")


def course_thumb(c: dict) -> str:
    if c["vid"]:
        return f'<img src="https://img.youtube.com/vi/{c["vid"]}/hqdefault.jpg" alt="">'
    return '<div class="vc-ph" style="background:#1E293B">▶️</div>'


def course_card_html(c: dict, row: bool = False) -> str:
    p = cprog(c)
    return video_card(course_thumb(c), f"{c['minutos']}:00", c["titulo"], c["instructor"],
                      f"{esc(c['tema'])} · {cstatus(p)}" if not row else cstatus(p), prog=p, tag=c["nivel"] if not row else "",
                      avatar=c["instructor"].split()[-1][:1].upper(), color=initials_color(c["instructor"]), row=row)


def course_card(c: dict, prefix: str, row: bool = False) -> None:
    clickable(f"c_{prefix}_{c['id']}", course_card_html(c, row), open_ctx, ("curso", c["id"]), "▶ Ver" if row else "▶ Ver lección")


def part_thumb(p: dict) -> str:
    uri = img_data_uri(p["imagen"])
    if uri:
        return f'<img src="{uri}" alt="">'
    g1, g2 = CAT_COLORS.get(p["cat"], CAT_COLORS["General"])
    return f'<div class="vc-ph" style="background:linear-gradient(135deg,{g1},{g2})">{p["emoji"]}</div>'


def part_card_html(p: dict, row: bool = False) -> str:
    seen = p["key"] in S()["partes_vistas"]
    price = money(p["precio"]) if p["precio"] else "Guía de diagnóstico"
    return video_card(part_thumb(p), f"⏱ {p['min']} min", p["nombre"], p["cat"], f"{p['dif']} · {price}",
                      prog=100 if seen else None, avatar=p["nombre"][:1], color=CAT_COLORS.get(p["cat"], CAT_COLORS["General"])[0],
                      row=row)


def part_card(p: dict, prefix: str, row: bool = False) -> None:
    clickable(f"p_{prefix}_{p['key']}", part_card_html(p, row), open_ctx, ("parte", p["key"]), "Ver" if row else "Ver detalle")


# ----------------------------------------------------------------------------
# 8. SHARED UI
# ----------------------------------------------------------------------------
def navbar() -> None:
    u = cur_user()
    with st.container(key="navbar"):
        c1, c2, c3 = st.columns([2, 2, 1])
        c1.markdown('<div class="sr-logo">Safe<span>ROAD</span> 🚗</div>', unsafe_allow_html=True)
        c2.markdown(f'<div class="sr-points">🏆 {S()["puntos"]} pts</div>', unsafe_allow_html=True)
        c3.markdown(f'<div class="sr-avatar">{esc(u["nombre"][:1].upper())}</div>', unsafe_allow_html=True)
        for col, page in zip(st.columns(len(PAGES)), PAGES):
            col.button(page, key=f"nav_{page}", on_click=nav_to, args=(page,),
                       type="primary" if st.session_state.page == page else "secondary", use_container_width=True)


def back_button() -> None:
    st.button("← Volver", key="go_back", on_click=go_back)


def streak_card(key: str) -> None:
    days, r = effective_days(), S()["racha"]
    tier = tier_for(days)
    done_today = r["ultimo"] == date.today().isoformat()
    nxt = next((t for t in st.session_state.cat["rachas"] if t["lo"] > days), None)
    title = tier["nivel"] if tier else "Sin racha activa"
    reward = tier["recompensa"] if tier else "Registra tu práctica de hoy para empezar"
    goal = f"Faltan {nxt['lo'] - days} día(s) para «{nxt['nivel']}»" if nxt else "¡Recompensa máxima alcanzada!"
    pct = 100 if not nxt else int((days - (tier["lo"] if tier else 0)) / max(nxt["lo"] - (tier["lo"] if tier else 0), 1) * 100)
    render(f"""
    <div class="sr-card">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <div><div class="sr-title">🔥 {days} día(s) de racha</div><div class="sr-muted">{esc(title)} · {esc(reward)}</div></div>
        {chip('Doble XP activo', 'coral') if streak_multiplier() > 1 else ''}
      </div>
      {bar(pct)}<div class="sr-muted">{esc(goal)}</div>
    </div>""")
    if st.button("✅ Ya practiqué hoy (+10 XP)" if not done_today else "✔ Racha de hoy registrada", key=f"checkin_{key}",
                 type="primary", use_container_width=True, disabled=done_today):
        do_checkin()
        st.rerun()


# ----------------------------------------------------------------------------
# 9. LOGIN + ONBOARDING
# ----------------------------------------------------------------------------
def view_login() -> None:
    render('<div class="sr-logo" style="text-align:center;font-size:2rem;margin-top:1rem">Safe<span>ROAD</span> 🚗</div>')
    render('<h3 style="text-align:center">Bienvenido a bordo</h3>')
    tab_new, tab_in, tab_demo = st.tabs(["Crear cuenta", "Iniciar sesión", "Perfiles demo"])

    with tab_new:
        with st.form("signup"):
            nombre = st.text_input("Nombre de usuario", placeholder="Ej.: SantiDrive")
            email = st.text_input("Correo electrónico", placeholder="tu@correo.com")
            c1, c2 = st.columns(2)
            pw = c1.text_input("Contraseña (mín. 6)", type="password")
            pw2 = c2.text_input("Repite la contraseña", type="password")
            coche = st.text_input("Modelo de tu coche", placeholder="Ej.: Nissan Versa 2021")
            st.caption("Contacto de emergencia (opcional, puedes agregarlo después en tu perfil)")
            d1, d2 = st.columns(2)
            cnombre = d1.text_input("Nombre del contacto")
            ctel = d2.text_input("Teléfono del contacto", placeholder="+52 477 123 4567")
            ok = st.form_submit_button("Crear mi cuenta", type="primary", use_container_width=True)
        if ok:
            existing = {u["email"].lower() for u in st.session_state.cat["usuarios"]} | {a["email"].lower() for a in accounts()}
            errors = validate_signup(nombre, email, pw, pw2, coche, ctel, existing)
            if errors:
                for e in errors:
                    st.error(e)
            else:
                login(create_account(nombre, email, pw, coche, cnombre, ctel))
                st.rerun()

    with tab_in:
        with st.form("login_form"):
            email_in = st.text_input("Correo electrónico", key="login_email")
            pw_in = st.text_input("Contraseña", type="password", key="login_pw")
            go = st.form_submit_button("Entrar", type="primary", use_container_width=True)
        if go:
            uid = check_login(email_in, pw_in)
            if uid:
                login(uid)
                st.rerun()
            else:
                st.error("Correo o contraseña incorrectos.")

    with tab_demo:
        st.caption("Perfiles de ejemplo de tu archivo Usuarios.csv. Elige uno y confirma.")
        by_id = {u["id"]: u for u in st.session_state.cat["usuarios"]}
        sel = st.radio("Perfil demo", list(by_id), index=None, key="demo_sel", label_visibility="collapsed",
                       format_func=lambda i: f"{by_id[i]['nombre']} · {by_id[i]['coche']}")
        if sel:
            u = by_id[sel]
            render(f"""
            <div class="sr-card" style="display:flex;gap:1rem;align-items:center">
              <div class="sr-avatar" style="width:52px;height:52px;font-size:1.3rem;margin:0;background:{initials_color(u['nombre'])}">{esc(u['nombre'][:1].upper())}</div>
              <div><div class="sr-title">{esc(u['nombre'])}</div><div class="sr-muted">✉️ {esc(u['email'])}</div>
              <div class="sr-muted">🚘 {esc(u['coche'])}</div></div>
            </div>""")
            st.button(f"✅ Confirmar y entrar como {u['nombre']}", key="demo_confirm", type="primary",
                      on_click=login, args=(sel,), use_container_width=True)


def view_onboarding() -> None:
    ss = st.session_state
    render('<div class="sr-logo" style="text-align:center;font-size:1.8rem">Safe<span>ROAD</span> 🚗</div>')
    if ss.onb_step < len(ONBOARDING_STEPS):
        title, body = ONBOARDING_STEPS[ss.onb_step]
        render(f'<div class="sr-card" style="text-align:center;margin-top:1rem"><h3>{title}</h3><p>{body}</p>'
               f'{bar((ss.onb_step + 1) / (len(ONBOARDING_STEPS) + 1) * 100)}'
               f'<span class="sr-muted">Paso {ss.onb_step + 1} de {len(ONBOARDING_STEPS) + 1}</span></div>')
        c1, c2 = st.columns(2)
        if c1.button("Omitir tutorial", use_container_width=True):
            ss.onb_step = len(ONBOARDING_STEPS)
            st.rerun()
        if c2.button("Siguiente →", type="primary", use_container_width=True):
            ss.onb_step += 1
            st.rerun()
        return
    if ss.quiz_result is not None:
        score, lvl = ss.quiz_result
        render(f'<div class="sr-card" style="text-align:center"><h3>🎉 ¡Diagnóstico listo!</h3><p>Acertaste <b>{score} de {len(QUIZ)}</b>.</p>'
               f'<p>Tu nivel inicial: {chip(lvl, "aqua")}</p></div>')
        if st.button("Comenzar mi ruta →", type="primary", use_container_width=True):
            S()["quiz_done"] = True
            save_state()
            ss.quiz_result = None
            st.rerun()
        return
    st.subheader("🧠 Quiz de diagnóstico")
    st.caption("5 preguntas rápidas para conocer tu nivel de seguridad al volante.")
    with st.form("diagnostic_quiz"):
        answers = [st.radio(f"{i + 1}. {q['q']}", q["o"], index=None, key=f"quiz_{ss.user_id}_{i}") for i, q in enumerate(QUIZ)]
        submitted = st.form_submit_button("Ver mi resultado", type="primary", use_container_width=True)
    if submitted:
        if any(a is None for a in answers):
            st.warning("Responde todas las preguntas para continuar.")
            return
        score = sum(1 for a, q in zip(answers, QUIZ) if q["o"].index(a) == q["a"])
        lvl = "Avanzado" if score >= 4 else "Principiante"
        S()["nivel_experiencia"] = lvl
        save_state()
        ss.quiz_result = (score, lvl)
        st.rerun()


# ----------------------------------------------------------------------------
# 10. INICIO
# ----------------------------------------------------------------------------
def view_inicio() -> None:
    u, lvl = cur_user(), level()
    xp_in = S()["xp"] % XP_PER_LEVEL
    render(f"""
    <div class="sr-hero">
      <div class="sr-sub">¡Hola de nuevo!</div><h2>{esc(u['nombre'])}</h2>
      <div style="margin:.4rem 0"><span class="sr-chip white">Nivel {lvl}</span><span class="sr-chip white">{esc(S()['nivel_experiencia'])}</span>
      <span class="sr-chip white">🚘 {esc(u['coche'])}</span></div>
      <div class="sr-bar" style="background:rgba(255,255,255,.3)"><span style="width:{xp_in}%;background:#fff"></span></div>
      <div class="sr-sub">{xp_in}/{XP_PER_LEVEL} XP para el nivel {lvl + 1}</div>
    </div>""")
    streak_card("home")

    recs = recommended(3)
    if recs:
        top = recs[0]
        st.markdown("#### ▶️ Continúa donde te quedaste")
        if top["url"]:
            st.video(top["url"])
        st.markdown(f"**{top['titulo']}** · {top['instructor']}")
        st.button("Ir a la lección", key="home_jump", type="primary", on_click=open_ctx, args=("curso", top["id"]), use_container_width=True)
        if len(recs) > 1:
            st.markdown("#### 📚 Recomendados para ti")
            grid(recs[1:], lambda c: course_card(c, "home"), cols=2)
    else:
        st.success("¡Completaste todos los cursos! 🎉")

    st.markdown("#### ⚡ Acceso rápido")
    q1, q2 = st.columns(2)
    q1.button("📚 Cursos y clases en vivo", key="q_cur", on_click=nav_to, args=("Cursos",), use_container_width=True)
    q2.button("🎯 Misiones y medallas", key="q_mis", on_click=nav_to, args=("Misiones",), use_container_width=True)
    q3, q4 = st.columns(2)
    q3.button("🔧 Mantenimiento", key="q_man", on_click=nav_to, args=("Mantenimiento",), use_container_width=True)
    q4.button("🆘 Contactos de emergencia", key="q_sos", on_click=nav_to, args=("Perfil",), use_container_width=True)
    st.caption("💡 ¿Dudas? Toca el orbe 🤖 de la esquina inferior derecha.")


# ----------------------------------------------------------------------------
# 11. CURSOS (catalog, lesson, live, history)
# ----------------------------------------------------------------------------
def view_lesson(cid: str) -> None:
    c = find_course(cid)
    if not c:
        go_back()
        st.rerun()
    if S()["ultimo_curso"] != cid:
        S()["ultimo_curso"] = cid
        save_state()
    back_button()
    if c["url"]:
        st.video(c["url"])
    else:
        render('<div class="sr-video-ph">▶️<br><b>Video no disponible</b></div>')
    p = cprog(c)
    st.markdown(f"### {c['titulo']}")
    render(f'{chip(c["nivel"], "gray")}{chip(c["tema"], "aqua")}{chip(str(c["minutos"]) + " min", "gray")}'
           f'<div class="sr-muted">👤 {esc(c["instructor"])}</div>{bar(p, AQUA if p >= 100 else CORAL)}'
           f'<div class="sr-muted">{p}% · {cstatus(p)}</div>')
    c1, c2 = st.columns(2)
    if c1.button("▶️ Avanzar 25% (simulado)", use_container_width=True, disabled=p >= 100):
        set_course_progress(c, p + 25)
        st.rerun()
    if c2.button("✅ Marcar como completado", type="primary", use_container_width=True, disabled=p >= 100):
        set_course_progress(c, 100)
        st.rerun()
    st.markdown("##### 📝 Mis apuntes")
    S()["notas"][cid] = st.text_area("Apuntes", value=S()["notas"].get(cid, ""), height=120, label_visibility="collapsed",
                                     placeholder="Escribe lo más importante de esta lección…", key=f"note_{cid}")
    others = [x for x in st.session_state.cat["cursos"] if x["id"] != cid][:4]
    st.markdown("##### Más videos")
    for x in others:
        course_card(x, "more", row=True)


def view_live() -> None:
    options = {f"{s['hora']} · {s['tema']}": s for s in LIVE_SESSIONS}
    sess = options[st.selectbox("Próximas clases", list(options))]
    badge = chip("🔴 EN VIVO", "coral") if sess["en_vivo"] else chip("Programada", "gray")
    render(f"""<div class="sr-video-ph">{'🔴' if sess['en_vivo'] else '🕒'}<br><b>{esc(sess['tema'])}</b><br>
    <span class="sr-sub">{esc(sess['instructor'])} · {esc(sess['hora'])}</span></div><div>{badge}</div>""")
    qkey = f"live_q_{sess['id']}"
    questions = st.session_state.setdefault(qkey, [])
    st.markdown("##### ❓ Preguntas al instructor")
    with st.form(f"ask_{sess['id']}", clear_on_submit=True):
        q = st.text_input("Tu pregunta", placeholder="¿Cómo sé cuándo cambiar las llantas?")
        if st.form_submit_button("Enviar pregunta", type="primary") and q.strip():
            questions.append(q.strip())
            log(f"Pregunta enviada en «{sess['tema']}»")
            save_state()
            st.rerun()
    for item in questions:
        render(f'<div class="sr-card">💬 {esc(item)}<br><span class="sr-muted">Pendiente de respuesta</span></div>')
    nkey = f"live_{sess['id']}"
    st.markdown("##### 📝 Notas de la clase")
    S()["notas"][nkey] = st.text_area("Notas", value=S()["notas"].get(nkey, ""), height=100, label_visibility="collapsed", key=f"note_{nkey}")


def view_cursos() -> None:
    cursos, lvl = st.session_state.cat["cursos"], S()["nivel_experiencia"]
    tab_cat, tab_live, tab_hist = st.tabs(["Catálogo", "En vivo", "Historial"])
    with tab_cat:
        q = st.text_input("Buscar", placeholder="🔍 Buscar cursos, temas o instructores…", label_visibility="collapsed", key="q_cursos").strip().lower()
        flt = pills("Filtro", ["Todos", "Para ti", "En progreso", "Completados", "No iniciados"], "f_cursos", "Todos")
        items = []
        for c in cursos:
            p = cprog(c)
            ok = {"Todos": True, "Para ti": p < 100 and c["nivel"] in (lvl, "Todos"), "En progreso": 0 < p < 100,
                  "Completados": p >= 100, "No iniciados": p == 0}[flt]
            if ok and (not q or q in f"{c['titulo']} {c['instructor']} {c['tema']}".lower()):
                items.append(c)
        if not items:
            st.info("No hay cursos con ese filtro.")
        grid(items, lambda c: course_card(c, "cat"), cols=2)
    with tab_live:
        view_live()
    with tab_hist:
        done = [c for c in cursos if cprog(c) >= 100]
        st.markdown("##### ✅ Cursos completados")
        if not done:
            st.info("Aún no completas cursos.")
        grid(done, lambda c: course_card(c, "done"), cols=2)
        st.markdown("##### 🕘 Registro de actividad")
        if not S()["historial"]:
            st.caption("Tu actividad aparecerá aquí.")
        for item in S()["historial"][:15]:
            st.markdown(f"- `{item['ts']}` {item['texto']}")


# ----------------------------------------------------------------------------
# 12. MANTENIMIENTO (catalog, part page, cart)
# ----------------------------------------------------------------------------
def view_part(key: str) -> None:
    parts = st.session_state.cat["partes"]
    p = next((x for x in parts if x["key"] == key), None)
    if not p:
        go_back()
        st.rerun()
    if key not in S()["partes_vistas"]:
        S()["partes_vistas"].append(key)
        bump_mission(PARTS_MISSION, 10)
        log(f"Revisaste «{p['nombre']}»")
        save_state()
    back_button()
    render(f'<div class="vc-thumb" style="border-radius:18px">{part_thumb(p)}<span class="vc-dur">⏱ {p["min"]} min</span></div>')
    st.markdown(f"### {p['nombre']}")
    render(f'{chip(p["cat"], "coral")}{chip("Dificultad: " + p["dif"], "gray")}'
           f'<div class="sr-card" style="margin-top:.4rem"><div><b>📍 Ubicación:</b> {esc(p["ubic"])}</div></div>')
    st.markdown("##### 🧰 Herramientas necesarias")
    render("".join(chip(h, "aqua") for h in p["herramientas"]))
    st.warning(f"⚠️ {p['advertencia']}")

    course = find_course(MAINT_COURSE)
    if course and course["url"]:
        with st.expander(f"▶️ Video relacionado: {course['titulo']}"):
            st.video(course["url"])

    st.markdown("##### 🛒 Tienda virtual")
    if not p["precio"]:
        st.info("Esta sección es una guía de diagnóstico, no se vende. Si un testigo rojo se enciende, detente de inmediato.")
    else:
        render(f'<div style="font-size:1.5rem;font-weight:800;color:#FF6349">{money(p["precio"])}</div>'
               f'<div class="sr-muted">Precio de demostración</div>')
        if key in st.session_state.cart:
            st.success("✔ Ya está en tu carrito")
            st.button("Ir al carrito", key="to_cart", on_click=open_ctx, args=("carrito",), type="primary")
        elif st.button("🛒 Agregar al carrito", type="primary", use_container_width=True):
            st.session_state.cart.append(key)
            st.rerun()

    related = [x for x in parts if x["cat"] == p["cat"] and x["key"] != key] or [x for x in parts if x["key"] != key]
    st.markdown("##### Más del catálogo")
    for x in related[:3]:
        part_card(x, "rel", row=True)


def view_cart() -> None:
    ss, parts = st.session_state, st.session_state.cat["partes"]
    back_button()
    st.markdown("### 🛒 Tu carrito")
    if ss.order_done:
        st.success(ss.order_done)
        ss.order_done = ""
    items = [p for p in parts if p["key"] in ss.cart]
    if not items:
        st.info("Tu carrito está vacío. Explora el catálogo en Mantenimiento.")
        return
    subtotal = sum(p["precio"] for p in items)
    for p in items:
        c1, c2 = st.columns([4, 1])
        c1.markdown(f"{p['emoji']} **{p['nombre']}**  \n{money(p['precio'])}")
        if c2.button("🗑️", key=f"rm_{p['key']}"):
            ss.cart.remove(p["key"])
            st.rerun()
    st.markdown("##### 🎟️ Cupón de descuento")
    coupon = current_coupon()
    code = st.text_input("Código", value=ss.cart_coupon, placeholder="Ej.: RACHA3", label_visibility="collapsed", key="coupon_in").strip().upper()
    ss.cart_coupon = code
    pct = coupon[1] if coupon and code == coupon[0] else 0
    if code and not pct:
        st.caption("Cupón no válido, usado o aún no disponible. Revisa Perfil → Racha.")
    discount = subtotal * pct // 100
    render(f'<div class="sr-card"><div>Subtotal: <b>{money(subtotal)}</b></div>'
           f'{f"<div>Descuento ({pct}%): <b>-{money(discount)}</b></div>" if pct else ""}'
           f'<div style="font-size:1.2rem;margin-top:.3rem">Total: <b style="color:#FF6349">{money(subtotal - discount)}</b></div>'
           f'<div class="sr-muted">Modo simulación: no se usa dinero real.</div></div>')
    if st.button("✅ Completar transacción de prueba", type="primary", use_container_width=True):
        if pct:
            S()["cupones_usados"].append(coupon[0])
        log(f"Compra simulada de {len(items)} artículo(s): {money(subtotal - discount)}")
        add_xp(10 * len(items))
        ss.order_done = f"¡Compra simulada completada! Total {money(subtotal - discount)}."
        ss.cart, ss.cart_coupon = [], ""
        save_state()
        st.rerun()


def view_mantenimiento() -> None:
    parts, lvl = st.session_state.cat["partes"], level()
    c1, c2 = st.columns([3, 1])
    c1.markdown("### 🔧 Mantenimiento")
    c2.button(f"🛒 {len(st.session_state.cart)}", key="open_cart", on_click=open_ctx, args=("carrito",), use_container_width=True)
    tab_cat, tab_guides = st.tabs(["Catálogo de refacciones", "Guías rápidas"])
    with tab_cat:
        if lvl < PARTS_UNLOCK_LEVEL:
            pct = min(100, int(S()["xp"] / (PARTS_UNLOCK_LEVEL * XP_PER_LEVEL) * 100))
            render(f'<div class="sr-card sr-locked"><div style="font-size:2.4rem">🔒</div><h4>Catálogo bloqueado</h4>'
                   f'<p>Se desbloquea en el <b>nivel {PARTS_UNLOCK_LEVEL}</b>. Ahora estás en el nivel {lvl}.</p>{bar(pct)}</div>')
            if st.button("🔓 Desbloquear para demostración", use_container_width=True):
                S()["xp"] = max(S()["xp"], (PARTS_UNLOCK_LEVEL - 1) * XP_PER_LEVEL)
                save_state()
                st.rerun()
            return
        q = st.text_input("Buscar", placeholder="🔍 Buscar refacciones…", label_visibility="collapsed", key="q_partes").strip().lower()
        cats = ["Todas"] + sorted({p["cat"] for p in parts})
        flt = pills("Categoría", cats, "f_partes", "Todas")
        items = [p for p in parts if (flt == "Todas" or p["cat"] == flt) and (not q or q in f"{p['nombre']} {p['cat']}".lower())]
        if not items:
            st.info("Sin resultados.")
        grid(items, lambda p: part_card(p, "cat"), cols=2)
    with tab_guides:
        for title, steps in GUIDES.items():
            with st.expander(title):
                for i, step in enumerate(steps, 1):
                    st.markdown(f"{i}. {step}")
        course = find_course(MAINT_COURSE)
        if course:
            st.button(f"▶️ Ver curso: {course['titulo']}", key="guide_course", on_click=open_ctx, args=("curso", course["id"]), use_container_width=True)


# ----------------------------------------------------------------------------
# 13. MISIONES
# ----------------------------------------------------------------------------
def view_misiones() -> None:
    cat = st.session_state.cat
    st.markdown("#### 🔥 Racha diaria")
    streak_card("mis")
    with st.expander("Ver todas las recompensas por racha"):
        for t in cat["rachas"]:
            hi = f"{t['lo']}+" if t["hi"] > 10 ** 5 else f"{t['lo']}–{t['hi']}"
            st.markdown(f"**Días {hi} · {t['nivel']}** — {t['recompensa']}  \n<span style='color:#64748B;font-size:.8rem'>{t['estado']}</span>",
                        unsafe_allow_html=True)

    st.markdown("#### 🏅 Mis medallas")
    st.caption("A color = desbloqueada · en gris = por conseguir.")

    def tile(m):
        emoji, color = TIERS[mission_tier(m)]
        done = mission_done(m)
        render(f'<div class="sr-tile {"" if done else "locked"}" style="border-color:{color}"><div class="icon">{emoji}</div>'
               f'<div class="sr-title" style="font-size:.8rem">{esc(m["medalla_nombre"])}</div><div class="sr-muted">{mission_tier(m)}</div></div>')

    grid(cat["misiones"], tile, cols=3)

    st.markdown("#### 🎯 Misiones")
    for m in cat["misiones"]:
        p, locked, tier = mission_progress(m), mission_locked(m), mission_tier(m)
        emoji, color = TIERS["Bloqueada"] if locked else TIERS[tier]
        prev = cat["misiones"][mission_index(m) - 1]["nombre"] if locked else ""
        sub = f"🔒 Se desbloquea al completar «{prev}»" if locked else f"{tier} · +{MISSION_XP[tier]} XP"
        render(f'<div class="sr-card"><div class="sr-title">{emoji} {esc(m["nombre"])}</div><div class="sr-muted">{esc(sub)}</div>'
               f'{bar(0 if locked else p, AQUA if p >= 100 else CORAL)}<div class="sr-muted">{0 if locked else p}%</div></div>')
        if not locked and mission_done(m):
            if m["id"] in S()["mision_reclamada"]:
                st.caption("✅ XP reclamado")
            elif st.button(f"🎁 Reclamar +{MISSION_XP[tier]} XP", key=f"claim_{m['id']}", type="primary"):
                S()["mision_reclamada"].append(m["id"])
                log(f"Reclamaste «{m['nombre']}» (+{MISSION_XP[tier]} XP)")
                add_xp(MISSION_XP[tier])
                st.rerun()
        with st.expander(f"Detalles de {m['nombre']}"):
            st.markdown(f"**Medalla:** {m['medalla_nombre']} ({tier})")
            if locked:
                st.info("Misión bloqueada.")
            elif mission_done(m):
                st.success(f"Desbloqueada el {S()['mision_fecha'].get(m['id'], 'fecha no registrada')}")
            else:
                hint = {PARKING_LINK[0]: "Avanza en el curso de estacionamiento.", PARTS_MISSION: "Revisa refacciones en Mantenimiento."}.get(m["id"], "")
                if hint:
                    st.caption(hint)
                if st.button("Simular avance +20% (demo)", key=f"demo_{m['id']}"):
                    bump_mission(m["id"], 20)
                    st.rerun()


# ----------------------------------------------------------------------------
# 14. PERFIL
# ----------------------------------------------------------------------------
def _wheel(cx: int, r: int, sport: bool = False, chunky: bool = False) -> str:
    cy = 132 - r
    tread = f'<circle cx="{cx}" cy="{cy}" r="{r - 3}" fill="none" stroke="#374151" stroke-width="3" stroke-dasharray="4 3"/>' if chunky else ""
    spokes = "".join(f'<line x1="{cx}" y1="{cy}" x2="{cx + r * 0.62 * math.cos(i * 2 * math.pi / 5):.1f}" '
                     f'y2="{cy + r * 0.62 * math.sin(i * 2 * math.pi / 5):.1f}" stroke="#64748B" stroke-width="2"/>' for i in range(5)) if sport else ""
    return (f'<circle cx="{cx}" cy="{cy}" r="{r + 6}" fill="#0F172A" opacity=".28"/><circle cx="{cx}" cy="{cy}" r="{r}" fill="#111827"/>{tread}'
            f'<circle cx="{cx}" cy="{cy}" r="{int(r * 0.55)}" fill="#CBD5E1"/>{spokes}<circle cx="{cx}" cy="{cy}" r="{int(r * 0.18) + 1}" fill="#64748B"/>')


def car_svg(kind: str, color: str) -> str:
    edge = 'stroke="#0F172A" stroke-opacity=".25" stroke-width="2"'
    glass = "#E6F9FF"
    head = lambda x, y: f'<rect x="{x}" y="{y}" width="10" height="8" rx="3" fill="#FFE066"/>'
    tail = lambda x, y: f'<rect x="{x}" y="{y}" width="8" height="9" rx="3" fill="#FF3B30"/>'
    if kind == "SUV":
        body = (f'<path d="M30 110 L30 84 Q30 76 40 74 L84 68 L96 42 Q100 36 110 36 L232 36 Q242 36 246 44 L262 72 L282 78 Q292 82 292 92 L292 110 Z" fill="{color}" {edge}/>'
                f'<path d="M104 46 L132 46 L132 70 L96 70 Z M140 46 L232 46 L248 70 L140 70 Z" fill="{glass}"/>'
                f'<line x1="112" y1="31" x2="228" y2="31" stroke="#1E293B" stroke-width="4"/>{head(282, 88)}{tail(30, 88)}{_wheel(84, 22)}{_wheel(240, 22)}')
    elif kind == "Pickup":
        body = (f'<path d="M28 110 L28 72 L130 72 L138 46 Q142 40 150 40 L206 40 Q216 40 222 48 L238 70 L278 74 Q292 76 292 90 L292 110 Z" fill="{color}" {edge}/>'
                f'<rect x="34" y="67" width="92" height="6" rx="2" fill="#000" opacity=".3"/><path d="M146 48 L204 48 L224 70 L146 70 Z" fill="{glass}"/>'
                f'<rect x="284" y="84" width="8" height="14" fill="#CBD5E1"/>{head(282, 76)}{tail(28, 80)}{_wheel(82, 24)}{_wheel(240, 24)}')
    elif kind == "4x4":
        body = (f'<rect x="70" y="30" width="140" height="5" rx="2" fill="#1E293B"/>'
                f'<path d="M34 104 L34 64 L48 60 L60 38 L222 38 L236 60 L284 64 L290 72 L290 104 Z" fill="{color}" {edge}/>'
                f'<path d="M70 46 L128 46 L128 62 L62 62 Z M136 46 L214 46 L226 62 L136 62 Z" fill="{glass}"/>'
                f'<circle cx="26" cy="78" r="15" fill="#111827"/><circle cx="26" cy="78" r="7" fill="#94A3B8"/>'
                f'<circle cx="284" cy="80" r="5" fill="#FFE066"/>{_wheel(84, 28, chunky=True)}{_wheel(240, 28, chunky=True)}'
                '<path d="M50 104 A34 34 0 0 1 118 104 M206 104 A34 34 0 0 1 274 104" fill="none" stroke="#1E293B" stroke-width="5"/>')
    elif kind == "Deportivo":
        body = (f'<path d="M22 112 L22 102 Q22 94 38 92 L108 80 Q150 52 192 56 Q224 60 246 78 L288 88 Q302 92 302 104 L302 112 Z" fill="{color}" {edge}/>'
                f'<path d="M130 78 Q154 60 188 64 Q210 66 224 78 Z" fill="{glass}"/><path d="M20 92 L20 78 L62 78 L62 82 L30 86 Z" fill="#1E293B"/>'
                f'<path d="M150 94 L190 94 L180 102 L152 102 Z" fill="#0F172A" opacity=".55"/>'
                f'<path d="M276 90 L298 94 L298 98 L272 94 Z" fill="#FFE066"/><rect x="22" y="96" width="8" height="4" fill="#FF3B30"/>'
                f'{_wheel(82, 18, sport=True)}{_wheel(244, 18, sport=True)}')
    else:  # Urbana / Aventura
        adv = kind == "Aventura"
        rack = '<rect x="112" y="36" width="100" height="5" rx="2" fill="#1E293B"/>' if adv else ""
        r = 24 if adv else 20
        body = (f'{rack}<path d="M32 110 Q30 86 58 82 L98 52 Q106 44 120 44 L204 44 Q218 44 228 54 L256 82 Q290 86 290 110 Z" fill="{color}" {edge}/>'
                f'<path d="M108 56 L126 56 L126 80 L94 80 Z M136 56 L202 56 L224 80 L136 80 Z" fill="{glass}"/>'
                f'{head(280, 90)}{tail(30, 90)}{_wheel(84, r)}{_wheel(240, r)}')
    return H(f"""<svg viewBox="0 0 320 150" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:440px;display:block;margin:auto">
      <ellipse cx="160" cy="136" rx="140" ry="8" fill="#1E293B" opacity=".12"/>{body}</svg>""")


def all_contacts() -> list:
    u = cur_user()
    out = [{"nombre": u["contacto_nombre"], "tel": u["contacto_tel"], "idx": None}] if u["contacto_tel"] else []
    return out + [{**c, "idx": i} for i, c in enumerate(S()["contactos"])]


def view_perfil() -> None:
    u, lvl, cat = cur_user(), level(), st.session_state.cat
    render(f"""
    <div class="sr-card" style="display:flex;gap:1rem;align-items:center">
      <div class="sr-avatar" style="width:64px;height:64px;font-size:1.6rem;margin:0;background:{initials_color(u['nombre'])}">{esc(u['nombre'][:1].upper())}</div>
      <div><div class="sr-title" style="font-size:1.15rem">{esc(u['nombre'])}</div><div class="sr-muted">✉️ {esc(u['email'])}</div>
      <div class="sr-muted">🪪 ID: {esc(u['id'])} · 🚘 {esc(u['coche'])}</div></div>
    </div>""")
    done = sum(1 for c in cat["cursos"] if cprog(c) >= 100)
    medals = sum(1 for m in cat["misiones"] if mission_done(m))
    render(f"""
    <div class="sr-card"><div class="sr-title">📈 Mi progreso</div>
      <div class="sr-muted">Nivel {lvl} · {S()['xp'] % XP_PER_LEVEL}/{XP_PER_LEVEL} XP al siguiente</div>{bar(S()['xp'] % XP_PER_LEVEL)}
      <div class="sr-muted">Cursos completados: {done}/{len(cat['cursos'])}</div>{bar(done / max(len(cat['cursos']), 1) * 100, AQUA)}
      <div class="sr-muted">Medallas: {medals}/{len(cat['misiones'])}</div>{bar(medals / max(len(cat['misiones']), 1) * 100, AQUA)}
      <div class="sr-muted">Catálogo de refacciones (nivel {PARTS_UNLOCK_LEVEL}): {min(lvl, PARTS_UNLOCK_LEVEL)}/{PARTS_UNLOCK_LEVEL}</div>
      {bar(min(lvl, PARTS_UNLOCK_LEVEL) / PARTS_UNLOCK_LEVEL * 100)}
    </div>""")

    tab_car, tab_sos, tab_med, tab_streak, tab_fam = st.tabs(["Mi coche", "Emergencia", "Medallas", "Racha", "Familia"])

    with tab_car:
        types = list(VEHICLE_TYPES)
        kind = st.selectbox("Tipo de vehículo", types, format_func=lambda k: VEHICLE_TYPES[k],
                            index=types.index(S()["vehiculo_tipo"]) if S()["vehiculo_tipo"] in types else 0)
        color = st.color_picker("Color principal", S()["vehiculo_color"])
        st.markdown(f"<div class='sr-muted' style='text-align:center'>{esc(u['coche'])}</div>", unsafe_allow_html=True)
        st.markdown(car_svg(kind, color), unsafe_allow_html=True)
        if st.button("💾 Guardar vehículo", type="primary", use_container_width=True):
            S()["vehiculo_tipo"], S()["vehiculo_color"] = kind, color
            save_state()
            st.success("Vehículo guardado")

    with tab_sos:
        contacts = all_contacts()
        st.caption(f"Contactos guardados: {len(contacts)}/{MAX_CONTACTS}")
        if st.button("🆘 SOS: avisar a todos (simulado)", type="primary", use_container_width=True, disabled=not contacts):
            st.toast("Alerta enviada a tus contactos de emergencia (simulación).", icon="🆘")
        for i, c in enumerate(contacts):
            c1, c2, c3, c4 = st.columns([3, 1.4, 1.1, 1])
            c1.markdown(f"**{esc(c['nombre'] or 'Sin nombre')}**{' · principal' if c['idx'] is None else ''}  \n{esc(c['tel'])}")
            if c2.button("📞 Llamar", key=f"call_{i}", use_container_width=True):
                st.toast(f"Llamando a {c['nombre'] or c['tel']}… (simulado)", icon="📞")
            c3.link_button("📱", f"tel:{phone_digits(c['tel'])}", use_container_width=True, help="Abre el marcador del teléfono")
            if c['idx'] is not None and c4.button("🗑️", key=f"del_{i}", use_container_width=True):
                S()["contactos"].pop(c["idx"])
                save_state()
                st.rerun()
        if len(contacts) < MAX_CONTACTS:
            with st.form("add_contact", clear_on_submit=True):
                name = st.text_input("Nombre del contacto")
                phone = st.text_input("Teléfono", placeholder="+52 477 123 4567")
                if st.form_submit_button("➕ Agregar contacto", use_container_width=True):
                    if not name.strip() or not PHONE_RE.match(phone.strip()):
                        st.error("Escribe un nombre y un teléfono válido.")
                    else:
                        S()["contactos"].append({"nombre": name.strip(), "tel": phone.strip()})
                        save_state()
                        st.rerun()
        else:
            st.info("Llegaste al máximo de 5 contactos.")
        st.caption("💡 ¿Dudas? Toca el orbe 🤖 de la esquina para ver la guía «Agregar número de SOS».")

    with tab_med:
        got = [m for m in cat["misiones"] if mission_done(m)]
        if not got:
            st.info("Aún no tienes medallas. ¡Completa misiones!")

        def tile(m):
            emoji, color = TIERS[mission_tier(m)]
            render(f'<div class="sr-tile" style="border-color:{color}"><div class="icon">{emoji}</div>'
                   f'<div class="sr-title" style="font-size:.8rem">{esc(m["medalla_nombre"])}</div><div class="sr-muted">{mission_tier(m)}</div></div>')

        grid(got, tile, cols=3)

    with tab_streak:
        streak_card("perfil")
        coupon = current_coupon()
        st.markdown("##### 🎟️ Mis cupones")
        if coupon:
            render(f'<div class="sr-card"><div class="sr-title">Cupón de mantenimiento: {coupon[1]}%</div>'
                   f'<div>Código: <b style="color:#FF6349">{coupon[0]}</b></div><div class="sr-muted">Úsalo en el carrito de la tienda (un solo uso).</div></div>')
        else:
            st.info("Llega a 10 días de racha para ganar tu primer cupón de descuento.")

    with tab_fam:
        contacts = all_contacts()
        st.caption("Ubicación simulada de tus contactos (demostración).")
        if not contacts:
            st.info("Agrega contactos en la pestaña Emergencia.")
        else:
            rng = random.Random(st.session_state.family_seed)
            pts = pd.DataFrame([{"lat": 19.4326 + rng.uniform(-0.03, 0.03), "lon": -99.1332 + rng.uniform(-0.03, 0.03)} for _ in contacts])
            st.map(pts, size=80, color=CORAL)
            for c, (_, r) in zip(contacts, pts.iterrows()):
                st.markdown(f"📍 **{c['nombre'] or 'Contacto'}** · {r['lat']:.4f}, {r['lon']:.4f}")
            if st.button("🔄 Actualizar ubicaciones", use_container_width=True):
                st.session_state.family_seed += 1
                st.rerun()

    st.button("🚪 Cerrar sesión", key="logout", on_click=logout, use_container_width=True)
    with st.expander("🛠️ Herramientas de demo"):
        d1, d2 = st.columns(2)
        if d1.button("➕ Sumar 500 XP", use_container_width=True):
            add_xp(500)
            st.rerun()
        if d2.button("📅 Simular siguiente día", use_container_width=True):
            S()["racha"]["ultimo"] = (date.today() - timedelta(days=1)).isoformat()
            if S()["racha"]["dias"] == 0:
                S()["racha"]["dias"] = 1
            save_state()
            st.rerun()
        days = st.number_input("Fijar racha en (días)", 0, 80, S()["racha"]["dias"])
        if st.button("Aplicar racha", use_container_width=True):
            S()["racha"] = {"dias": int(days), "ultimo": (date.today() - timedelta(days=1)).isoformat()}
            save_state()
            st.rerun()
        if st.button("↺ Repetir diagnóstico inicial", use_container_width=True):
            S()["quiz_done"] = False
            save_state()
            st.session_state.onb_step, st.session_state.quiz_result = 0, None
            st.rerun()
        if st.button("🧹 Reiniciar todo mi progreso", use_container_width=True):
            st.session_state.state = new_state(cat, fresh=not is_demo_user(st.session_state.user_id))
            save_state()
            st.session_state.onb_step, st.session_state.quiz_result, st.session_state.cart = 0, None, []
            st.rerun()


# ----------------------------------------------------------------------------
# 15. ASISTENTE (step-by-step guides from Asistente_IA_Guias.csv)
# ----------------------------------------------------------------------------
def step_to(n: int) -> None:
    st.session_state.guide_step = n


def _plain(t: str) -> str:
    return unicodedata.normalize("NFD", t.lower()).encode("ascii", "ignore").decode()


_STOP = {"motor", "curso", "cursos", "parte", "partes", "video", "videos", "clase", "clases", "nivel", "niveles"}


def _stems(*texts) -> set:
    words = {w for t in texts for w in re.findall(r"[a-z0-9]+", _plain(t)) if len(w) >= 5 and w not in _STOP}
    return {w if len(w) < 6 else w[:6] for w in words}


def _best(t: str, items: list, texts):
    best, score = None, 0
    for it in items:
        sc = sum(1 for w in _stems(*texts(it)) if w in t)
        if sc > score:
            best, score = it, sc
    return best


def _numbered(lines: list) -> str:
    return "\n".join(f"{i}. {x}" for i, x in enumerate(lines, 1))


def local_answer(q: str):
    """Rule-based answers built from the app's own data. Returns (text, actions)."""
    ss, cat = st.session_state, st.session_state.cat
    t = _plain(q)
    has = lambda *w: any(x in t for x in w)
    lvl, xp = level(), S()["xp"]
    part = _best(t, cat["partes"], lambda p: (p["nombre"],))
    course = _best(t, cat["cursos"], lambda c: (c["titulo"], c["tema"]))
    coupon = current_coupon()

    if has("compr", "tienda", "carrito", "pagar", "ordenar", "pedir", "cupon", "descuento"):
        steps = [x[0][:-1] if x[0].endswith(".") else x[0] for x in cat["guias"].get("GUA_02", {}).get("pasos", [])]
        text = "Así compras en la tienda virtual (modo simulación, sin dinero real):\n" + (_numbered(steps) or "Entra a Mantenimiento → Catálogo.")
        text += ("\n\n✅ Ya tienes el catálogo desbloqueado." if lvl >= PARTS_UNLOCK_LEVEL else
                 f"\n\n🔒 El catálogo se abre en el nivel {PARTS_UNLOCK_LEVEL}. Vas en el nivel {lvl}: te faltan "
                 f"{max(0, (PARTS_UNLOCK_LEVEL - 1) * XP_PER_LEVEL - xp)} XP. En Mantenimiento hay un botón de demostración para abrirlo ya.")
        if part and part["precio"]:
            text += f"\n\n«{part['nombre']}» cuesta {money(part['precio'])} (precio de demostración)."
        if coupon:
            text += f"\n\n🎟️ Tienes un cupón: **{coupon[0]}** ({coupon[1]}% de descuento)."
        acts = [("🔧 Ir a Mantenimiento", "page", "Mantenimiento"), ("🛒 Ver mi carrito", "cart", None)]
        if part:
            acts.insert(0, (f"Ver «{part['nombre']}»", "parte", part["key"]))
        return text, acts

    if has("recomiend", "recomend", "que curso", "cual curso", "empezar", "por donde", "aprender", "siguiente curso", "que veo"):
        recs = recommended(3)
        if not recs:
            return "¡Ya completaste todos los cursos! 🎉", []
        lines = []
        for c in recs:
            p = cprog(c)
            why = f"retómalo, vas en {p}%" if p > 0 else f"va con tu nivel ({c['nivel']})"
            lines.append(f"**{c['titulo']}** — {c['instructor']} · {c['minutos']} min · {why}")
        return (f"Por tu nivel ({S()['nivel_experiencia']}) y tu avance, te recomiendo:\n" + _numbered(lines),
                [(f"▶ {c['titulo']}", "curso", c["id"]) for c in recs])

    if part and not (course and not has("refaccion", "pieza", "herramienta", "precio", "cuesta")):
        pr = money(part["precio"]) if part["precio"] else "es una guía de diagnóstico (no se vende)"
        return (f"**{part['nombre']}** ({part['cat']}, dificultad {part['dif']}, ~{part['min']} min).\n📍 {part['ubic']}\n"
                f"🧰 Herramientas: {', '.join(part['herramientas'])}.\n⚠️ {part['advertencia']}\n💲 {pr}",
                [(f"Ver «{part['nombre']}»", "parte", part["key"])])

    if course:
        p = cprog(course)
        return (f"**{course['titulo']}** — {course['instructor']}.\nTema: {course['tema']} · {course['minutos']} min · nivel {course['nivel']}.\n"
                f"Tu progreso: {p}% ({cstatus(p)}).", [(f"▶ Abrir «{course['titulo']}»", "curso", course["id"])])

    if has("testigo", "tablero", "luz roja", "check engine", "se prendio", "se enciende"):
        tp = next((x for x in cat["partes"] if x["key"] == "Testigos"), None)
        if tp:
            return (f"{tp['advertencia']}\n🧰 Para diagnosticar: {', '.join(tp['herramientas'])}.\nSi la luz es roja, detente en un lugar seguro y llama a un mecánico.",
                    [("Ver testigos del tablero", "parte", "Testigos")])

    if has("sos", "emergencia", "contacto"):
        steps = [x[0][:-1] if x[0].endswith(".") else x[0] for x in cat["guias"].get("GUA_01", {}).get("pasos", [])]
        return ("Así agregas un contacto de emergencia:\n" + (_numbered(steps) or "Perfil → Emergencia → Agregar contacto.")
                + f"\n\nTienes {len(all_contacts())} de {MAX_CONTACTS} contactos.", [("👤 Ir a mi Perfil", "page", "Perfil")])

    if has("nivel", "xp", "puntos", "progreso", "cuanto llevo"):
        done = sum(1 for c in cat["cursos"] if cprog(c) >= 100)
        meds = sum(1 for m in cat["misiones"] if mission_done(m))
        return (f"Vas en el **nivel {lvl}** con {xp} XP ({S()['nivel_experiencia']}).\nCursos completados: {done}/{len(cat['cursos'])} · "
                f"Medallas: {meds}/{len(cat['misiones'])} · Racha: {effective_days()} día(s).", [("👤 Ver mi perfil", "page", "Perfil")])

    if has("racha", "streak"):
        tier = tier_for(effective_days())
        return (f"Tu racha es de **{effective_days()} día(s)**" + (f" ({tier['nivel']}: {tier['recompensa']})." if tier else ".")
                + "\nRegistra tu práctica diaria en Inicio para mantenerla."
                + (f"\n🎟️ Cupón disponible: {coupon[0]}." if coupon else ""), [("🏠 Ir a Inicio", "page", "Inicio")])

    if has("mision", "medalla", "insignia"):
        lines = [f"{m['nombre']}: {'🔒' if mission_locked(m) else str(mission_progress(m)) + '%'}" for m in cat["misiones"]]
        return "Tus misiones:\n" + _numbered(lines), [("🎯 Ir a Misiones", "page", "Misiones")]

    if has("coche", "vehiculo", "color", "personaliz", "camioneta", "pickup", "deportivo", "4x4"):
        return ("En **Perfil → Mi coche** eliges el tipo: " + ", ".join(v.split(" ", 1)[1] for v in VEHICLE_TYPES.values())
                + " y el color. Pulsa «Guardar vehículo» al terminar.", [("👤 Ir a mi Perfil", "page", "Perfil")])

    if has("hola", "buenas", "hey", "gracias"):
        return "¡Hola! 👋 Pregúntame cómo comprar, qué curso te conviene, sobre refacciones, testigos del tablero, tu progreso o tus contactos SOS.", []

    extra = "" if claude_ready() else "\n\n💡 Para responder cualquier tema, activa la IA con tu clave de Anthropic (mira las instrucciones del archivo)."
    return ("No estoy seguro de eso. Puedo ayudarte con: compras y cupones, cursos recomendados, refacciones, testigos del tablero, "
            "contactos SOS, tu nivel y tu racha." + extra), []


def claude_ready() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def app_context() -> str:
    cat, lvl = st.session_state.cat, level()
    lines = [f"Usuario: {cur_user()['nombre']}, coche {cur_user()['coche']}. Nivel {lvl} ({S()['xp']} XP), experiencia {S()['nivel_experiencia']}. "
             f"Racha: {effective_days()} días. Cupón: {current_coupon() or 'ninguno'}.",
             f"El catálogo de refacciones se desbloquea en el nivel {PARTS_UNLOCK_LEVEL} (hay un botón de demostración en Mantenimiento). Precios y stock son de demostración.",
             "CURSOS:"]
    lines += [f"- {c['id']} {c['titulo']} ({c['instructor']}, {c['minutos']} min, tema {c['tema']}, nivel {c['nivel']}, avance {cprog(c)}%)" for c in cat["cursos"]]
    lines.append("RECOMENDADOS AHORA: " + ", ".join(c["titulo"] for c in recommended(3)))
    lines.append("REFACCIONES:")
    lines += [f"- {p['nombre']} ({p['cat']}, dificultad {p['dif']}, {money(p['precio']) if p['precio'] else 'no se vende'}, herramientas: {', '.join(p['herramientas'])}; aviso: {p['advertencia']})" for p in cat["partes"]]
    lines.append("MISIONES: " + "; ".join(f"{m['nombre']} {mission_progress(m)}%" for m in cat["misiones"]))
    for gid, g in cat["guias"].items():
        lines.append(f"GUÍA {g['modulo']}: " + " | ".join(f"{a} -> {b}" for a, b in g["pasos"]))
    lines.append("NAVEGACIÓN: Inicio, Cursos (catálogo, en vivo, historial), Mantenimiento (catálogo y guías, carrito), Misiones (racha y medallas), Perfil (coche, emergencia, medallas, racha, familia).")
    return "\n".join(lines)


def claude_answer(q: str):
    """Free-form answer with Claude (needs `pip install anthropic` and ANTHROPIC_API_KEY). Returns None on any problem."""
    try:
        import anthropic
        msgs = []
        for ex in st.session_state.chat[-4:]:
            msgs += [{"role": "user", "content": ex["q"]}, {"role": "assistant", "content": ex["a"]}]
        msgs.append({"role": "user", "content": q})
        system = ("Eres el asistente de Safe ROAD, una app educativa para conductores principiantes. Responde en español, breve y claro "
                  "(máximo 6 frases o una lista corta). Sobre la app usa SOLO el contexto; si algo no está ahí, dilo. Sobre conducción o "
                  "mecánica da consejos generales de seguridad; si hay riesgo (testigo rojo, frenos, accidente) recomienda detenerse con seguridad "
                  "y llamar a un profesional o a emergencias. No inventes precios ni stock.\n\nCONTEXTO DE LA APP:\n" + app_context())
        r = anthropic.Anthropic().messages.create(model=ASSISTANT_MODEL, max_tokens=600, system=system, messages=msgs)
        return "".join(b.text for b in r.content if getattr(b, "type", "") == "text").strip() or None
    except Exception:
        return None


def ask(q: str) -> None:
    """Answer a question and store it in the chat history."""
    q = q.strip()
    if not q:
        return
    text, actions = local_answer(q)
    if claude_ready():
        ai = claude_answer(q)
        if ai:
            text = ai
    st.session_state.chat.append({"q": q, "a": text, "actions": actions})
    del st.session_state.chat[:-30]


def send_question() -> None:
    ask(st.session_state.get("orb_q", ""))


def run_action(kind: str, arg) -> None:
    {"page": nav_to, "curso": lambda a: open_ctx("curso", a), "parte": goto_part, "cart": lambda a: open_ctx("carrito")}[kind](arg)


def bubble(text: str, css: str) -> str:
    t = esc(text)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?m)^- ", "• ", t).replace("\n", "<br>")
    return f'<div class="{css}">{t}</div>'


def assistant_panel() -> None:
    ss, guides = st.session_state, st.session_state.cat["guias"]
    st.markdown("**🤖 Asistente Safe ROAD**")
    st.caption("✨ IA conectada (Claude)" if claude_ready() else "📘 Modo guía de la app")
    for i, qq in enumerate(QUICK_QUESTIONS):
        st.button(qq, key=f"orb_chip_{i}", on_click=ask, args=(qq,), use_container_width=True)
    with st.form("orb_form", clear_on_submit=True):
        st.text_input("Pregunta", key="orb_q", placeholder="Escribe tu pregunta y pulsa Enter…", label_visibility="collapsed")
        st.form_submit_button("Enviar", type="primary", on_click=send_question, use_container_width=True)

    with st.container(height=330):
        if not ss.chat:
            render(bubble("¡Hola! Pregúntame cómo comprar, qué curso te conviene, sobre refacciones, testigos, tu progreso o tus contactos SOS.", "cb-bot"))
        for idx, ex in enumerate(reversed(ss.chat)):
            render(bubble(ex["q"], "cb-user") + bubble(ex["a"], "cb-bot"))
            if idx == 0:
                for j, (label, kind, arg) in enumerate(ex["actions"]):
                    st.button(label, key=f"orb_act_{len(ss.chat)}_{j}", on_click=run_action, args=(kind, arg), use_container_width=True)
    if ss.chat:
        st.button("🗑️ Limpiar conversación", key="orb_clear", on_click=lambda: ss.chat.clear())

    with st.expander("📋 Guías paso a paso"):
        gid = st.selectbox("Guía", list(guides), format_func=lambda g: guides[g]["modulo"], key="guide_sel")
        if ss.guide_last != gid:
            ss.guide_last, ss.guide_step = gid, 0
        steps = guides[gid]["pasos"]
        i = min(ss.guide_step, len(steps) - 1)
        instr, action = steps[i]
        render(f'<div class="sr-card"><div class="sr-muted">Paso {i + 1} de {len(steps)}</div>{bar((i + 1) / len(steps) * 100)}'
               f'<div class="sr-title" style="margin-top:.5rem">{esc(instr)}</div><div style="margin-top:.4rem">👉 <b>Qué hacer:</b> {esc(action)}</div></div>')
        c1, c2 = st.columns(2)
        c1.button("← Anterior", key="orb_prev", on_click=step_to, args=(i - 1,), use_container_width=True, disabled=i == 0)
        c2.button("Siguiente →", key="orb_next", on_click=step_to, args=(i + 1,), type="primary", use_container_width=True, disabled=i >= len(steps) - 1)


def assistant_orb() -> None:
    """Floating orb in the bottom-right corner; opens the assistant in a popover."""
    with st.container(key="orb"):
        with st.popover("🤖", help="Asistente Safe ROAD"):
            assistant_panel()


# ----------------------------------------------------------------------------
# 16. ROUTER
# ----------------------------------------------------------------------------
def ensure_light_theme() -> bool:
    """Create .streamlit/config.toml (light theme) next to the app if missing. Returns True if it was just created."""
    cfg = os.path.join(BASE_DIR, ".streamlit", "config.toml")
    if os.path.exists(cfg):
        return False
    try:
        os.makedirs(os.path.dirname(cfg), exist_ok=True)
        with open(cfg, "w", encoding="utf-8") as fh:
            fh.write('[theme]\nbase = "light"\nprimaryColor = "#FF6349"\nbackgroundColor = "#F8F9FA"\n'
                     'secondaryBackgroundColor = "#FFFFFF"\ntextColor = "#1E293B"\n\n[browser]\ngatherUsageStats = false\n')
        return True
    except OSError:
        return False


def main() -> None:
    st.markdown(build_css(), unsafe_allow_html=True)
    if ensure_light_theme():
        st.warning("Creé el archivo .streamlit/config.toml para usar el tema claro. Cierra la app con Ctrl+C y ejecútala otra vez para verlo.")
    cat = get_catalog()
    if cat["missing"]:
        st.error("Faltan archivos de datos: " + ", ".join(cat["missing"]))
        st.info(f"Busqué en esta carpeta: {BASE_DIR}  (y en la subcarpeta «datos»).\n\n"
                "Copia ahí esos archivos .csv (o el Excel «Saveroad_App_Maestro_Final.xlsx») y recarga la página.")
        st.caption("Archivos .csv/.xlsx que sí encontré: " + (", ".join(cat.get("found", [])) or "ninguno"))
        st.stop()
    st.session_state.cat = cat
    init_session(cat)
    ss = st.session_state

    if ss.user_id is None:
        view_login()
        return
    if not S()["quiz_done"]:
        view_onboarding()
        return
    sync_unlocks()

    if ss.ctx:   # contextual views: no navbar, only a Back button
        kind, item = ss.ctx
        views = {"curso": lambda: view_lesson(item), "parte": lambda: view_part(item), "carrito": view_cart}
        if kind in views:
            views[kind]()
        else:
            ss.ctx = None
            st.rerun()
    else:
        navbar()
        {"Inicio": view_inicio, "Cursos": view_cursos, "Mantenimiento": view_mantenimiento,
         "Misiones": view_misiones, "Perfil": view_perfil}[ss.page]()
    assistant_orb()


main()