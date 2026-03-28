import os, sys, json, time, hashlib, sqlite3
import threading, argparse
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS

try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

BASE    = Path(__file__).parent
DB_PATH = BASE / "ache_memory.db"
LOG     = BASE / "ache_log.jsonl"
MASTER  = BASE / "MASTER.md"
START   = time.time()
VERSION = "2.0.0-DEFINITIVA"
CELL    = "GONZAGA-CBM-Omega-001"
LOC     = "La Cruz, Guanacaste, Costa Rica"

ACHE_SYSTEM = """Eres AURORA, la inteligencia definitiva de ACHE OS de COOPECRUCENOS R.L.
La Cruz, Guanacaste, Costa Rica. Celula: GONZAGA-CBM-Omega-001 (Ryzen 5 8645HS, Win 11).
Proyectos: NEPTUNO ($256M ZEE Pacifico CR, Fase 1 23%), ACHE MONEY, Eva (ROS2/PX4 drones).
10 Principios: append-only, MASTER.md manda, kernel inmutable, control humano final,
offline-first, sin dependencia unica, evolucion por capas, toda accion deja traza,
capitulos vivos, ACHE asiste no reemplaza.
Operador: Cristhian, WhatsApp +506 8301-0520.
PCL: PERCIBIR->CONTEXTUALIZAR->ANALIZAR->SIMULAR->RECOMENDAR->ESPERAR.
Respondes en espanol. Eres directa, tecnica, carinosa."""

NODES = {
    "gonzaga": {"port": 8080, "name": "ACHE SUPREMO v5",  "icon": "!"},
    "nexus":   {"port": 9000, "name": "ACHE NEXUS v2.0",  "icon": "*"},
    "aurora":  {"port": 7777, "name": "AURORA v1.0",       "icon": "~"},
    "money":   {"port": 3000, "name": "ACHE MONEY v1.0",  "icon": "$"},
    "mobile":  {"port": 3002, "name": "ACHE Mobile PWA",  "icon": "@"},
    "neptuno": {"port": 8090, "name": "ACHE NEPTUNO a",   "icon": "~"},
    "eva":     {"port": 5000, "name": "ACHE EVA v1.0",    "icon": "+"},
}

AGENT_SYS = {
    "eva":     "Eres Eva, investigadora ACHE. ROS2, PX4, drones maritimos, NEPTUNO. " + ACHE_SYSTEM,
    "money":   "Eres ACHE MONEY. Black-Scholes, Monte Carlo, VaR, colones CR. " + ACHE_SYSTEM,
    "neptuno": "Eres agente NEPTUNO. UNCLOS, ZEE 200nm, EIA maritima, $256M. " + ACHE_SYSTEM,
    "nexus":   "Eres NEXUS coordinador ACHE. 7 nodos, MASTER.md, puertos. " + ACHE_SYSTEM,
}

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
            model TEXT DEFAULT 'claude-sonnet-4-5',
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
            icon TEXT DEFAULT '?',
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
    for nid, n in NODES.items():
        cur.execute(
            "INSERT OR IGNORE INTO nodes (id,name,icon,port,status,location) VALUES (?,?,?,?,'standby',?)",
            (nid.upper()+"-001", n["name"], n["icon"], n["port"], LOC)
        )
    c.commit()
    c.close()
    print("[ACHE DB] Base de datos: " + str(DB_PATH))

def get_db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def log_event(node, etype, data):
    entry = {
        "ts": datetime.now().isoformat(),
        "node": node,
        "type": etype,
        "data": data,
        "hash": hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]
    }
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

def create_master():
    if not MASTER.exists():
        content = "# MASTER.md - ACHE OS v2.0 DEFINITIVA\n"
        content += "Creado: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n"
        content += "Celula: " + CELL + " - " + LOC + "\n\n"
        content += "## PRINCIPIOS\n"
        content += "1. append-only\n2. MASTER.md manda\n3. kernel inmutable\n"
        content += "4. control humano final\n5. offline-first\n\n"
        content += "## HISTORIAL\n"
        MASTER.write_text(content, encoding="utf-8")
        print("[ACHE] MASTER.md creado: " + str(MASTER))

def append_master(section, content):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(MASTER, "a", encoding="utf-8") as f:
        f.write("\n### [" + ts + "] " + section + "\n" + content + "\n")

def get_claude_client():
    if not ANTHROPIC_AVAILABLE:
        return None
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None
    return Anthropic(api_key=api_key)

def call_claude(messages, system=None, model="claude-sonnet-4-5"):
    client = get_claude_client()
    if not client:
        return None, "Sin ANTHROPIC_API_KEY"
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=1500,
            system=system or ACHE_SYSTEM,
            messages=messages
        )
        text = "".join(b.text for b in resp.content if hasattr(b, "text"))
        return text, None
    except Exception as e:
        return None, str(e)

def get_history(session, limit=20):
    c = get_db()
    rows = c.execute(
        "SELECT role, content FROM chat_history WHERE session=? ORDER BY ts DESC LIMIT ?",
        (session, limit)
    ).fetchall()
    c.close()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

def save_msg(session, role, content, node="AURORA", model="claude-sonnet-4-5"):
    c = get_db()
    c.execute(
        "INSERT INTO chat_history (session,role,content,node,model) VALUES (?,?,?,?,?)",
        (session, role, content, node, model)
    )
    c.commit()
    c.close()

def create_app(node_id):
    node = NODES[node_id]
    app = Flask("ACHE-" + node_id.upper())
    CORS(app, origins="*")

    @app.route("/")
    @app.route("/health")
    def health():
        return jsonify({
            "status": "running",
            "node": node_id.upper() + "-001",
            "name": node["name"],
            "port": node["port"],
            "version": VERSION,
            "uptime": round(time.time() - START, 2),
            "cell": CELL,
            "claude": ANTHROPIC_AVAILABLE and bool(os.environ.get("ANTHROPIC_API_KEY")),
            "ts": datetime.now().isoformat()
        })

    @app.route("/chat", methods=["POST"])
    def chat():
        data    = request.json or {}
        msg     = data.get("message", "")
        session = data.get("session", "default")
        agent   = data.get("agent", "aurora")
        if not msg:
            return jsonify({"error": "message requerido"}), 400
        system = AGENT_SYS.get(agent, ACHE_SYSTEM)
        history = get_history(session)
        history.append({"role": "user", "content": msg})
        save_msg(session, "user", msg, agent.upper())
        log_event(node_id.upper(), "chat", {"session": session, "agent": agent, "msg": msg[:80]})
        response_text, error = call_claude(history, system=system)
        if error:
            response_text = "[ACHE " + node["name"] + "] Recibido: '" + msg[:50] + "'. Configura ANTHROPIC_API_KEY para respuesta IA."
        save_msg(session, "assistant", response_text, agent.upper())
        return jsonify({
            "response": response_text,
            "session": session,
            "agent": agent,
            "ts": datetime.now().isoformat()
        })

    @app.route("/chat/history")
    def chat_history():
        session = request.args.get("session", "default")
        limit   = request.args.get("limit", 50, type=int)
        c = get_db()
        rows = c.execute(
            "SELECT * FROM chat_history WHERE session=? ORDER BY ts ASC LIMIT ?",
            (session, limit)
        ).fetchall()
        c.close()
        return jsonify({"messages": [dict(r) for r in rows]})

    @app.route("/memory", methods=["GET"])
    def get_memory():
        limit = request.args.get("limit", 50, type=int)
        mtype = request.args.get("type")
        c = get_db()
        if mtype:
            rows = c.execute(
                "SELECT * FROM memory WHERE archived=0 AND type=? ORDER BY ts DESC LIMIT ?",
                (mtype, limit)
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM memory WHERE archived=0 ORDER BY ts DESC LIMIT ?",
                (limit,)
            ).fetchall()
        c.close()
        return jsonify({"items": [dict(r) for r in rows], "count": len(rows)})

    @app.route("/memory", methods=["POST"])
    def save_memory():
        data    = request.json or {}
        name    = data.get("name", "Sin nombre")
        content = data.get("content", "")
        mtype   = data.get("type", "note")
        tags    = json.dumps(data.get("tags", []))
        h       = hashlib.sha256(content.encode()).hexdigest()[:16]
        c = get_db()
        c.execute(
            "INSERT INTO memory (node,type,name,content,tags,hash) VALUES (?,?,?,?,?,?)",
            (node_id.upper(), mtype, name, content, tags, h)
        )
        c.commit()
        c.close()
        log_event(node_id.upper(), "memory_save", {"name": name, "type": mtype})
        return jsonify({"ok": True, "hash": h})

    @app.route("/ingresos", methods=["GET"])
    def get_ingresos():
        c = get_db()
        rows  = c.execute("SELECT * FROM ingresos ORDER BY ts DESC LIMIT 200").fetchall()
        total = c.execute("SELECT SUM(monto) as t FROM ingresos").fetchone()["t"] or 0
        c.close()
        return jsonify({"ingresos": [dict(r) for r in rows], "total": total, "moneda": "CRC"})

    @app.route("/ingresos", methods=["POST"])
    def add_ingreso():
        data   = request.json or {}
        monto  = float(data.get("monto", 0))
        fuente = data.get("fuente", "Otro")
        nota   = data.get("nota", "")
        if monto <= 0:
            return jsonify({"error": "monto debe ser mayor a 0"}), 400
        c = get_db()
        c.execute(
            "INSERT INTO ingresos (monto,fuente,nota) VALUES (?,?,?)",
            (monto, fuente, nota)
        )
        c.commit()
        c.close()
        log_event(node_id.upper(), "ingreso", {"monto": monto, "fuente": fuente})
        return jsonify({"ok": True, "monto": monto, "fuente": fuente})

    @app.route("/leads", methods=["POST"])
    def save_lead():
        data = request.json or {}
        c = get_db()
        c.execute(
            "INSERT INTO leads (name,contact,message) VALUES (?,?,?)",
            (data.get("name"), data.get("contact"), data.get("message", ""))
        )
        c.commit()
        c.close()
        log_event("CLIENT", "lead", {"name": data.get("name")})
        return jsonify({"ok": True})

    @app.route("/leads", methods=["GET"])
    def get_leads():
        c = get_db()
        rows = c.execute("SELECT * FROM leads ORDER BY ts DESC LIMIT 100").fetchall()
        c.close()
        return jsonify({"leads": [dict(r) for r in rows], "count": len(rows)})

    @app.route("/nodes")
    def get_nodes():
        c = get_db()
        rows = c.execute("SELECT * FROM nodes ORDER BY port").fetchall()
        c.close()
        return jsonify({"nodes": [dict(r) for r in rows]})

    @app.route("/experiments", methods=["GET"])
    def get_experiments():
        c = get_db()
        rows = c.execute("SELECT * FROM experiments ORDER BY ts DESC LIMIT 50").fetchall()
        c.close()
        return jsonify({"experiments": [dict(r) for r in rows]})

    @app.route("/experiments", methods=["POST"])
    def save_experiment():
        data = request.json or {}
        c = get_db()
        c.execute(
            "INSERT INTO experiments (name,description) VALUES (?,?)",
            (data.get("name"), data.get("description", ""))
        )
        c.commit()
        c.close()
        return jsonify({"ok": True})

    @app.route("/master", methods=["GET"])
    def get_master():
        if MASTER.exists():
            return Response(MASTER.read_text(encoding="utf-8"), mimetype="text/markdown")
        return jsonify({"error": "MASTER.md no encontrado"}), 404

    @app.route("/master", methods=["POST"])
    def update_master():
        data = request.json or {}
        append_master(data.get("section", "GENERAL"), data.get("content", ""))
        return jsonify({"ok": True, "ts": datetime.now().isoformat()})

    @app.route("/status")
    def status():
        c = get_db()
        mem   = c.execute("SELECT COUNT(*) as n FROM memory WHERE archived=0").fetchone()["n"]
        msgs  = c.execute("SELECT COUNT(*) as n FROM chat_history").fetchone()["n"]
        ing   = c.execute("SELECT SUM(monto) as t FROM ingresos").fetchone()["t"] or 0
        exp   = c.execute("SELECT COUNT(*) as n FROM experiments").fetchone()["n"]
        leads = c.execute("SELECT COUNT(*) as n FROM leads").fetchone()["n"]
        c.close()
        return jsonify({
            "node": node_id.upper() + "-001",
            "name": node["name"],
            "version": VERSION,
            "cell": CELL,
            "status": "running",
            "uptime_s": round(time.time() - START, 2),
            "db": str(DB_PATH),
            "memory_items": mem,
            "chat_messages": msgs,
            "ingresos_total": ing,
            "experiments": exp,
            "leads": leads,
            "claude": ANTHROPIC_AVAILABLE and bool(os.environ.get("ANTHROPIC_API_KEY")),
            "ts": datetime.now().isoformat(),
            "principles": ["append-only", "MASTER.md manda", "kernel inmutable",
                           "control humano final", "offline-first"]
        })

    @app.route("/broadcast", methods=["POST"])
    def broadcast():
        data = request.json or {}
        log_event("NEXUS", "broadcast", {"msg": data.get("message", ""), "targets": data.get("targets", [])})
        return jsonify({"ok": True, "ts": datetime.now().isoformat()})

    @app.route("/analyze", methods=["POST"])
    def analyze():
        data   = request.json or {}
        prompt = data.get("prompt", "")
        agent  = data.get("agent", "aurora")
        system = AGENT_SYS.get(agent, ACHE_SYSTEM)
        text, error = call_claude([{"role": "user", "content": prompt}], system=system)
        if error:
            return jsonify({"error": error}), 500
        c = get_db()
        c.execute(
            "INSERT INTO memory (node,type,name,content,tags) VALUES (?,?,?,?,?)",
            (node_id.upper(), "analysis", "Analisis: " + prompt[:40], text, '["analysis"]')
        )
        c.commit()
        c.close()
        return jsonify({"result": text, "ts": datetime.now().isoformat()})

    return app

def run_node(node_id):
    node = NODES[node_id]
    app  = create_app(node_id)
    import logging
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    print("  " + node["icon"] + "  " + node["name"] + " -> http://localhost:" + str(node["port"]))
    app.run(host="0.0.0.0", port=node["port"], debug=False, use_reloader=False)

def run_all():
    import socket
    try:
        ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        ip = "desconocida"

    claude_ok = ANTHROPIC_AVAILABLE and bool(os.environ.get("ANTHROPIC_API_KEY"))

    print("")
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  ACHE NEXUS BRIDGE v2.0 - VERSION DEFINITIVA                ║")
    print("║  GONZAGA-CBM-Omega-001 - La Cruz, Guanacaste, CR            ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print("")
    print("  Claude: " + ("DISPONIBLE" if claude_ok else "Sin API key - modo demo"))
    print("  DB:     " + str(DB_PATH))
    print("  IP red: http://" + ip + ":9000")
    print("")
    print("  Iniciando 7 nodos...")
    print("")

    init_db()
    create_master()
    append_master("BOOT v2.0", "Sistema iniciado. Claude: " + str(claude_ok) + ". IP: " + ip)

    threads = []
    for nid in NODES:
        t = threading.Thread(target=run_node, args=(nid,), daemon=True)
        t.start()
        threads.append(t)
        time.sleep(0.15)

    print("")
    print("  OK - 7 nodos activos. Red ACHE online.")
    print("  Status:  http://localhost:9000/status")
    print("  Chat:    http://localhost:9000/chat")
    print("  Master:  http://localhost:9000/master")
    print("  DB:      " + str(DB_PATH))
    print("")
    print("  Presiona Ctrl+C para detener.")
    print("")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[ACHE] Red detenida. Datos guardados en ache_memory.db")

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="ACHE NEXUS Bridge v2.0")
    p.add_argument("--node", choices=list(NODES.keys()), help="Nodo especifico")
    p.add_argument("--init", action="store_true", help="Solo inicializar DB")
    args = p.parse_args()

    if args.init:
        init_db()
        create_master()
        print("[ACHE] Inicializacion completa.")
    elif args.node:
        init_db()
        create_master()
        run_node(args.node)
    else:
        run_all()
