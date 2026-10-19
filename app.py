import subprocess
import json
import sys
import os
import re
import threading
import time
import requests
from datetime import datetime
from flask import Flask, send_from_directory, jsonify

AQUI = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=AQUI, static_url_path="")

# =========================================================
# CONFIGURACIÓN STARLINK
# =========================================================
os.environ.setdefault("STARLINK_CLIENT_ID", "a08eec8d-01ce-4a5b-9bbc-facec3615cc9")
os.environ.setdefault("STARLINK_CLIENT_SECRET", "spx_df_XMQjQS4OCKWeJ3K71YU1uS5kSviXDAZXhy5SSWxVMvyPt8jP")

BASE_STARLINK = "https://starlink.com/api/public/v2"
TOKEN_URL = "https://starlink.com/api/auth/connect/token"
UA = {"User-Agent": "monitor-interno-starlink/1.0"}
STARLINK_CACHE = {}
_tok = {"v": None, "exp": 0.0}

GROUPS_FILE = os.path.join(AQUI, "groups.json")

def load_json(path, default):
    if not os.path.exists(path): return default
    try:
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    except Exception: return default

# =========================================================
# LÓGICA STARLINK
# =========================================================
def token_starlink():
    if _tok["v"] and time.time() < _tok["exp"]: return _tok["v"]
    r = requests.post(TOKEN_URL, data={"grant_type": "client_credentials", "client_id": os.environ.get("STARLINK_CLIENT_ID"), "client_secret": os.environ.get("STARLINK_CLIENT_SECRET")}, headers=UA, timeout=30)
    r.raise_for_status()
    j = r.json()
    _tok["v"] = j["access_token"]
    _tok["exp"] = time.time() + min(int(j.get("expires_in", 900)), 900) - 60
    return _tok["v"]

def api_starlink(method, path, **kw):
    for intento in (1, 2):
        h = {**UA, "Authorization": f"Bearer {token_starlink()}", "Accept": "application/json"}
        r = requests.request(method, BASE_STARLINK + path, headers=h, timeout=45, **kw)
        if r.status_code == 401 and intento == 1:
            _tok["v"] = None
            continue
        return r

def actualizar_starlink_bg():
    while True:
        try:
            r = api_starlink("GET", "/user-terminals")
            if r.status_code == 200:
                terms = r.json().get("content", {}).get("results", [])
                for t in terms:
                    utid = t.get("userTerminalId")
                    if utid:
                        STARLINK_CACHE[utid] = {
                            "estado": "OK" if t.get("active") else "FAIL",
                            "ultima_lectura": datetime.now().strftime("%d/%m/%Y-%H:%M:%S")
                        }
            time.sleep(300)
        except Exception:
            time.sleep(60)

# =========================================================
# LÓGICA EZVIZ
# =========================================================
def parsear_tabla(salida):
    lineas = salida.splitlines()
    idx_header = idx_sep = None
    for i, linea in enumerate(lineas):
        if "serial" in linea.lower() and "name" in linea.lower() and "status" in linea.lower():
            idx_header, idx_sep = i, i + 1
            break
    if idx_header is None: return []
    rangos = [(m.start(), m.end()) for m in re.finditer(r"-+", lineas[idx_sep])]
    nombres = [(lineas[idx_header][ini:fin].strip() if ini < len(lineas[idx_header]) else "") for (ini, fin) in rangos]
    dispositivos = []
    for linea in lineas[idx_sep + 1:]:
        if not linea.strip() or re.match(r"^\s*(INFO|WARNING|ERROR|DEBUG)\b", linea): break
        fila = {}
        for (ini, fin), nombre in zip(rangos, nombres):
            if nombre: fila[nombre] = linea[ini:fin].strip() if ini < len(linea) else ""
        if fila.get("serial"): dispositivos.append(fila)
    return dispositivos

def fetch_cameras():
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"; env["PYTHONUTF8"] = "1"
    try:
        resultado = subprocess.run([sys.executable, "-X", "utf8", "-m", "pyezvizapi", "devices", "status"], capture_output=True, text=True, cwd=AQUI, timeout=30, env=env)
        if resultado.returncode != 0: return {"error": "Error pyezvizapi"}
        dispositivos = parsear_tabla(resultado.stdout)
        for d in dispositivos: d["_estado"] = {"online": (d.get("status") == "1")}
        return {"cameras": dispositivos}
    except Exception as e:
        return {"error": str(e)}

# =========================================================
# RUTAS FLASK
# =========================================================
@app.route("/")
def index():
    return send_from_directory(AQUI, "index.html")

@app.route("/api/proyectos")
def api_proyectos():
    groups = load_json(GROUPS_FILE, {"global": {}, "subgroups": {}})
    data_cams = fetch_cameras()
    if "error" in data_cams: return jsonify({"error": data_cams["error"]})
    
    camaras = data_cams.get("cameras", [])
    proyectos = {}

    for cam in camaras:
        serial = cam.get("serial")
        subgrupos = [sub for sub, seriales in groups.get("subgroups", {}).items() if isinstance(seriales, list) and serial in seriales]
        proy_name = subgrupos[0] if subgrupos else "SIN ASIGNAR"
        
        if proy_name not in proyectos:
            antena_id = groups.get("subgroups", {}).get(proy_name, {}).get("starlink_id") if isinstance(groups.get("subgroups", {}).get(proy_name), dict) else None
            ant_info = STARLINK_CACHE.get(antena_id, {"estado": "SIN DATOS", "ultima_lectura": "—"})
            proyectos[proy_name] = {"nombre": proy_name, "antena": ant_info, "camaras": []}

        nombre_parts = (cam.get("name") or "").split("-")
        tipo_cam = nombre_parts[-1].strip().upper() if len(nombre_parts) >= 3 else "CAM"
        
        proyectos[proy_name]["camaras"].append({
            "tipo": tipo_cam,
            "estado": "OK" if cam.get("_estado", {}).get("online") else "FAIL"
        })

    return jsonify(list(proyectos.values()))

if __name__ == "__main__":
    threading.Thread(target=actualizar_starlink_bg, daemon=True).start()
    print("Servidor en http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False, threaded=True)