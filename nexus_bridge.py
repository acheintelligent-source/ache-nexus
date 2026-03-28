#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║  NEXUS BRIDGE v1.0 — Servidor Local ACHE                ║
║  GONZAGA-CBM-Ω-001 · La Cruz, Guanacaste, CR            ║
║  Conecta: GONZAGA:8080 · NEXUS:9000 · EVA:5000          ║
║           MONEY:3000 · NEPTUNO:8090                     ║
╚══════════════════════════════════════════════════════════╝

INSTALACIÓN RÁPIDA:
  pip install flask flask-cors requests

CORRER TODOS LOS NODOS EN PARALELO:
  python nexus_bridge.py --all

CORRER UN NODO ESPECÍFICO:
  python nexus_bridge.py --node gonzaga
  python nexus_bridge.py --node nexus
  python nexus_bridge.py --node eva

AUTOR: ACHE OS · COOPECRUCENOS R.L.
PRINCIPIO: append-only · MASTER.md manda · kernel inmutable
"""

import sys
import json
import time
import hashlib
import sqlite3
import threading
import argparse
import os
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, Response
from flask_cors import CORS

# ── CONFIGURACIÓN GLOBAL ──────────────────────────────────
BASE_DIR = Path(__file__).parent
DB_PATH  = BASE_DIR / "ache_memory.db"
LOG_PATH = BASE_DIR / "ache_log.jsonl"

NODES = {
    "gonzaga": {"port": 8080, "name": "ACHE SUPREMO v5",    "icon": "⚡"},
    "nexus":   {"port": 9000, "name": "ACHE NEXUS v2.0",    "icon": "🧠"},
    "aurora":  {"port": 7777, "name": "AURORA v1.0",         "icon": "🌌"},
    "money":   {"port": 3000, "name": "ACHE MONEY v1.0",    "icon": "💰"},
    "mobile":  {"port": 3002, "name": "ACHE Mobile PWA",    "icon": "📱"},  # resuelto conflicto
    "neptuno": {"port": 8090, "name": "ACHE NEPTUNO α",     "icon": "🌊"},
    "eva":     {"port": 5000, "name": "ACHE EVA v1.0",      "icon": "🔬"},
}

START_TIME = time.time()

# ── DATABASE (append-only, SQLite) ────────────────────────
def init_db():
    """Inicializa la base de datos ACHE. Append-only por principio."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Memoria principal
    c.execute("""CREATE TABLE IF NOT EXISTS memory (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        ts        REAL    NOT NULL DEFAULT (unixepoch('now','subsec')),
        node      TEXT    NOT NULL DEFAULT 'NEXUS',
        type      TEXT    NOT NULL DEFAULT 'note',
        name      TEXT    NOT NULL,
        content   TEXT,
        tags      TEXT,
        hash      TEXT,
        archived  INTEGER NOT NULL DEFAULT 0
    )""")

    # Mensajes de chat (historial permanente)
    c.execute("""CREATE TABLE IF NOT EXISTS chat_history (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        ts        REAL    NOT NULL DEFAULT (unixepoch('now','subsec')),
        session   TEXT    NOT NULL,
        role      TEXT    NOT NULL,
        content   TEXT    NOT NULL,
        node      TEXT    NOT NULL DEFAULT 'AURORA',
        tokens    INTEGER DEFAULT 0
    )""")

    # Ingresos COOPECRUCENOS
    c.execute("""CREATE TABLE IF NOT EXISTS ingresos (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        ts        REAL    NOT NULL DEFAULT (unixepoch('now','subsec')),
        monto     REAL    NOT NULL,
        fuente    TEXT    NOT NULL,
        nota      TEXT,
        moneda    TEXT    NOT NULL DEFAULT 'CRC'
    )""")

    # Nodos de la red
    c.execute("""CREATE TABLE IF NOT EXISTS nodes (
        id        TEXT    PRIMARY KEY,
        name      TEXT    NOT NULL,
        icon      TEXT    DEFAULT '🔗',
        port      INTEGER NOT NULL,
        status    TEXT    NOT NULL DEFAULT 'standby',
        location  TEXT,
        last_seen REAL
    )""")

    # Experimentos del operador
    c.execute("""CREATE TABLE IF NOT EXISTS experiments (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        ts        REAL    NOT NULL DEFAULT (unixepoch('now','subsec')),
        name      TEXT    NOT NULL,
        description TEXT,
        status    TEXT    NOT NULL DEFAULT 'active',
        results   TEXT
    )""")

    # Seed de nodos iniciales
    for node_id, node in NODES.items():
        c.execute("""INSERT OR IGNORE INTO nodes (id, name, icon, port, status, location)
                     VALUES (?, ?, ?, ?, 'standby', 'La Cruz, Guanacaste, CR')""",
                  (node_id.upper()+"-001", node["name"], node["icon"], node["port"]))

    conn.commit()
    conn.close()
    print(f"[ACHE DB] Base de datos inicializada: {DB_PATH}")

def db():
    """Conexión a la base de datos."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def log_event(node, event_type, data):
    """Log append-only a JSONL. Nunca se borra."""
    entry = {
        "ts": datetime.now().isoformat(),
        "node": node,
        "type": event_type,
        "data": data,
        "hash": hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]
    }
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

# ── FACTORY DE APPS FLASK ─────────────────────────────────
def create_app(node_id: str) -> Flask:
    """
    Crea una app Flask para un nodo específico.
    Cada nodo tiene su propia identidad pero comparten la DB.
    """
    node = NODES[node_id]
    app = Flask(f"ACHE-{node_id.upper()}")
    CORS(app, origins="*")  # Permite conexión desde ACHE OS browser

    # ── HEALTH ──────────────────────────────────────────
    @app.route("/health")
    @app.route("/")
    def health():
        return jsonify({
            "status":  "running",
            "node":    node_id.upper() + "-001",
            "name":    node["name"],
            "icon":    node["icon"],
            "port":    node["port"],
            "uptime":  round(time.time() - START_TIME, 2),
            "ts":      datetime.now().isoformat(),
            "version": "1.0.0",
            "ache":    "GONZAGA-CBM-Ω-001 · La Cruz, Guanacaste, CR"
        })

    # ── MEMORIA ─────────────────────────────────────────
    @app.route("/memory", methods=["GET"])
    def get_memory():
        limit  = request.args.get("limit", 50, type=int)
        type_f = request.args.get("type")
        conn = db()
        if type_f:
            rows = conn.execute(
                "SELECT * FROM memory WHERE archived=0 AND type=? ORDER BY ts DESC LIMIT ?",
                (type_f, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM memory WHERE archived=0 ORDER BY ts DESC LIMIT ?",
                (limit,)
            ).fetchall()
        conn.close()
        return jsonify({"items": [dict(r) for r in rows], "count": len(rows)})

    @app.route("/memory", methods=["POST"])
    def save_memory():
        data    = request.json or {}
        name    = data.get("name", "Sin nombre")
        content = data.get("content", "")
        mtype   = data.get("type", "note")
        tags    = json.dumps(data.get("tags", []))
        h       = hashlib.sha256(content.encode()).hexdigest()[:16]
        conn = db()
        conn.execute(
            "INSERT INTO memory (node, type, name, content, tags, hash) VALUES (?,?,?,?,?,?)",
            (node_id.upper(), mtype, name, content, tags, h)
        )
        conn.commit()
        conn.close()
        log_event(node_id.upper(), "memory_save", {"name": name, "type": mtype})
        return jsonify({"ok": True, "hash": h, "name": name})

    # ── CHAT HISTORY ────────────────────────────────────
    @app.route("/chat/history", methods=["GET"])
    def chat_history():
        session = request.args.get("session", "default")
        limit   = request.args.get("limit", 30, type=int)
        conn = db()
        rows = conn.execute(
            "SELECT * FROM chat_history WHERE session=? ORDER BY ts DESC LIMIT ?",
            (session, limit)
        ).fetchall()
        conn.close()
        return jsonify({"messages": [dict(r) for r in reversed(rows)]})

    @app.route("/chat/save", methods=["POST"])
    def save_chat():
        data    = request.json or {}
        session = data.get("session", "default")
        role    = data.get("role", "user")
        content = data.get("content", "")
        target  = data.get("node", "AURORA")
        tokens  = data.get("tokens", 0)
        conn = db()
        conn.execute(
            "INSERT INTO chat_history (session, role, content, node, tokens) VALUES (?,?,?,?,?)",
            (session, role, content, target, tokens)
        )
        conn.commit()
        conn.close()
        return jsonify({"ok": True})

    # ── INGRESOS ────────────────────────────────────────
    @app.route("/ingresos", methods=["GET"])
    def get_ingresos():
        conn = db()
        rows = conn.execute(
            "SELECT * FROM ingresos ORDER BY ts DESC LIMIT 200"
        ).fetchall()
        total = conn.execute("SELECT SUM(monto) as t FROM ingresos").fetchone()["t"] or 0
        conn.close()
        return jsonify({"ingresos": [dict(r) for r in rows], "total": total, "moneda": "CRC"})

    @app.route("/ingresos", methods=["POST"])
    def add_ingreso():
        data   = request.json or {}
        monto  = float(data.get("monto", 0))
        fuente = data.get("fuente", "Otro")
        nota   = data.get("nota", "")
        if monto <= 0:
            return jsonify({"error": "Monto debe ser mayor a 0"}), 400
        conn = db()
        conn.execute(
            "INSERT INTO ingresos (monto, fuente, nota) VALUES (?,?,?)",
            (monto, fuente, nota)
        )
        conn.commit()
        conn.close()
        log_event(node_id.upper(), "ingreso", {"monto": monto, "fuente": fuente})
        return jsonify({"ok": True, "monto": monto, "fuente": fuente})

    # ── NODOS ────────────────────────────────────────────
    @app.route("/nodes", methods=["GET"])
    def get_nodes():
        conn = db()
        rows = conn.execute("SELECT * FROM nodes ORDER BY port").fetchall()
        conn.close()
        return jsonify({"nodes": [dict(r) for r in rows]})

    @app.route("/nodes/<node_id_param>/ping", methods=["POST"])
    def ping_node(node_id_param):
        conn = db()
        conn.execute(
            "UPDATE nodes SET status='running', last_seen=? WHERE id=?",
            (time.time(), node_id_param.upper() + "-001")
        )
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "node": node_id_param, "ts": datetime.now().isoformat()})

    # ── BROADCAST ────────────────────────────────────────
    @app.route("/broadcast", methods=["POST"])
    def broadcast():
        data    = request.json or {}
        msg     = data.get("message", "")
        targets = data.get("targets", list(NODES.keys()))
        log_event("NEXUS", "broadcast", {"message": msg, "targets": targets})
        return jsonify({
            "ok":      True,
            "message": msg,
            "targets": targets,
            "ts":      datetime.now().isoformat()
        })

    # ── EXPERIMENTOS (solo NEXUS/GONZAGA) ───────────────
    @app.route("/experiments", methods=["GET"])
    def get_experiments():
        conn = db()
        rows = conn.execute(
            "SELECT * FROM experiments ORDER BY ts DESC LIMIT 50"
        ).fetchall()
        conn.close()
        return jsonify({"experiments": [dict(r) for r in rows]})

    @app.route("/experiments", methods=["POST"])
    def save_experiment():
        data = request.json or {}
        name = data.get("name", "Sin nombre")
        desc = data.get("description", "")
        conn = db()
        conn.execute(
            "INSERT INTO experiments (name, description) VALUES (?,?)",
            (name, desc)
        )
        conn.commit()
        conn.close()
        log_event(node_id.upper(), "experiment", {"name": name})
        return jsonify({"ok": True, "name": name})

    # ── STATUS COMPLETO ──────────────────────────────────
    @app.route("/status", methods=["GET"])
    def status():
        conn = db()
        mem_count = conn.execute("SELECT COUNT(*) as c FROM memory WHERE archived=0").fetchone()["c"]
        ing_total = conn.execute("SELECT SUM(monto) as t FROM ingresos").fetchone()["t"] or 0
        msg_count = conn.execute("SELECT COUNT(*) as c FROM chat_history").fetchone()["c"]
        exp_count = conn.execute("SELECT COUNT(*) as c FROM experiments").fetchone()["c"]
        conn.close()
        return jsonify({
            "node":        node_id.upper() + "-001",
            "name":        node["name"],
            "status":      "running",
            "uptime_s":    round(time.time() - START_TIME, 2),
            "db":          str(DB_PATH),
            "memory_items": mem_count,
            "chat_messages": msg_count,
            "ingresos_total": ing_total,
            "experiments":  exp_count,
            "ts":           datetime.now().isoformat(),
            "principles":   [
                "append-only", "MASTER.md manda", "kernel inmutable",
                "control humano final", "offline-first"
            ]
        })

    # ── MASTER.MD ────────────────────────────────────────
    @app.route("/master", methods=["GET"])
    def get_master():
        master_path = BASE_DIR / "MASTER.md"
        if master_path.exists():
            return Response(master_path.read_text(encoding="utf-8"),
                          mimetype="text/markdown")
        return jsonify({"error": "MASTER.md no encontrado"}), 404

    @app.route("/master", methods=["POST"])
    def update_master():
        """Actualiza MASTER.md — append-only, nunca borra."""
        data    = request.json or {}
        section = data.get("section", "GENERAL")
        content = data.get("content", "")
        master_path = BASE_DIR / "MASTER.md"
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"\n\n## [{ts}] {section}\n{content}\n"
        with open(master_path, "a", encoding="utf-8") as f:
            f.write(entry)
        log_event(node_id.upper(), "master_update", {"section": section})
        return jsonify({"ok": True, "section": section, "ts": ts})

    return app

# ── RUNNER MULTI-NODO ─────────────────────────────────────
def run_node(node_id: str):
    """Corre un nodo en su propio thread."""
    node = NODES[node_id]
    app  = create_app(node_id)
    print(f"  {node['icon']}  {node['name']} → http://localhost:{node['port']}")
    app.run(
        host="0.0.0.0",
        port=node["port"],
        debug=False,
        use_reloader=False
    )

def run_all():
    """Corre todos los nodos en paralelo con threads."""
    print("""
╔══════════════════════════════════════════════════════╗
║  ACHE NEXUS BRIDGE v1.0 — Iniciando red completa    ║
║  GONZAGA-CBM-Ω-001 · La Cruz, Guanacaste, CR        ║
╚══════════════════════════════════════════════════════╝
    """)
    init_db()
    threads = []
    for node_id in NODES:
        t = threading.Thread(target=run_node, args=(node_id,), daemon=True)
        t.start()
        threads.append(t)
        time.sleep(0.2)  # pequeño delay para evitar colisión de logs

    print(f"\n  ✅ {len(NODES)} nodos activos. Red ACHE online.")
    print(f"  📊 Dashboard: http://localhost:9000/status")
    print(f"  📝 MASTER.md: http://localhost:9000/master")
    print(f"  💾 Base de datos: {DB_PATH}")
    print(f"\n  Presiona Ctrl+C para detener todos los nodos.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[ACHE] Red detenida. Los datos persisten en ache_memory.db")

# ── MASTER.MD INICIAL ─────────────────────────────────────
def create_master_md():
    master_path = BASE_DIR / "MASTER.md"
    if not master_path.exists():
        content = f"""# MASTER.md — ACHE OS
*Creado: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}*
*Célula: GONZAGA-CBM-Ω-001 · La Cruz, Guanacaste, CR*

## PRINCIPIOS INVARIANTES
1. append-only — nada se borra, todo se versiona
2. MASTER.md manda — este archivo es la verdad del sistema
3. kernel inmutable — el núcleo no cambia sin consenso
4. control humano final — Cristhian siempre decide
5. offline-first — funciona sin internet
6. sin dependencia única — redundancia en todo
7. evolución por capas — sin romper lo que funciona
8. toda acción deja traza — log siempre
9. capítulos vivos — el sistema aprende
10. ACHE asiste, no reemplaza — el humano manda

## NODOS ACTIVOS
- GONZAGA-CBM-Ω-001 :8080 — Núcleo físico (Ryzen 5 8645HS)
- NEXUS-001 :9000 — Coordinador
- AURORA-001 :7777 — Interfaz principal
- MONEY-001 :3000 — Finanzas
- MOBILE-001 :3002 — PWA (resuelto conflicto)
- NEPTUNO-α :8090 — Plataforma marítima ZEE
- EVA-001 :5000 — Investigación robótica

## PROYECTOS
- NEPTUNO: $256M · ZEE Pacífico CR · Fase 1 23%
- ACHE MONEY: Fintech cooperativa
- Eva: Drones autónomos ROS2/PX4
- ACHE OS: SaaS $10M+

## HISTORIAL DE CAMBIOS
*(append-only — las entradas se agregan abajo automáticamente)*
"""
        master_path.write_text(content, encoding="utf-8")
        print(f"[ACHE] MASTER.md creado: {master_path}")

# ── ENTRY POINT ───────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ACHE NEXUS Bridge")
    parser.add_argument("--all",  action="store_true", help="Corre todos los nodos")
    parser.add_argument("--node", type=str, choices=list(NODES.keys()), help="Nodo específico")
    parser.add_argument("--init", action="store_true", help="Solo inicializa la DB")
    args = parser.parse_args()

    create_master_md()

    if args.init:
        init_db()
        print("[ACHE] Inicialización completa.")
    elif args.node:
        init_db()
        print(f"\n[ACHE] Iniciando nodo: {args.node.upper()}")
        run_node(args.node)
    else:
        # Por defecto corre todo
        run_all()