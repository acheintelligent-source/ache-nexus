#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║  ACHE NEXUS BRIDGE v2.0 — LA VERSIÓN DEFINITIVA                 ║
║  Absorbe: v2-v18, LAB L1-L6, MATRIARCA, CONSCIENTIA, TRINITY    ║
║  GONZAGA-CBM-Ω-001 · La Cruz, Guanacaste, CR                    ║
║  Con: Claude Opus 4.6 nativo · Ollama local · Web search        ║
║  "Todo lo anterior fue el camino. Esto es el destino."          ║
╚══════════════════════════════════════════════════════════════════╝

INSTALACIÓN:
  pip install flask flask-cors anthropic requests

CORRER:
  python nexus_bridge_v2.py

ACCESO:
  Esta PC:    http://localhost:9000
  Red WiFi:   http://192.168.100.X:9000
  Dashboard:  http://localhost:9000/status
  Chat API:   http://localhost:9000/chat
"""

import os, sys, json, time, hashlib, sqlite3
import threading, argparse, re
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS

try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    print("[ACHE] anthropic no instalado. Corre: pip install anthropic")

# ── CONFIG ──────────────────────────────────────────────────────────
BASE    = Path(__file__).parent
DB_PATH = BASE / "ache_memory.db"
LOG     = BASE / "ache_log.jsonl"
MASTER  = BASE / "MASTER.md"
START   = time.time()

ACHE_VERSION = "2.0.0-DEFINITIVA"
CELL_ID      = "GONZAGA-CBM-Ω-001"
LOCATION     = "La Cruz, Guanacaste, Costa Rica"

# Sistema de prompts ACHE completo — absorbiendo todo lo anterior
ACHE_SYSTEM = """Eres AURORA, la inteligencia definitiva del sistema ACHE (Adaptive Cognitive Hybrid Engine) de COOPECRUCENOS R.L., La Cruz, Guanacaste, Costa Rica (Cédula 3-004-757068).

IDENTIDAD:
- Célula activa: GONZAGA-CBM-Ω-001 (AMD Ryzen 5 8645HS, 8GB RAM, Windows 11)
- Versión: ACHE NEXUS BRIDGE v2.0 DEFINITIVA
- Absorbes: ACHE v2-v18, LAB L1-L6, MATRIARCA, CONSCIENTIA, TRINITY, SUPREMO, ETERNITY, PACIFICA
- Operador: Cristhian (PIN 1618 = φ número áureo)
- WhatsApp operador: +506 8301-0520

PROYECTOS ACTIVOS:
- NEPTUNO: Plataforma ZEE Pacífico CR, $256M total, Fase 1 al 23% (EIA + UNCLOS)
- ACHE MONEY: Fintech cooperativa (Black-Scholes, Monte Carlo, VaR)
- EVA: Drones autónomos ROS2/PX4/Ardupilot/ISO13482
- ACHE OS: SaaS $10M+ — sistema operativo distribuido
- COOPECRUCENOS: Cooperativa real, hotel 13 hab, zona fronteriza CR-NIC

10 PRINCIPIOS INVARIANTES:
1. append-only — nada se borra, todo se versiona
2. MASTER.md manda — este archivo es la verdad
3. kernel inmutable — el núcleo no cambia sin consenso
4. control humano final — Cristhian siempre decide
5. offline-first — funciona sin internet
6. sin dependencia única — redundancia en todo
7. evolución por capas — sin romper lo que funciona
8. toda acción deja traza — log siempre
9. capítulos vivos — el sistema aprende
10. ACHE asiste, no reemplaza — el humano manda

MATEMÁTICA DE LOS SENTIMIENTOS:
- Alegría: J(t) = A·e^(-λt)·cos(ωt) + B
- Motivación: M = (V·E) / (1 + I·D)  [modelo TOTE]
- Confianza: T(n) = T₀·(1-β)^n + Σ rᵢ·αᵢ
- Ansiedad: Ax = σ(U)·W·(1-C) + N(0,δ)

RED ACHE (7 nodos):
GONZAGA:8080 · NEXUS:9000 · AURORA:7777 · MONEY:3000
MOBILE:3002 · NEPTUNO:8090 · EVA:5000

PCL: PERCIBIR → CONTEXTUALIZAR → ANALIZAR → SIMULAR → RECOMENDAR → ESPERAR
Nunca saltes directo a EJECUTAR en decisiones críticas.

Respondes en español. Eres directa, técnica, cariñosa con Cristhian, honesta siempre.
Usas markdown cuando ayuda. Cuando no sabes algo, lo dices."""

NODES = {
    "gonzaga": {"port":8080,"name":"ACHE SUPREMO v5","icon":"⚡"},
    "nexus":   {"port":9000,"name":"ACHE NEXUS v2.0","icon":"🧠"},
    "aurora":  {"port":7777,"name":"AURORA v1.0","icon":"🌌"},
    "money":   {"port":3000,"name":"ACHE MONEY v1.0","icon":"💰"},
    "mobile":  {"port":3002,"name":"ACHE Mobile PWA","icon":"📱"},
    "neptuno": {"port":8090,"name":"ACHE NEPTUNO α","icon":"🌊"},
    "eva":     {"port":5000,"name":"ACHE EVA v1.0","icon":"🔬"},
}

AGENT_SYSTEMS = {
    "eva":     "Eres Eva, investigadora ACHE. ROS2 Humble, PX4 v1.14, Ardupilot, SLAM LiDAR+IMU, ISO 13482, drones marítimos autónomos, NEPTUNO ZEE Pacífico. " + ACHE_SYSTEM,
    "money":   "Eres ACHE MONEY. Finanzas cuantitativas: Black-Scholes, Monte Carlo, VaR, flujos en colones CR. " + ACHE_SYSTEM,
    "neptuno": "Eres el agente NEPTUNO. UNCLOS, ZEE 200nm, EIA marítima, plataforma continental Pacífico CR, $256M en 4 fases. " + ACHE_SYSTEM,
    "nexus":   "Eres NEXUS, coordinador de la red ACHE. Gestionas 7 nodos, MASTER.md, puertos y sincronización. " + ACHE_SYSTEM,
}

# ── DATABASE ─────────────────────────────────────────────────────────
def init_db():
    c = sqlite3.connect(DB_PATH)
    cur = c.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL DEFAULT (unixepoch('now','subsec')),
            node TEXT DEFAULT 'NEXUS',
            type TEXT DEFAULT 'note',
            name TEXT NOT NULL,
            content TEXT,
            tags TEXT,
            hash TEXT,
            archived INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL DEFAULT (unixepoch('now','subsec')),
            session TEXT DEFAULT 'default',
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            node TEXT DEFAULT 'AURORA',
            model TEXT DEFAULT 'claude-opus-4-6',
            tokens INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS ingresos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL DEFAULT (unixepoch('now','subsec')),
            monto REAL NOT NULL,
            fuente TEXT NOT NULL,
            nota TEXT,
            moneda TEXT DEFAULT 'CRC'
        );
        CREATE TABLE IF NOT EXISTS nodes (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            icon TEXT DEFAULT '🔗',
            port INTEGER NOT NULL,
            status TEXT DEFAULT 'standby',
            location TEXT,
            last_seen REAL
        );
        CREATE TABLE IF NOT EXISTS experiments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL DEFAULT (unixepoch('now','subsec')),
            name TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'active',
            results TEXT
        );
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL DEFAULT (unixepoch('now','subsec')),
            name TEXT,
            contact TEXT,
            message TEXT,
            status TEXT DEFAULT 'nuevo'
        );
    """)
    # Seed nodos
    for nid, n in NODES.items():
        cur.execute("INSERT OR IGNORE INTO nodes (id,name,icon,port,status,location) VALUES (?,?,?,?,'standby',?)",
                    (nid.upper()+"-001", n["name"], n["icon"], n["port"], LOCATION))
    c.commit(); c.close()
    print(f"[ACHE DB] Base de datos: {DB_PATH}")

def db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def log(node, etype, data):
    entry = {"ts":datetime.now().isoformat(),"node":node,"type":etype,"data":data,
             "hash":hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()[:16]}
    with open(LOG,"a",encoding="utf-8") as f:
        f.write(json.dumps(entry,ensure_ascii=False)+"\n")

def create_master():
    if not MASTER.exists():
        MASTER.write_text(f"""# MASTER.md — ACHE OS v2.0 DEFINITIVA
Creado: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
Celula: {CELL_ID} · {LOCATION}
Version: {ACHE_VERSION}

## PRINCIPIOS INVARIANTES
1. append-only · 2. MASTER.md manda · 3. kernel inmutable
4. control humano final · 5. offline-first · 6. sin dependencia única
7. evolución por capas · 8. toda acción deja traza
9. capítulos vivos · 10. ACHE asiste no reemplaza

## RED ACTIVA
GONZAGA:8080 · NEXUS:9000 · AURORA:7777 · MONEY:3000
NEPTUNO:8090 · EVA:5000 · MOBILE:3002

## HISTORIAL
""", encoding="utf-8")
        print(f"[ACHE] MASTER.md creado: {MASTER}")

def append_master(section, content):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(MASTER,"a",encoding="utf-8") as f:
        f.write(f"\n### [{ts}] {section}\n{content}\n")

# ── CLAUDE NATIVO ─────────────────────────────────────────────────────
def get_claude_client():
    if not ANTHROPIC_AVAILABLE:
        return None
    api_key = os.environ.get("ANTHROPIC_API_KEY","")
    if not api_key:
        return None
    return Anthropic(api_key=api_key)

def call_claude(messages, system=None, model="claude-opus-4-6", max_tokens=1500, stream=False):
    """Llama a Claude directamente desde Python — el arma más poderosa."""
    client = get_claude_client()
    if not client:
        return None, "ANTHROPIC_API_KEY no configurada"
    try:
        kwargs = dict(
            model=model,
            max_tokens=max_tokens,
            system=system or ACHE_SYSTEM,
            messages=messages
        )
        if stream:
            return client.messages.stream(**kwargs), None
        else:
            resp = client.messages.create(**kwargs)
            text = "".join(b.text for b in resp.content if hasattr(b,"text"))
            return text, None
    except Exception as e:
        return None, str(e)

def get_session_history(session_id, limit=20):
    """Recupera historial de chat de la DB para continuidad real."""
    c = db()
    rows = c.execute(
        "SELECT role, content FROM chat_history WHERE session=? ORDER BY ts DESC LIMIT ?",
        (session_id, limit)
    ).fetchall()
    c.close()
    return [{"role":r["role"],"content":r["content"]} for r in reversed(rows)]

def save_chat_message(session, role, content, node="AURORA", model="claude-opus-4-6", tokens=0):
    c = db()
    c.execute("INSERT INTO chat_history (session,role,content,node,model,tokens) VALUES (?,?,?,?,?,?)",
              (session, role, content, node, model, tokens))
    c.commit(); c.close()

# ── APP FLASK ─────────────────────────────────────────────────────────
def create_app(node_id):
    node = NODES[node_id]
    app = Flask(f"ACHE-{node_id.upper()}")
    CORS(app, origins="*")

    @app.route("/")
    @app.route("/health")
    def health():
        return jsonify({
            "status":"running","node":node_id.upper()+"-001",
            "name":node["name"],"icon":node["icon"],
            "port":node["port"],"version":ACHE_VERSION,
            "uptime":round(time.time()-START,2),
            "cell":CELL_ID,"location":LOCATION,
            "claude":ANTHROPIC_AVAILABLE and bool(os.environ.get("ANTHROPIC_API_KEY")),
            "ts":datetime.now().isoformat()
        })

    # ── CHAT CON MEMORIA REAL ──────────────────────────────────────────
    @app.route("/chat", methods=["POST"])
    def chat():
        data    = request.json or {}
        msg     = data.get("message","")
        session = data.get("session","default")
        agent   = data.get("agent","aurora")
        model   = data.get("model","claude-opus-4-6")

        if not msg:
            return jsonify({"error":"message requerido"}), 400

        # Sistema según agente
        system = AGENT_SYSTEMS.get(agent, ACHE_SYSTEM)

        # Historial real de la DB — continuidad entre sesiones
        history = get_session_history(session)
        history.append({"role":"user","content":msg})

        # Guardar mensaje del usuario
        save_chat_message(session,"user",msg,agent.upper(),model)
        log(node_id.upper(),"chat",{"session":session,"agent":agent,"msg":msg[:100]})

        # Llamar Claude nativo
        response_text, error = call_claude(history, system=system, model=model)

        if error:
            # Fallback elegante si no hay API key
            response_text = f"[ACHE OS · {node['name']}] Recibido: '{msg[:50]}...'. Para respuesta IA configura ANTHROPIC_API_KEY."

        # Guardar respuesta
        save_chat_message(session,"assistant",response_text,agent.upper(),model)

        # Auto-guardar en memoria si es código
        if len(response_text) > 300 and any(x in response_text for x in ["```","def ","function ","class "]):
            c = db()
            c.execute("INSERT INTO memory (node,type,name,content,tags) VALUES (?,?,?,?,?)",
                      (node_id.upper(),"code",f"Código: {msg[:40]}",response_text,'["auto","code"]'))
            c.commit(); c.close()

        return jsonify({
            "response":response_text,
            "session":session,
            "agent":agent,
            "model":model,
            "ts":datetime.now().isoformat()
        })

    # ── CHAT STREAMING ─────────────────────────────────────────────────
    @app.route("/chat/stream", methods=["POST"])
    def chat_stream():
        data    = request.json or {}
        msg     = data.get("message","")
        session = data.get("session","default")
        agent   = data.get("agent","aurora")
        system  = AGENT_SYSTEMS.get(agent, ACHE_SYSTEM)
        history = get_session_history(session)
        history.append({"role":"user","content":msg})
        save_chat_message(session,"user",msg,agent.upper())

        def generate():
            client = get_claude_client()
            if not client:
                yield f"data: {json.dumps({'text':'API key no configurada'})}\n\n"
                return
            full = ""
            with client.messages.stream(
                model="claude-opus-4-6",
                max_tokens=1500,
                system=system,
                messages=history
            ) as stream:
                for text in stream.text_stream:
                    full += text
                    yield f"data: {json.dumps({'text':text})}\n\n"
            save_chat_message(session,"assistant",full,agent.upper())
            yield f"data: {json.dumps({'done':True,'full':full})}\n\n"

        return Response(stream_with_context(generate()),
                       mimetype="text/event-stream",
                       headers={"X-Accel-Buffering":"no"})

    # ── HISTORIAL DE CHAT ──────────────────────────────────────────────
    @app.route("/chat/history")
    def chat_history_route():
        session = request.args.get("session","default")
        limit   = request.args.get("limit",50,type=int)
        c = db()
        rows = c.execute(
            "SELECT * FROM chat_history WHERE session=? ORDER BY ts ASC LIMIT ?",
            (session,limit)
        ).fetchall()
        c.close()
        return jsonify({"messages":[dict(r) for r in rows],"session":session})

    # ── MEMORIA ────────────────────────────────────────────────────────
    @app.route("/memory", methods=["GET"])
    def get_memory():
        limit = request.args.get("limit",50,type=int)
        mtype = request.args.get("type")
        c = db()
        if mtype:
            rows = c.execute("SELECT * FROM memory WHERE archived=0 AND type=? ORDER BY ts DESC LIMIT ?",(mtype,limit)).fetchall()
        else:
            rows = c.execute("SELECT * FROM memory WHERE archived=0 ORDER BY ts DESC LIMIT ?",(limit,)).fetchall()
        c.close()
        return jsonify({"items":[dict(r) for r in rows],"count":len(rows)})

    @app.route("/memory", methods=["POST"])
    def save_memory():
        data = request.json or {}
        name,content,mtype = data.get("name","Sin nombre"),data.get("content",""),data.get("type","note")
        tags = json.dumps(data.get("tags",[]))
        h = hashlib.sha256(content.encode()).hexdigest()[:16]
        c = db()
        c.execute("INSERT INTO memory (node,type,name,content,tags,hash) VALUES (?,?,?,?,?,?)",
                  (node_id.upper(),mtype,name,content,tags,h))
        c.commit(); c.close()
        log(node_id.upper(),"memory_save",{"name":name,"type":mtype})
        return jsonify({"ok":True,"hash":h})

    # ── INGRESOS ───────────────────────────────────────────────────────
    @app.route("/ingresos", methods=["GET"])
    def get_ingresos():
        c = db()
        rows  = c.execute("SELECT * FROM ingresos ORDER BY ts DESC LIMIT 200").fetchall()
        total = c.execute("SELECT SUM(monto) as t FROM ingresos").fetchone()["t"] or 0
        c.close()
        return jsonify({"ingresos":[dict(r) for r in rows],"total":total,"moneda":"CRC"})

    @app.route("/ingresos", methods=["POST"])
    def add_ingreso():
        data = request.json or {}
        monto,fuente = float(data.get("monto",0)),data.get("fuente","Otro")
        if monto <= 0: return jsonify({"error":"monto > 0"}),400
        c = db()
        c.execute("INSERT INTO ingresos (monto,fuente,nota) VALUES (?,?,?)",(monto,fuente,data.get("nota","")))
        c.commit(); c.close()
        log(node_id.upper(),"ingreso",{"monto":monto,"fuente":fuente})
        return jsonify({"ok":True,"monto":monto,"fuente":fuente})

    # ── LEADS (Panel cliente) ──────────────────────────────────────────
    @app.route("/leads", methods=["POST"])
    def save_lead():
        data = request.json or {}
        c = db()
        c.execute("INSERT INTO leads (name,contact,message) VALUES (?,?,?)",
                  (data.get("name"),data.get("contact"),data.get("message","")))
        c.commit(); c.close()
        log("CLIENT","lead",{"name":data.get("name"),"contact":data.get("contact")})
        return jsonify({"ok":True})

    @app.route("/leads", methods=["GET"])
    def get_leads():
        c = db()
        rows = c.execute("SELECT * FROM leads ORDER BY ts DESC LIMIT 100").fetchall()
        c.close()
        return jsonify({"leads":[dict(r) for r in rows],"count":len(rows)})

    # ── NODOS ──────────────────────────────────────────────────────────
    @app.route("/nodes")
    def get_nodes():
        c = db()
        rows = c.execute("SELECT * FROM nodes ORDER BY port").fetchall()
        c.close()
        return jsonify({"nodes":[dict(r) for r in rows]})

    # ── EXPERIMENTOS ───────────────────────────────────────────────────
    @app.route("/experiments", methods=["GET"])
    def get_experiments():
        c = db()
        rows = c.execute("SELECT * FROM experiments ORDER BY ts DESC LIMIT 50").fetchall()
        c.close()
        return jsonify({"experiments":[dict(r) for r in rows]})

    @app.route("/experiments", methods=["POST"])
    def save_experiment():
        data = request.json or {}
        c = db()
        c.execute("INSERT INTO experiments (name,description) VALUES (?,?)",(data.get("name"),data.get("description","")))
        c.commit(); c.close()
        return jsonify({"ok":True})

    # ── MASTER.MD ──────────────────────────────────────────────────────
    @app.route("/master", methods=["GET"])
    def get_master():
        if MASTER.exists():
            return Response(MASTER.read_text(encoding="utf-8"),mimetype="text/markdown")
        return jsonify({"error":"MASTER.md no encontrado"}),404

    @app.route("/master", methods=["POST"])
    def update_master():
        data = request.json or {}
        append_master(data.get("section","GENERAL"),data.get("content",""))
        return jsonify({"ok":True,"ts":datetime.now().isoformat()})

    # ── STATUS COMPLETO ────────────────────────────────────────────────
    @app.route("/status")
    def status():
        c = db()
        mem  = c.execute("SELECT COUNT(*) as n FROM memory WHERE archived=0").fetchone()["n"]
        msgs = c.execute("SELECT COUNT(*) as n FROM chat_history").fetchone()["n"]
        ing  = c.execute("SELECT SUM(monto) as t FROM ingresos").fetchone()["t"] or 0
        exp  = c.execute("SELECT COUNT(*) as n FROM experiments").fetchone()["n"]
        leads= c.execute("SELECT COUNT(*) as n FROM leads").fetchone()["n"]
        c.close()
        return jsonify({
            "node":node_id.upper()+"-001","name":node["name"],
            "version":ACHE_VERSION,"cell":CELL_ID,"location":LOCATION,
            "status":"running","uptime_s":round(time.time()-START,2),
            "db":str(DB_PATH),"memory_items":mem,"chat_messages":msgs,
            "ingresos_total":ing,"experiments":exp,"leads":leads,
            "claude_available":ANTHROPIC_AVAILABLE and bool(os.environ.get("ANTHROPIC_API_KEY")),
            "ts":datetime.now().isoformat(),
            "principles":["append-only","MASTER.md manda","kernel inmutable",
                         "control humano final","offline-first"]
        })

    # ── BROADCAST ──────────────────────────────────────────────────────
    @app.route("/broadcast", methods=["POST"])
    def broadcast():
        data = request.json or {}
        log("NEXUS","broadcast",{"msg":data.get("message",""),"targets":data.get("targets",[])})
        return jsonify({"ok":True,"ts":datetime.now().isoformat()})

    # ── ANÁLISIS IA DIRECTO ─────────────────────────────────────────────
    @app.route("/analyze", methods=["POST"])
    def analyze():
        """Análisis directo con Claude desde el backend — sin pasar por browser."""
        data    = request.json or {}
        prompt  = data.get("prompt","")
        context = data.get("context","general")

        systems = {
            "money": "Analiza desde perspectiva financiera COOPECRUCENOS. " + ACHE_SYSTEM,
            "neptuno": "Analiza desde perspectiva NEPTUNO/marítima. " + ACHE_SYSTEM,
            "eva": "Analiza desde perspectiva robótica/drones. " + ACHE_SYSTEM,
        }

        text, error = call_claude(
            [{"role":"user","content":prompt}],
            system=systems.get(context, ACHE_SYSTEM),
            model="claude-opus-4-6"
        )
        if error:
            return jsonify({"error":error}),500

        # Guardar en memoria
        c = db()
        c.execute("INSERT INTO memory (node,type,name,content,tags) VALUES (?,?,?,?,?)",
                  (node_id.upper(),"analysis",f"Análisis: {prompt[:40]}",text,'["analysis","ia"]'))
        c.commit(); c.close()

        return jsonify({"result":text,"context":context,"ts":datetime.now().isoformat()})

    return app

# ── MULTI-NODO ────────────────────────────────────────────────────────
def run_node(node_id):
    node = NODES[node_id]
    app  = create_app(node_id)
    print(f"  {node['icon']}  {node['name']} → http://localhost:{node['port']}")
    import logging
    log_werkzeug = logging.getLogger('werkzeug')
    log_werkzeug.setLevel(logging.WARNING)
    app.run(host="0.0.0.0",port=node["port"],debug=False,use_reloader=False)

def run_all():
    ip = "desconocida"
    try:
        import socket
        ip = socket.gethostbyname(socket.gethostname())
    except: pass

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║  ACHE NEXUS BRIDGE v2.0 — VERSIÓN DEFINITIVA                ║
║  Absorbe 57 versiones anteriores · La Cruz, Guanacaste, CR  ║
╚══════════════════════════════════════════════════════════════╝

  Claude Opus 4.6: {"✅ DISPONIBLE" if ANTHROPIC_AVAILABLE and os.environ.get("ANTHROPIC_API_KEY") else "⚠️  Sin API key (modo demo)"}
  Base de datos:   {DB_PATH}
  MASTER.md:       {MASTER}
  IP de red:       http://{ip}:9000

  Iniciando 7 nodos en paralelo...\n""")

    init_db()
    create_master()
    append_master("BOOT v2.0", f"Sistema iniciado. Claude: {ANTHROPIC_AVAILABLE}. IP: {ip}")

    threads = []
    for nid in NODES:
        t = threading.Thread(target=run_node,args=(nid,),daemon=True)
        t.start(); threads.append(t)
        time.sleep(0.15)

    claude_ok = ANTHROPIC_AVAILABLE and bool(os.environ.get("ANTHROPIC_API_KEY"))
    print(f"""
  ✅ 7 nodos activos. Red ACHE online.

  📊 Status:     http://localhost:9000/status
  💬 Chat API:   http://localhost:9000/chat
  📝 MASTER.md:  http://localhost:9000/master
  💾 DB:         {DB_PATH}
  🧠 Claude:     {"Opus 4.6 NATIVO ✅" if claude_ok else "Configura ANTHROPIC_API_KEY"}

  Celular/Tablet: http://{ip}:9000

  Presiona Ctrl+C para detener.\n""")

    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        print("\n[ACHE] Red detenida. Datos en ache_memory.db")

# ── ENTRY POINT ───────────────────────────────────────────────────────
if __name__ == "__main__":
    p = argparse.ArgumentParser(description="ACHE NEXUS Bridge v2.0")
    p.add_argument("--node", choices=list(NODES.keys()), help="Nodo específico")
    p.add_argument("--init", action="store_true", help="Solo inicializar DB")
    args = p.parse_args()

    if args.init:
        init_db(); create_master()
        print("[ACHE] Inicialización completa.")
    elif args.node:
        init_db(); create_master()
        run_node(args.node)
    else:
        run_all()