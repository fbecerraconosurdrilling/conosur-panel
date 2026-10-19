import json
import os
import sys
import time
import threading
import subprocess
import urllib.request
import urllib.error
import webbrowser
from datetime import datetime

import pystray
from PIL import Image, ImageDraw
import tkinter as tk
from tkinter import messagebox

FLASK_BASE = "http://127.0.0.1:5000"
REPO_DIR = r"C:\conosur-panel\TABLERO UNIFICADO DE STALINK CON EZVIZ TODO JUNTO"
GIT_EXE = r"C:\Program Files\Git\bin\git.exe"
PANEL_URL = "https://fbecerraconosurdrilling.github.io/conosur-panel/"
BRANCH = "main"
DATA_FILE = os.path.join(REPO_DIR, "data.json")
INTERVALO_SEG = 5 * 60

estado = {
    "ultima_publicacion": None,
    "ultimo_resultado": "—",
    "proximo_ciclo": None,
    "corriendo": True,
    "forzar_ahora": False,
}
icono_ref = None

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def http_get(path):
    url = FLASK_BASE + path
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        raise RuntimeError(f"Error leyendo {url}: {e}")

def git(*args):
    try:
        r = subprocess.run([GIT_EXE, *args], cwd=REPO_DIR, capture_output=True, text=True, timeout=90)
        return r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return False, str(e)

def construir_payload():
    """Llama a la nueva ruta unificada"""
    proyectos = http_get("/api/proyectos")
    
    if isinstance(proyectos, dict) and "error" in proyectos:
        raise RuntimeError(f"El servidor devolvió error: {proyectos['error']}")

    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "proyectos": proyectos
    }

def publicar(payload):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    ok, out = git("add", "data.json")
    if not ok: raise RuntimeError(f"git add falló: {out}")

    ok, status = git("status", "--porcelain", "data.json")
    if not ok: raise RuntimeError(f"git status falló: {status}")
    if not status.strip(): return "sin cambios"

    msg = f"data.json · {payload['timestamp']} · {len(payload['proyectos'])} proyectos"
    ok, out = git("commit", "-m", msg)
    if not ok: raise RuntimeError(f"git commit falló: {out}")

    ok, out = git("push", "origin", BRANCH)
    if not ok: raise RuntimeError(f"git push falló: {out}")

    return "push OK"

def ciclo():
    try:
        payload = construir_payload()
        resultado = publicar(payload)
        estado["ultima_publicacion"] = datetime.now()
        estado["ultimo_resultado"] = resultado
        log(f"✔ Ciclo OK ({resultado})")
        actualizar_tooltip()
    except Exception as e:
        estado["ultimo_resultado"] = f"error: {e}"
        log(f"❌ Error en ciclo: {e}")
        actualizar_tooltip()

def loop_automatico():
    while estado["corriendo"]:
        for _ in range(INTERVALO_SEG):
            if not estado["corriendo"]: return
            if estado["forzar_ahora"]:
                estado["forzar_ahora"] = False
                break
            time.sleep(1)
        if not estado["corriendo"]: return
        ciclo()

def crear_imagen_icono():
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((4, 4, size - 4, size - 4), fill="#0d1117", outline="#2e7be0", width=2)
    d.ellipse((22, 22, 42, 42), fill="#3fb950")
    return img

def actualizar_tooltip():
    if icono_ref is None: return
    ult = estado["ultima_publicacion"]
    ult_txt = ult.strftime("%H:%M:%S") if ult else "—"
    icono_ref.title = f"CONOSUR Publicador\nÚltima: {ult_txt}\nResultado: {estado['ultimo_resultado']}"

def on_publicar_ahora(icon, item):
    estado["forzar_ahora"] = True

def on_ver_estado(icon, item):
    ult_txt = estado["ultima_publicacion"].strftime("%Y-%m-%d %H:%M:%S") if estado["ultima_publicacion"] else "nunca"
    msg = f"Última: {ult_txt}\nResultado: {estado['ultimo_resultado']}"
    threading.Thread(target=lambda: _mostrar_info("Estado", msg), daemon=True).start()

def _mostrar_info(titulo, msg):
    root = tk.Tk(); root.withdraw(); messagebox.showinfo(titulo, msg); root.destroy()

def on_salir(icon, item):
    estado["corriendo"] = False
    icon.stop()

def main():
    global icono_ref
    threading.Thread(target=loop_automatico, daemon=True).start()
    menu = pystray.Menu(
        pystray.MenuItem("📤  Publicar ahora", on_publicar_ahora, default=True),
        pystray.MenuItem("📊  Ver estado", on_ver_estado),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("❌  Salir", on_salir),
    )
    icono_ref = pystray.Icon("conosur_publish", icon=crear_imagen_icono(), title="Publicador", menu=menu)
    actualizar_tooltip()
    icono_ref.run()

if __name__ == "__main__":
    main()