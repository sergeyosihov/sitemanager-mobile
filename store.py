# -*- coding: utf-8 -*-
# store.py — слой данных SiteManager Mobile. Схема базы совместима с ПК-версией.
import os, re, json, sqlite3, shutil
from datetime import datetime

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "sitemanager.db")

CHK_STATUSES = ["Не приступали", "В работе", "Выполнено", "На паузе",
                "Завершено", "Не в зоне ответственности"]
ORDER_STATUSES = ["не заказано", "заказано, не оплачено", "заказано, оплачено", "доставлено"]

CREATE_SQL = {
    "objects": ("CREATE TABLE objects (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "name TEXT NOT NULL, position INTEGER NOT NULL DEFAULT 0)"),
    "projects": ("CREATE TABLE projects (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                 "object_id INTEGER NOT NULL REFERENCES objects(id) ON DELETE CASCADE, "
                 "name TEXT NOT NULL, comment TEXT NOT NULL DEFAULT '', "
                 "position INTEGER NOT NULL DEFAULT 0)"),
    "pdf_files": ("CREATE TABLE pdf_files (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                  "project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE, "
                  "title TEXT NOT NULL, path TEXT NOT NULL, added TEXT NOT NULL DEFAULT '', "
                  "is_actual INTEGER NOT NULL DEFAULT 0, comment TEXT NOT NULL DEFAULT '')"),
    "spec_columns": ("CREATE TABLE spec_columns (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                     "project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE, "
                     "name TEXT NOT NULL, position INTEGER NOT NULL DEFAULT 0, "
                     "width INTEGER NOT NULL DEFAULT 120)"),
    "spec_rows": ("CREATE TABLE spec_rows (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                  "project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE, "
                  "position INTEGER NOT NULL DEFAULT 0)"),
    "spec_cells": ("CREATE TABLE spec_cells (row_id INTEGER NOT NULL REFERENCES spec_rows(id) "
                   "ON DELETE CASCADE, col_id INTEGER NOT NULL REFERENCES spec_columns(id) "
                   "ON DELETE CASCADE, value TEXT NOT NULL DEFAULT '', PRIMARY KEY (row_id, col_id))"),
    "orders": ("CREATE TABLE orders (id INTEGER PRIMARY KEY AUTOINCREMENT, "
               "project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE, "
               "order_no TEXT NOT NULL DEFAULT '', name TEXT NOT NULL DEFAULT '', "
               "status TEXT NOT NULL DEFAULT '', company TEXT NOT NULL DEFAULT '', "
               "creator TEXT NOT NULL DEFAULT '', created TEXT NOT NULL DEFAULT '', "
               "approved TEXT NOT NULL DEFAULT '', delivery_date TEXT NOT NULL DEFAULT '', "
               "region TEXT NOT NULL DEFAULT '', project_name TEXT NOT NULL DEFAULT '', "
               "address TEXT NOT NULL DEFAULT '', inn TEXT NOT NULL DEFAULT '', "
               "need_delivery TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '', "
               "email TEXT NOT NULL DEFAULT '', details TEXT NOT NULL DEFAULT '', "
               "path TEXT NOT NULL DEFAULT '')"),
    "order_items": ("CREATE TABLE order_items (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                    "order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE, "
                    "pos INTEGER NOT NULL DEFAULT 0, code TEXT NOT NULL DEFAULT '', "
                    "goods TEXT NOT NULL DEFAULT '', qty TEXT NOT NULL DEFAULT '', "
                    "unit TEXT NOT NULL DEFAULT '', category TEXT NOT NULL DEFAULT '', "
                    "cost_item TEXT NOT NULL DEFAULT '', comment_in TEXT NOT NULL DEFAULT '', "
                    "comment_out TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'не заказано')"),
    "memos": ("CREATE TABLE memos (id INTEGER PRIMARY KEY AUTOINCREMENT, "
              "object_id INTEGER NOT NULL REFERENCES objects(id) ON DELETE CASCADE, "
              "title TEXT NOT NULL DEFAULT '', to_whom TEXT NOT NULL DEFAULT '', "
              "subject TEXT NOT NULL DEFAULT '', created TEXT NOT NULL DEFAULT '', "
              "path TEXT NOT NULL DEFAULT '')"),
    "contractors": ("CREATE TABLE contractors (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                    "object_id INTEGER NOT NULL REFERENCES objects(id) ON DELETE CASCADE, "
                    "name TEXT NOT NULL, comment TEXT NOT NULL DEFAULT '', "
                    "position INTEGER NOT NULL DEFAULT 0)"),
    "ks2_docs": ("CREATE TABLE ks2_docs (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                 "contractor_id INTEGER NOT NULL REFERENCES contractors(id) ON DELETE CASCADE, "
                 "doc_no TEXT NOT NULL DEFAULT '', doc_date TEXT NOT NULL DEFAULT '', "
                 "comment TEXT NOT NULL DEFAULT '', sections TEXT NOT NULL DEFAULT '', "
                 "period_from TEXT NOT NULL DEFAULT '', period_to TEXT NOT NULL DEFAULT '', "
                 "path TEXT NOT NULL DEFAULT '')"),
    "ks2_items": ("CREATE TABLE ks2_items (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                  "doc_id INTEGER NOT NULL REFERENCES ks2_docs(id) ON DELETE CASCADE, "
                  "pos INTEGER NOT NULL DEFAULT 0, name TEXT NOT NULL DEFAULT '', "
                  "unit TEXT NOT NULL DEFAULT '', qty TEXT NOT NULL DEFAULT '', "
                  "price TEXT NOT NULL DEFAULT '', total TEXT NOT NULL DEFAULT '', "
                  "section TEXT NOT NULL DEFAULT '')"),
    "warehouse_items": ("CREATE TABLE warehouse_items (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                        "name TEXT NOT NULL DEFAULT '', unit TEXT NOT NULL DEFAULT '', "
                        "qty TEXT NOT NULL DEFAULT '', cell TEXT NOT NULL DEFAULT '', "
                        "source TEXT NOT NULL DEFAULT '', loaded TEXT NOT NULL DEFAULT '')"),
    "moves": ("CREATE TABLE moves (id INTEGER PRIMARY KEY AUTOINCREMENT, "
              "object_id INTEGER NOT NULL REFERENCES objects(id) ON DELETE CASCADE, "
              "wh_id INTEGER NOT NULL DEFAULT 0, name TEXT NOT NULL DEFAULT '', "
              "unit TEXT NOT NULL DEFAULT '', qty TEXT NOT NULL DEFAULT '', "
              "cell TEXT NOT NULL DEFAULT '', project TEXT NOT NULL DEFAULT '', "
              "spec_text TEXT NOT NULL DEFAULT '', created TEXT NOT NULL DEFAULT '')"),
    "settings": ("CREATE TABLE settings (key TEXT PRIMARY KEY, "
                 "value TEXT NOT NULL DEFAULT '')"),
    "service_files": ("CREATE TABLE service_files (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                      "object_id INTEGER REFERENCES objects(id) ON DELETE CASCADE, "
                      "title TEXT NOT NULL DEFAULT '', category TEXT NOT NULL DEFAULT 'Прочее', "
                      "login TEXT NOT NULL DEFAULT '', password TEXT NOT NULL DEFAULT '', "
                      "note TEXT NOT NULL DEFAULT '', path TEXT NOT NULL DEFAULT '', "
                      "added TEXT NOT NULL DEFAULT '')"),
    "order_spec_links": ("CREATE TABLE order_spec_links (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                         "order_item_id INTEGER NOT NULL REFERENCES order_items(id) ON DELETE CASCADE, "
                         "row_id INTEGER NOT NULL REFERENCES spec_rows(id) ON DELETE CASCADE)"),
    "checklists": ("CREATE TABLE checklists (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                   "object_id INTEGER NOT NULL REFERENCES objects(id) ON DELETE CASCADE, "
                   "role TEXT NOT NULL DEFAULT '', week TEXT NOT NULL DEFAULT '', "
                   "data TEXT NOT NULL DEFAULT '', updated TEXT NOT NULL DEFAULT '')"),
    "checklist_templates": ("CREATE TABLE checklist_templates (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                            "object_id INTEGER NOT NULL REFERENCES objects(id) ON DELETE CASCADE, "
                            "role TEXT NOT NULL DEFAULT '', data TEXT NOT NULL DEFAULT '', "
                            "updated TEXT NOT NULL DEFAULT '')"),
}


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn):
    for t, sql in CREATE_SQL.items():
        conn.execute(sql.replace("CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ", 1))
    conn.commit()


def get_setting(conn, key, default=""):
    try:
        r = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        if r is not None and r["value"] is not None:
            return r["value"]
    except Exception:
        pass
    return default


def set_setting(conn, key, value):
    conn.execute("INSERT INTO settings(key, value) VALUES (?, ?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
    conn.commit()


# ---------- объекты / проекты ----------

def objects_list(conn):
    return [dict(r) for r in conn.execute("SELECT * FROM objects ORDER BY position, id")]


def objects_add(conn, name):
    cur = conn.execute("INSERT INTO objects(name, position) VALUES (?, ?)", (name, 0))
    conn.commit()
    return cur.lastrowid


def objects_rename(conn, oid, name):
    conn.execute("UPDATE objects SET name=? WHERE id=?", (name, oid)); conn.commit()


def objects_delete(conn, oid):
    conn.execute("DELETE FROM objects WHERE id=?", (oid,)); conn.commit()


def projects_list(conn, oid):
    return [dict(r) for r in conn.execute(
        "SELECT * FROM projects WHERE object_id=? ORDER BY position, id", (oid,))]


def projects_add(conn, oid, name, comment=""):
    cur = conn.execute("INSERT INTO projects(object_id, name, comment) VALUES (?, ?, ?)",
                       (oid, name, comment))
    conn.commit()
    return cur.lastrowid


def projects_rename(conn, pid, name):
    conn.execute("UPDATE projects SET name=? WHERE id=?", (name, pid)); conn.commit()


def projects_delete(conn, pid):
    conn.execute("DELETE FROM projects WHERE id=?", (pid,)); conn.commit()


# ---------- спецификация ----------

def spec_columns(conn, pid):
    return [dict(r) for r in conn.execute(
        "SELECT * FROM spec_columns WHERE project_id=? ORDER BY position, id", (pid,))]


def spec_rows(conn, pid):
    return [dict(r) for r in conn.execute(
        "SELECT * FROM spec_rows WHERE project_id=? ORDER BY position, id", (pid,))]


def spec_grid(conn, pid):
    cols = spec_columns(conn, pid)
    rows = spec_rows(conn, pid)
    cells = {}
    for r in conn.execute(
            "SELECT c.row_id, c.col_id, c.value FROM spec_cells c "
            "JOIN spec_rows s ON s.id=c.row_id WHERE s.project_id=?", (pid,)):
        cells.setdefault(r["row_id"], {})[r["col_id"]] = r["value"]
    return cols, rows, cells


def spec_cell_set(conn, row_id, col_id, value):
    conn.execute("INSERT INTO spec_cells(row_id, col_id, value) VALUES (?, ?, ?) "
                 "ON CONFLICT(row_id, col_id) DO UPDATE SET value=excluded.value",
                 (row_id, col_id, value))
    conn.commit()


def spec_add_row(conn, pid, pos=None):
    if pos is None:
        r = conn.execute("SELECT COALESCE(MAX(position), -1) FROM spec_rows "
                         "WHERE project_id=?", (pid,)).fetchone()
        pos = (r[0] or -1) + 1
    cur = conn.execute("INSERT INTO spec_rows(project_id, position) VALUES (?, ?)", (pid, pos))
    conn.commit()
    return cur.lastrowid


def spec_add_column(conn, pid, name="Новая", pos=None):
    if pos is None:
        r = conn.execute("SELECT COALESCE(MAX(position), -1) FROM spec_columns "
                         "WHERE project_id=?", (pid,)).fetchone()
        pos = (r[0] or -1) + 1
    cur = conn.execute("INSERT INTO spec_columns(project_id, name, position) VALUES (?, ?, ?)",
                       (pid, name, pos))
    conn.commit()
    return cur.lastrowid


def spec_delete_rows(conn, row_ids):
    for rid in row_ids:
        conn.execute("DELETE FROM spec_cells WHERE row_id=?", (rid,))
        conn.execute("DELETE FROM spec_rows WHERE id=?", (rid,))
    conn.commit()


# ---------- PDF ----------

def pdf_list(conn, pid):
    return [dict(r) for r in conn.execute(
        "SELECT * FROM pdf_files WHERE project_id=? ORDER BY is_actual DESC, id", (pid,))]


def pdf_set_actual(conn, project_id, pdf_id):
    conn.execute("UPDATE pdf_files SET is_actual=0 WHERE project_id=?", (project_id,))
    conn.execute("UPDATE pdf_files SET is_actual=1 WHERE id=?", (pdf_id,))
    conn.commit()


def pdf_set_comment(conn, pdf_id, comment):
    conn.execute("UPDATE pdf_files SET comment=? WHERE id=?", (comment, pdf_id))
    conn.commit()


def pdf_delete(conn, pdf_id):
    conn.execute("DELETE FROM pdf_files WHERE id=?", (pdf_id,)); conn.commit()


# ---------- заявки ----------

def orders_list(conn, pid=None, object_id=None):
    if pid is not None:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM orders WHERE project_id=? ORDER BY id", (pid,))]
    if object_id is not None:
        return [dict(r) for r in conn.execute(
            "SELECT o.* FROM orders o JOIN projects p ON p.id=o.project_id "
            "WHERE p.object_id=? ORDER BY o.id", (object_id,))]
    return [dict(r) for r in conn.execute("SELECT * FROM orders ORDER BY id")]


def order_items_list(conn, order_id):
    return [dict(r) for r in conn.execute(
        "SELECT * FROM order_items WHERE order_id=? ORDER BY pos, id", (order_id,))]


def order_item_set_status(conn, item_id, status):
    conn.execute("UPDATE order_items SET status=? WHERE id=?", (status, item_id))
    conn.commit()


# ---------- подрядчики / КС-2 ----------

def contractors_list(conn, oid):
    return [dict(r) for r in conn.execute(
        "SELECT * FROM contractors WHERE object_id=? ORDER BY position, id", (oid,))]


def contractors_add(conn, oid, name, comment=""):
    cur = conn.execute("INSERT INTO contractors(object_id, name, comment) VALUES (?, ?, ?)",
                       (oid, name, comment))
    conn.commit()
    return cur.lastrowid


def contractors_rename(conn, cid, name):
    conn.execute("UPDATE contractors SET name=? WHERE id=?", (name, cid)); conn.commit()


def contractors_delete(conn, cid):
    conn.execute("DELETE FROM contractors WHERE id=?", (cid,)); conn.commit()


def ks2_docs_list(conn, contractor_id):
    return [dict(r) for r in conn.execute(
        "SELECT * FROM ks2_docs WHERE contractor_id=? ORDER BY doc_date, id", (contractor_id,))]


def ks2_doc_get(conn, doc_id):
    r = conn.execute("SELECT * FROM ks2_docs WHERE id=?", (doc_id,)).fetchone()
    return dict(r) if r else None


def ks2_doc_set_comment(conn, doc_id, comment):
    conn.execute("UPDATE ks2_docs SET comment=? WHERE id=?", (comment, doc_id))
    conn.commit()


def ks2_items_list(conn, doc_id):
    return [dict(r) for r in conn.execute(
        "SELECT * FROM ks2_items WHERE doc_id=? ORDER BY pos, id", (doc_id,))]


def ks2_doc_add(conn, contractor_id, doc_no, doc_date, comment, sections,
                period_from, period_to, path):
    cur = conn.execute(
        "INSERT INTO ks2_docs(contractor_id, doc_no, doc_date, comment, sections, "
        "period_from, period_to, path) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (contractor_id, doc_no, doc_date, comment, sections, period_from, period_to, path))
    conn.commit()
    return cur.lastrowid


# ---------- записки ----------

def memos_list(conn, oid):
    return [dict(r) for r in conn.execute(
        "SELECT * FROM memos WHERE object_id=? ORDER BY id DESC", (oid,))]


# ---------- склад ----------

def warehouse_items_list(conn):
    out = []
    for r in conn.execute("SELECT * FROM warehouse_items ORDER BY id"):
        d = dict(r)
        if not d.get("source"):
            d["source"] = d.get("cell", "")
        out.append(d)
    return out


def warehouse_clear(conn):
    conn.execute("DELETE FROM warehouse_items"); conn.commit()


def warehouse_import(conn, items):
    stamp = datetime.now().strftime("%d.%m.%Y %H:%M")
    conn.execute("DELETE FROM warehouse_items")
    for it in items:
        conn.execute("INSERT INTO warehouse_items(name, unit, qty, cell, loaded) "
                     "VALUES (?, ?, ?, ?, ?)",
                     (it[0], it[1], it[2], it[3] if len(it) > 3 else "", stamp))
    conn.commit()
    return len(items)


def _fuzzy_score(query, name):
    q = re.sub(r"\s+", " ", str(query or "")).strip().lower()
    n = re.sub(r"\s+", " ", str(name or "")).strip().lower()
    if not q or not n:
        return 0.0
    if q == n:
        return 100.0
    if q in n:
        return 90.0
    qw, nw = q.split(), n.split()
    qset, nset = set(qw), set(nw)
    inter = qset & nset
    score = 0.0
    if qset and nset:
        score += 60.0 * len(inter) / len(qset)
    qw2 = [w for w in qw if w not in inter]
    nw2 = [w for w in nw if w not in inter]
    if qw2:
        part = 0
        for w in qw2:
            hit = False
            for v in nw2:
                if len(w) >= 3 and (v.startswith(w[:4]) or w.startswith(v[:4])):
                    hit = True
                    break
                if re.fullmatch(r"\d+", w):
                    nums = re.findall(r"\d+", v)
                    if w in nums:
                        hit = True
                        break
            if hit:
                part += 1
        score += 40.0 * part / len(qw2)
    return score


def warehouse_matches_fuzzy(conn, text, limit=8, min_score=40.0):
    out = []
    for it in warehouse_items_list(conn):
        sc = _fuzzy_score(text, it["name"])
        if sc >= min_score:
            out.append((sc, it))
    out.sort(key=lambda x: -x[0])
    return out[:limit]


def moves_list(conn, object_id):
    return [dict(r) for r in conn.execute(
        "SELECT * FROM moves WHERE object_id=? ORDER BY id", (object_id,))]


def moves_add(conn, object_id, items):
    stamp = datetime.now().strftime("%d.%m.%Y %H:%M")
    for it in items:
        conn.execute(
            "INSERT INTO moves(object_id, wh_id, name, unit, qty, cell, project, spec_text, "
            "created) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (object_id, it.get("wh_id", 0), it.get("name", ""), it.get("unit", ""),
             it.get("qty", ""), it.get("cell", ""), it.get("project", ""),
             it.get("spec_text", ""), stamp))
    conn.commit()
    return len(items)


# ---------- чек-лист ----------

def _norm_role(role):
    r = (role or "").strip().upper()
    if r.startswith("АДИ") or r in ("ADIS", "A"):
        return "ADIS"
    if r.startswith("СС") or r in ("CC", "SC", "C"):
        return "CC"
    return r or "CC"


def week_key(dt=None):
    d = dt or datetime.now()
    iso = d.isocalendar()
    return "%d-Нед%02d" % (iso[0], iso[2])


def chk_template(conn, oid, role):
    role = _norm_role(role)
    r = conn.execute("SELECT data FROM checklist_templates WHERE object_id=? AND role=?",
                     (oid, role)).fetchone()
    if r:
        try:
            return json.loads(r["data"])
        except Exception:
            pass
    return {"secs": []}


def chk_template_save(conn, oid, role, template):
    role = _norm_role(role)
    conn.execute("DELETE FROM checklist_templates WHERE object_id=? AND role=?", (oid, role))
    conn.execute("INSERT INTO checklist_templates(object_id, role, data, updated) "
                 "VALUES (?, ?, ?, ?)",
                 (oid, role, json.dumps(template, ensure_ascii=False),
                  datetime.now().strftime("%d.%m.%Y %H:%M")))
    conn.commit()


def chk_week(conn, oid, role, week):
    role = _norm_role(role)
    r = conn.execute("SELECT data FROM checklists WHERE object_id=? AND role=? AND week=?",
                     (oid, role, week)).fetchone()
    if r:
        try:
            return json.loads(r["data"])
        except Exception:
            pass
    return {"meta": {}, "items": {}}


def chk_week_save(conn, oid, role, week, data):
    role = _norm_role(role)
    conn.execute("DELETE FROM checklists WHERE object_id=? AND role=? AND week=?",
                 (oid, role, week))
    conn.execute("INSERT INTO checklists(object_id, role, week, data, updated) "
                 "VALUES (?, ?, ?, ?, ?)",
                 (oid, role, week, json.dumps(data, ensure_ascii=False),
                  datetime.now().strftime("%d.%m.%Y %H:%M")))
    conn.commit()


def chk_key(sec_name, item_name):
    return "%s :: %s" % (sec_name, item_name)


def chk_fill_week(conn, oid, role, week):
    tmpl = chk_template(conn, oid, role)
    prev = chk_week(conn, oid, role, week)
    items = dict(prev.get("items", {}))
    for sec in tmpl.get("secs", []):
        for it in sec.get("items", []):
            k = chk_key(sec.get("name", ""), it.get("name", ""))
            if k not in items:
                items[k] = {"status": "Не приступали", "pct": 0, "date": "",
                            "problem": "", "orders": "", "comment": ""}
    chk_week_save(conn, oid, role, week, {"meta": prev.get("meta", {}), "items": items})


def chk_set_item(conn, oid, role, week, sec_name, item_name, field, value):
    data = chk_week(conn, oid, role, week)
    items = data.setdefault("items", {})
    k = chk_key(sec_name, item_name)
    rec = items.setdefault(k, {"status": "Не приступали", "pct": 0, "date": "",
                               "problem": "", "orders": "", "comment": ""})
    if field == "status":
        st = str(value)
        if st in ("Выполнено", "Завершено"):
            rec["pct"] = 100
    rec[field] = value
    chk_week_save(conn, oid, role, week, data)


def chk_template_rename_item(conn, oid, role, sec_name, old_name, new_name):
    tmpl = chk_template(conn, oid, role)
    for sec in tmpl.get("secs", []):
        if sec.get("name", "") == sec_name:
            for it in sec.get("items", []):
                if it.get("name", "") == old_name:
                    it["name"] = new_name
    chk_template_save(conn, oid, role, tmpl)
    old_k, new_k = chk_key(sec_name, old_name), chk_key(sec_name, new_name)
    for r in conn.execute("SELECT id, week, data FROM checklists WHERE object_id=? AND role=?",
                          (oid, _norm_role(role))).fetchall():
        try:
            data = json.loads(r["data"])
        except Exception:
            continue
        if old_k in data.get("items", {}):
            data["items"][new_k] = data["items"].pop(old_k)
            conn.execute("UPDATE checklists SET data=? WHERE id=?",
                         (json.dumps(data, ensure_ascii=False), r["id"]))
    conn.commit()


# ---------- глобальный поиск ----------

def search(conn, query, limit=20):
    q = (query or "").strip().lower()
    if not q:
        return []
    res = []

    def add(kind, title, oid=None, pid=None, extra=""):
        res.append({"kind": kind, "title": title, "object_id": oid,
                    "project_id": pid, "extra": extra})

    for r in conn.execute("SELECT id, name FROM objects"):
        if q in (r["name"] or "").lower():
            add("Объект", r["name"], oid=r["id"])
    for r in conn.execute("SELECT id, object_id, name FROM projects"):
        if q in (r["name"] or "").lower():
            add("Проект", r["name"], oid=r["object_id"], pid=r["id"])
    # SQLite LIKE не работает с кириллицей без учёта регистра — фильтруем в Python
    cnt = 0
    for r in conn.execute(
            "SELECT c.row_id, c.value, s.project_id FROM spec_cells c "
            "JOIN spec_rows s ON s.id=c.row_id LIMIT 500"):
        if q not in (r["value"] or "").lower():
            continue
        p = conn.execute("SELECT object_id FROM projects WHERE id=?",
                         (r["project_id"],)).fetchone()
        add("Спецификация", (r["value"] or "")[:80], oid=p["object_id"] if p else None,
            pid=r["project_id"])
        cnt += 1
        if cnt >= limit // 2:
            break
    for r in conn.execute("SELECT id, order_no, name FROM orders"):
        if q in (r["order_no"] or "").lower() or q in (r["name"] or "").lower():
            add("Заявка", "№%s %s" % (r["order_no"], r["name"]), pid=r["id"])
    for r in conn.execute("SELECT id, object_id, name FROM contractors"):
        if q in (r["name"] or "").lower():
            add("Подрядчик", r["name"], oid=r["object_id"])
    for r in conn.execute("SELECT id, object_id, title, subject FROM memos"):
        if q in (r["title"] or "").lower() or q in (r["subject"] or "").lower():
            add("Записка", "%s %s" % (r["title"], r["subject"]), oid=r["object_id"])
    for r in conn.execute("SELECT id, name, qty FROM warehouse_items"):
        if q in (r["name"] or "").lower():
            add("Склад", "%s (%s)" % (r["name"], r["qty"]))
    return res[:limit]


# ---------- PIN-код ----------
import hashlib

def _pin_hash(pin):
    salt = "sitemanager-v1"
    return hashlib.sha256((salt + pin).encode()).hexdigest()


def get_pin():
    conn = None
    try:
        conn = connect()
        return get_setting(conn, "pin_hash", "")
    finally:
        if conn:
            conn.close()


def set_pin(pin):
    conn = connect()
    try:
        set_setting(conn, "pin_hash", _pin_hash(pin))
    finally:
        conn.close()


def check_pin(pin):
    return get_pin() == _pin_hash(pin)
