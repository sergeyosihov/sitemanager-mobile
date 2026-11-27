# -*- coding: utf-8 -*-
# SiteManager Mobile — приложение для Android. Общая база с ПК-версией через Яндекс Диск.
import os, sys, json
from datetime import datetime

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.modalview import ModalView
from kivy.metrics import dp
from kivy.core.clipboard import Clipboard
from kivy.clock import Clock
from kivy.utils import platform

import store
import ydsync

if platform == "android":
    import jnius  # noqa: F401 (импорт для доступности позже)

C_BG = (0.949, 0.949, 0.957, 1)      # светлый фон в стиле системы
C_CARD = (1, 1, 1, 1)
C_ACCENT = (0.263, 0.522, 0.957, 1)  # синий
C_TEXT = (0.1, 0.1, 0.12, 1)
C_OK = (0.30, 0.69, 0.31, 1)
C_WARN = (0.95, 0.61, 0.07, 1)
C_BAD = (0.9, 0.27, 0.21, 1)

def _data_dir(app):
    if platform == "android":
        try:
            return app.user_data_dir or store.APP_DIR
        except Exception:
            return store.APP_DIR
    return store.APP_DIR

def _open_pdf(path):
    """Открывает PDF системным просмотрщиком."""
    if not os.path.exists(path):
        print("[toast] Файл не найден: " + path)
        return
    if platform == "android":
        try:
            from jnius import autoclass
            File = autoclass("java.io.File")
            Uri = autoclass("android.net.Uri")
            Intent = autoclass("android.content.Intent")
            ctx = autoclass("org.kivy.android.PythonActivity").mActivity
            # Сначала пытаемся через FileProvider (требование API 24+),
            # при недоступности — прямой file:// (старые устройства)
            uri = None
            try:
                FileProvider = autoclass("androidx.core.content.FileProvider")
                uri = FileProvider.getUriForFile(
                    ctx, ctx.getPackageName() + ".provider", File(path))
                intent = Intent(Intent.ACTION_VIEW)
                intent.setDataAndType(uri, "application/pdf")
                intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                ctx.startActivity(intent)
                return
            except Exception:
                pass
            uri = Uri.fromFile(File(path))
            intent = Intent(Intent.ACTION_VIEW)
            intent.setDataAndType(uri, "application/pdf")
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            ctx.startActivity(intent)
        except Exception as e:
            print("[toast] Не удалось открыть PDF:", e)
    else:
        try:
            os.startfile(path)  # Windows — для отладки на ПК
        except Exception as e:
            print("[toast] Не удалось открыть PDF:", e)


class Toast:
    _t = None

def _toast(msg):
    print("[toast]", msg)


class Nav:
    """Менеджер экранов: стек с кнопкой назад."""
    def __init__(self, app):
        self.app = app
        self.stack = []

    def push(self, widget, title):
        self.stack.append((widget, title))
        self._render()

    def pop(self, *a):
        if len(self.stack) > 1:
            self.stack.pop()
        self._render()

    def reset(self, widget, title):
        self.stack = [(widget, title)]
        self._render()

    def _render(self):
        self.app.render()


class AppScreen(BoxLayout):
    """Базовый экран: шапка с заголовком и кнопкой назад + контент."""
    def __init__(self, app, title, back=True, **kw):
        super().__init__(orientation="vertical", **kw)
        self.app = app
        bar = BoxLayout(size_hint_y=None, height=dp(52),
                       padding=[dp(8), dp(6)], spacing=dp(8))
        if back:
            bar.add_widget(_btn("←", self._back, width=dp(48), size_hint_x=None))
        bar.add_widget(Label(text=title, font_size=dp(20), bold=True,
                             color=C_TEXT, halign="left", valign="middle",
                             size_hint_x=1))
        self.add_widget(bar)
        self.content = BoxLayout(orientation="vertical", padding=[dp(8), dp(4)])
        self.add_widget(self.content)

    def _back(self, *a):
        self.app.nav.pop()


def _btn(text, on_press=None, **kw):
    kw.setdefault("font_size", dp(16))
    kw.setdefault("size_hint_y", None)
    kw.setdefault("height", dp(48))
    b = Button(text=text, **kw)
    if on_press:
        b.bind(on_press=on_press)
    return b


def _row(text, on_press=None, sub="", color=C_CARD):
    """Строка-карточка списка."""
    lay = BoxLayout(size_hint_y=None, height=dp(52), padding=[dp(12), 0],
                    spacing=dp(8))
    box = BoxLayout(orientation="vertical", padding=[0, dp(6)])
    box.add_widget(Label(text=text, font_size=dp(16), color=C_TEXT,
                         halign="left", valign="middle",
                         text_size=(None, None), size_hint_y=0.6))
    if sub:
        box.add_widget(Label(text=sub, font_size=dp(12),
                             color=(0.45, 0.45, 0.5, 1), halign="left",
                             valign="middle", size_hint_y=0.4))
    lay.add_widget(box)
    card = Button(size_hint_y=None, height=dp(52), background_normal="",
                  background_color=color)
    card.add_widget(lay)
    if on_press:
        card.bind(on_press=on_press)
    return card


def _list_scroll(widgets):
    sv = ScrollView()
    lay = GridLayout(cols=1, size_hint_y=None, spacing=dp(6), padding=[dp(4), dp(4)])
    lay.bind(minimum_height=lay.setter("height"))
    for w in widgets:
        lay.add_widget(w)
    sv.add_widget(lay)
    return sv


class Diag(ModalView):
    """Диалог: заголовок + одно поле ввода + ОК/Отмена."""
    def __init__(self, app, title, value="", on_ok=None, multiline=False, **kw):
        super().__init__(auto_dismiss=True, size_hint=(0.94, None),
                         height=dp(240 if not multiline else 340), **kw)
        self.on_ok = on_ok
        box = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
        box.add_widget(Label(text=title, font_size=dp(18), bold=True, color=C_TEXT))
        self.input = TextInput(text=value, multiline=multiline, font_size=dp(16),
                               size_hint_y=None, height=dp(44 if not multiline else dp(160)))
        box.add_widget(self.input)
        btns = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        btns.add_widget(_btn("Отмена", self.dismiss))
        btns.add_widget(_btn("Сохранить", self._ok, background_color=C_ACCENT,
                             background_normal=""))
        box.add_widget(btns)
        self.add_widget(box)

    def _ok(self, *a):
        self.dismiss()
        if self.on_ok:
            self.on_ok(self.input.text.strip())


class Choice(ModalView):
    """Диалог выбора из списка."""
    def __init__(self, app, title, options, on_pick=None, **kw):
        super().__init__(auto_dismiss=True, size_hint=(0.94, 0.7), **kw)
        self.on_pick = on_pick
        box = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        box.add_widget(Label(text=title, font_size=dp(18), bold=True, color=C_TEXT))
        box.add_widget(_list_scroll([_btn(o, self._pick, halign="center") for o in options]))
        self.options = options
        self.add_widget(box)

    def _pick(self, btn):
        self.dismiss()
        if self.on_pick:
            self.on_pick(btn.text)


class PinScreen(BoxLayout):
    def __init__(self, app, **kw):
        super().__init__(orientation="vertical", padding=dp(40), spacing=dp(16), **kw)
        self.app = app
        self.mode = "create" if not store.get_pin() else "enter"
        title = ("Придумайте PIN-код" if self.mode == "create" else "Введите PIN-код")
        self.info = Label(text=title, font_size=dp(20), bold=True, color=C_TEXT)
        self.input = TextInput(password=True, multiline=False, font_size=dp(24),
                               size_hint_y=None, height=dp(56), halign="center")
        ok = _btn("Войти" if self.mode == "enter" else "Сохранить",
                  self._check, background_color=C_ACCENT, background_normal="")
        self.add_widget(self.info)
        self.add_widget(self.input)
        self.add_widget(ok)

    def _check(self, *a):
        pin = self.input.text.strip()
        if not pin:
            self.info.text = "Введите PIN"
            return
        if self.mode == "create":
            if len(pin) < 4:
                self.info.text = "Минимум 4 символа"
                return
            store.set_pin(pin)
            self.app.enter()
        else:
            if store.check_pin(pin):
                self.app.enter()
            else:
                self.info.text = "Неверный PIN"
                self.input.text = ""


class ObjectsScreen(AppScreen):
    def refresh(self):
        self.content.clear_widgets()
        self.content.add_widget(_btn("+ Объект", self._add, background_color=C_ACCENT,
                                     background_normal="", size_hint_y=None))
        objs = store.objects_list(self.app.conn)
        ws = []
        for o in objs:
            np = len(store.projects_list(self.app.conn, o["id"]))
            ws.append(_row(o["name"], self._open, sub="%d проектов · долгий тап: правка" % np))
        if not objs:
            ws.append(Label(text="Объектов пока нет.\nНажмите «+ Объект».",
                            color=(0.4, 0.4, 0.45, 1)))
        self.content.add_widget(_list_scroll(ws))

    def _add(self, *a):
        Diag(self.app, "Новый объект", on_ok=self._do_add).open()

    def _do_add(self, name):
        if name:
            store.objects_add(self.app.conn, name)
        self.refresh()

    def _open(self, btn):
        # найдём объект по тексту
        for o in store.objects_list(self.app.conn):
            if o["name"] == btn.children[0].children[0].text:
                self.app.open_object(o["id"])
                return


class ObjectScreen(AppScreen):
    """Проекты объекта + чек-лист, подрядчики, записки."""
    def __init__(self, app, oid, **kw):
        self.oid = oid
        row = app.conn.execute("SELECT name FROM objects WHERE id=?", (oid,)).fetchone()
        super().__init__(app, "Объект: %s" % (row["name"] if row else "?"), **kw)
        self.refresh()

    def refresh(self):
        self.content.clear_widgets()
        oid = self.oid
        self.content.add_widget(_btn("+ Проект", self._add_p,
                                     background_color=C_ACCENT, background_normal="",
                                     size_hint_y=None))
        projs = store.projects_list(self.app.conn, oid)
        ws = []
        for p in projs:
            ws.append(_row(p["name"], lambda *a, pid=p["id"]: self.app.open_project(pid)))
        ws.append(_row("Чек-лист", lambda *a: self.app.open_checklist(oid),
                       sub="роли СС / АДИС, недели"))
        ws.append(_row("Подрядчики и КС-2", lambda *a: self.app.open_contractors(oid)))
        ws.append(_row("Заявки объекта", lambda *a: self.app.open_orders(oid)))
        ws.append(_row("Записки", lambda *a: self.app.open_memos(oid)))
        ws.append(_row("Перемещения на объект", lambda *a: self.app.open_moves(oid)))
        self.content.add_widget(_list_scroll(ws))

    def _add_p(self, *a):
        Diag(self.app, "Новый проект", on_ok=self._do_add).open()

    def _do_add(self, name):
        if name:
            store.projects_add(self.app.conn, self.oid, name)
        self.refresh()


class ProjectScreen(AppScreen):
    def __init__(self, app, pid, **kw):
        self.pid = pid
        row = app.conn.execute(
            "SELECT p.name, o.name AS oname FROM projects p JOIN objects o "
            "ON o.id=p.object_id WHERE p.id=?", (pid,)).fetchone()
        super().__init__(app, row["name"] if row else "Проект", **kw)
        self.refresh()

    def refresh(self):
        self.content.clear_widgets()
        self.content.add_widget(_row("Спецификация", lambda *a: self.app.open_spec(self.pid),
                                     sub="просмотр и правка ячеек"))
        self.content.add_widget(_row("PDF-версии", lambda *a: self.app.open_pdf(self.pid)))
        self.content.add_widget(_row("Заявки проекта", lambda *a: self.app.open_orders(None,
                                                                                     self.pid)))


class SpecScreen(AppScreen):
    """Спецификация: горизонтальный скролл колонок, тап по ячейке — правка."""
    def __init__(self, app, pid, **kw):
        self.pid = pid
        row = app.conn.execute("SELECT name FROM projects WHERE id=?", (pid,)).fetchone()
        super().__init__(app, "Спецификация: %s" % (row["name"] if row else "?"), **kw)
        self.refresh()

    def refresh(self):
        self.content.clear_widgets()
        cols, rows, cells = store.spec_grid(self.app.conn, self.pid)
        if not cols:
            self.content.add_widget(Label(text="Колонок нет. Создайте их на ПК "
                                              "или добавьте кнопкой ниже.",
                                          color=(0.4, 0.4, 0.45, 1)))
            self.content.add_widget(_btn("+ Колонка", self._add_col, size_hint_y=None))
            return
        self.cells = cells
        nrows = max(len(rows), 1)
        g = GridLayout(cols=len(cols), size_hint_y=None, row_default_height=dp(44),
                       spacing=dp(1), padding=[dp(2), dp(2)])
        g.bind(minimum_height=g.setter("height"))
        for c in cols:
            b = Button(text=c["name"], font_size=dp(13), bold=True,
                       background_color=(0.85, 0.87, 0.91, 1), background_normal="",
                       size_hint_y=None, height=dp(40))
            g.add_widget(b)
        row_map = {r["id"]: i for i, r in enumerate(rows)}
        cell_by = {}
        for r in rows:
            for c in cols:
                val = cells.get(r["id"], {}).get(c["id"], "")
                btn = Button(text=val, font_size=dp(12), background_normal="",
                             background_color=C_CARD, color=C_TEXT,
                             size_hint_y=None, height=dp(44))
                btn.bind(on_press=lambda *a, rid=r["id"], cid=c["id"]: self._edit(rid, cid))
                g.add_widget(btn)
                cell_by[(r["id"], c["id"])] = btn
        self.cell_by = cell_by
        self.content.add_widget(ScrollView())
        sv = self.content.children[0]
        sv.add_widget(g)
        bar = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(6))
        bar.add_widget(_btn("+ Строка", lambda *a: self._add_row(), size_hint_x=1))
        bar.add_widget(_btn("+ Колонка", lambda *a: self._add_col(), size_hint_x=1))
        self.content.add_widget(bar)

    def _edit(self, rid, cid):
        cur = self.cell_by.get((rid, cid))
        val = cur.text if cur else ""
        Diag(self.app, "Значение ячейки", value=val,
             on_ok=lambda v: self._save(rid, cid, v), multiline=True).open()

    def _save(self, rid, cid, v):
        store.spec_cell_set(self.app.conn, rid, cid, v)
        btn = self.cell_by.get((rid, cid))
        if btn:
            btn.text = v

    def _add_row(self, *a):
        store.spec_add_row(self.app.conn, self.pid)
        self.refresh()

    def _add_col(self, *a):
        Diag(self.app, "Новая колонка", value="Новая", on_ok=self._do_col).open()

    def _do_col(self, name):
        if name:
            store.spec_add_column(self.app.conn, self.pid, name)
        self.refresh()


class PdfScreen(AppScreen):
    def __init__(self, app, pid, **kw):
        self.pid = pid
        super().__init__(app, "PDF-версии", **kw)
        self.refresh()

    def refresh(self):
        self.content.clear_widgets()
        docs = store.pdf_list(self.app.conn, self.pid)
        ws = []
        for d in docs:
            mark = "✔ актуальная" if d["is_actual"] else ""
            ws.append(_row(d["title"] + (("  " + mark) if mark else ""),
                           lambda *a, dd=d: self._open(dd),
                           sub=(d["comment"] or "") + " · долгий тап: сделать актуальной"))
        if not docs:
            ws.append(Label(text="PDF загружаются на ПК.\nСинхронизация перенесёт их сюда.",
                            color=(0.4, 0.4, 0.45, 1)))
        self.content.add_widget(_list_scroll(ws))

    def _open(self, d):
        store.pdf_set_actual(self.app.conn, self.pid, d["id"])
        path = os.path.join(store.APP_DIR, d["path"].replace("/", os.sep)) \
            if not os.path.isabs(d["path"]) else d["path"]
        _open_pdf(path)
        self.refresh()


class CheckScreen(AppScreen):
    """Чек-лист: роли, недели, статусы. Данные — как в ПК-версии."""
    def __init__(self, app, oid, **kw):
        self.oid = oid
        super().__init__(app, "Чек-лист", **kw)
        self.role = "CC"
        self.week = store.week_key()
        self.refresh()

    def refresh(self):
        self.content.clear_widgets()
        top = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
        for r, lbl in (("CC", "Инженер СС"), ("ADIS", "Инженер АДИС")):
            b = _btn(lbl, lambda *a, rr=r: self._set_role(rr),
                     background_color=C_ACCENT if self.role == r else (0.8, 0.8, 0.85, 1),
                     background_normal="", font_size=dp(14))
            top.add_widget(b)
        self.content.add_widget(top)
        wk = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        wk.add_widget(_btn("<", lambda *a: self._shift(-1), size_hint_x=None, width=dp(48)))
        wk.add_widget(_btn(self.week, self._pick_week))
        wk.add_widget(_btn(">", lambda *a: self._shift(1), size_hint_x=None, width=dp(48)))
        self.content.add_widget(wk)
        store.chk_fill_week(self.app.conn, self.oid, self.role, self.week)
        data = store.chk_week(self.app.conn, self.oid, self.role, self.week)
        items = data.get("items", {})
        ws = []
        for sec in store.chk_template(self.app.conn, self.oid, self.role).get("secs", []):
            for it in sec.get("items", []):
                k = store.chk_key(sec.get("name", ""), it.get("name", ""))
                rec = items.get(k, {})
                st = rec.get("status", "Не приступали")
                col = {"Выполнено": C_OK, "Завершено": C_OK,
                       "В работе": C_WARN}.get(st, C_CARD)
                ws.append(_row(it.get("name", ""), self._edit_item,
                               sub="%s%s" % (st, (" · %d%%" % rec.get("pct", 0))
                                             if rec.get("pct") else ""),
                               color=col))
        if not ws:
            ws.append(Label(text="Шаблон чек-листа для этой роли пуст.\n"
                                "Шаблон создаётся на ПК-версии.",
                            color=(0.4, 0.4, 0.45, 1)))
        self.content.add_widget(_list_scroll(ws))

    def _set_role(self, r):
        self.role = r
        self.refresh()

    def _shift(self, d):
        from datetime import timedelta
        try:
            y, w = self.week.split("-Нед")
            base = datetime(int(y), 1, 4) + timedelta(weeks=int(w) - 1)
        except Exception:
            base = datetime.now()
        base = base + timedelta(weeks=d)
        self.week = store.week_key(base)
        self.refresh()

    def _pick_week(self, *a):
        Diag(self.app, "Неделя (год-НедNN)", value=self.week,
             on_ok=self._do_week).open()

    def _do_week(self, v):
        if v:
            self.week = v
            self.refresh()

    def _edit_item(self, btn):
        # находим пункт по тексту
        name = btn.children[0].children[0].text
        rec = None
        sec = ""
        data = store.chk_week(self.app.conn, self.oid, self.role, self.week)
        for k, v in data.get("items", {}).items():
            if k.split(" :: ")[-1] == name:
                rec, sec, item = v, k.split(" :: ")[0], k.split(" :: ")[-1]
        if rec is None:
            return
        fields = {}
        box = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        box.add_widget(Label(text=item, font_size=dp(16), bold=True, color=C_TEXT))
        for f, lbl in (("status", "Статус"), ("pct", "%"), ("date", "Дата"),
                       ("problem", "Проблема"), ("comment", "Комментарий")):
            h = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
            h.add_widget(Label(text=lbl, font_size=dp(14), size_hint_x=0.35, color=C_TEXT))
            if f == "status":
                self._status_btn = _btn(rec.get("status", ""), self._cyc, size_hint_x=0.65)
                h.add_widget(self._status_btn)
            else:
                ti = TextInput(text=str(rec.get(f, "")), multiline=False, font_size=dp(14))
                h.add_widget(ti)
                fields[f] = ti
            box.add_widget(h)
        btns = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        mv = ModalView(auto_dismiss=True, size_hint=(0.94, 0.8))
        btns.add_widget(_btn("Отмена", mv.dismiss))
        btns.add_widget(_btn("Сохранить", self._save, background_color=C_ACCENT,
                             background_normal=""))
        box.add_widget(btns)
        mv.add_widget(box)
        self._tmp = dict(rec)
        self._tmp_sec, self._tmp_item, self._mv = sec, item, mv
        self._fields = fields
        mv.open()

    def _cyc(self, *a):
        st = self._status_btn.text
        i = store.CHK_STATUSES.index(st) if st in store.CHK_STATUSES else 0
        self._status_btn.text = store.CHK_STATUSES[(i + 1) % len(store.CHK_STATUSES)]

    def _save(self, *a):
        oid, role, week = self.oid, self.role, self.week
        data = store.chk_week(self.app.conn, oid, role, week)
        k = store.chk_key(self._tmp_sec, self._tmp_item)
        rec = data.setdefault("items", {}).setdefault(k, {})
        rec["status"] = self._status_btn.text
        if rec["status"] in ("Выполнено", "Завершено"):
            rec["pct"] = 100
        for f, ti in self._fields.items():
            v = ti.text.strip()
            if f == "pct":
                try:
                    rec[f] = int(float(v.replace(",", ".")))
                except Exception:
                    pass
            else:
                rec[f] = v
        store.chk_week_save(self.app.conn, oid, role, week, data)
        self._mv.dismiss()
        self.refresh()


class OrdersScreen(AppScreen):
    def __init__(self, app, oid=None, pid=None, **kw):
        self.oid, self.pid = oid, pid
        super().__init__(app, "Заявки", **kw)
        self.refresh()

    def refresh(self):
        self.content.clear_widgets()
        orders = store.orders_list(self.app.conn, pid=self.pid, object_id=self.oid)
        ws = []
        for o in orders:
            ws.append(_row("№%s %s" % (o["order_no"], o["name"][:40]),
                           lambda *a, oo=o: self._open(oo),
                           sub="%s · поставка: %s" % (o["status"] or "—",
                                                      o["delivery_date"] or "—")))
        if not ws:
            ws.append(Label(text="Заявок нет.", color=(0.4, 0.4, 0.45, 1)))
        self.content.add_widget(_list_scroll(ws))

    def _open(self, o):
        ws = []
        items = store.order_items_list(self.app.conn, o["id"])
        for it in items:
            ws.append(_row(it["goods"][:60],
                           self._cyc_status,
                           sub="%s · кол-во %s %s" % (it["status"], it["qty"], it["unit"])))
            ws[-1].item_id = it["id"]
            ws[-1].status = it["status"]
        mv = ModalView(auto_dismiss=True, size_hint=(0.98, 0.9))
        lay = AppScreen(self.app, "Заявка №%s" % o["order_no"])
        mv.add_widget(lay)
        lay.content.add_widget(_list_scroll(ws))
        mv.open()

    def _cyc_status(self, btn):
        i = (store.ORDER_STATUSES.index(btn.status) + 1) % len(store.ORDER_STATUSES) \
            if btn.status in store.ORDER_STATUSES else 0
        store.order_item_set_status(self.app.conn, btn.item_id,
                                    store.ORDER_STATUSES[i])
        btn.status = store.ORDER_STATUSES[i]
        btn.children[0].children[0].text = store.ORDER_STATUSES[i]


class ContractorsScreen(AppScreen):
    def __init__(self, app, oid, **kw):
        self.oid = oid
        super().__init__(app, "Подрядчики", **kw)
        self.refresh()

    def refresh(self):
        self.content.clear_widgets()
        cs = store.contractors_list(self.app.conn, self.oid)
        ws = []
        for c in cs:
            n = len(store.ks2_docs_list(self.app.conn, c["id"]))
            ws.append(_row(c["name"], self._open, sub="КС-2: %d" % n))
        if not ws:
            ws.append(Label(text="Подрядчиков нет.", color=(0.4, 0.4, 0.45, 1)))
        self.content.add_widget(_list_scroll(ws))

    def _open(self, btn):
        name = btn.children[0].children[0].text
        for c in store.contractors_list(self.app.conn, self.oid):
            if c["name"] == name:
                docs = store.ks2_docs_list(self.app.conn, c["id"])
                mv = ModalView(auto_dismiss=True, size_hint=(0.98, 0.9))
                lay = AppScreen(self.app, "КС-2: %s" % c["name"])
                mv.add_widget(lay)
                ws = []
                for d in docs:
                    ws.append(_row(
                        "№%s от %s" % (d["doc_no"] or "—", d["doc_date"] or "—"),
                        self._doc,
                        sub="период: %s – %s%s" % (
                            d["period_from"] or "—", d["period_to"] or "—",
                            (" · " + (d["sections"] or ""))[:60])))
                    ws[-1].doc_id = d["id"]
                if not ws:
                    ws.append(Label(text="Актов КС-2 нет.", color=(0.4, 0.4, 0.45, 1)))
                lay.content.add_widget(_list_scroll(ws))
                mv.open()
                return

    def _doc(self, btn):
        d = store.ks2_doc_get(self.app.conn, btn.doc_id)
        if not d:
            return
        items = store.ks2_items_list(self.app.conn, d["id"])
        mv = ModalView(auto_dismiss=True, size_hint=(0.98, 0.9))
        lay = AppScreen(self.app, "КС-2 №%s от %s" % (d["doc_no"] or "—",
                                                      d["doc_date"] or "—"))
        mv.add_widget(lay)
        ws = [_row("Отчётный период", sub="%s – %s" % (d["period_from"] or "—",
                                                       d["period_to"] or "—")),
              _row("Разделы", sub=d["sections"] or "—")]
        for it in items:
            ws.append(_row(it["name"][:50],
                           sub="%s %s × %s = %s" % (it["qty"], it["unit"],
                                                    it["price"], it["total"])))
        if not items:
            ws.append(Label(text="Позиций нет (загружаются на ПК).",
                            color=(0.4, 0.4, 0.45, 1)))
        lay.content.add_widget(_list_scroll(ws))
        mv.open()


class MovesScreen(AppScreen):
    def __init__(self, app, oid, **kw):
        self.oid = oid
        super().__init__(app, "Перемещения", **kw)
        self.refresh()

    def refresh(self):
        self.content.clear_widgets()
        self.content.add_widget(_btn("+ Со склада на объект", self._send,
                                     background_color=C_ACCENT, background_normal="",
                                     size_hint_y=None))
        mv = store.moves_list(self.app.conn, self.oid)
        ws = [_row(m["name"][:50],
                   sub="%s %s · ячейка %s · %s" % (m["qty"], m["unit"], m["cell"],
                                                   m["created"]))
              for m in mv]
        if not ws:
            ws.append(Label(text="Перемещений нет.", color=(0.4, 0.4, 0.45, 1)))
        self.content.add_widget(_list_scroll(ws))

    def _send(self, *a):
        ws = []
        for it in store.warehouse_items_list(self.app.conn):
            ws.append(_row("%s · %s %s" % (it["name"][:40], it["qty"], it["unit"]),
                           self._pick_wh))
            ws[-1].wh = it
        mv = ModalView(auto_dismiss=True, size_hint=(0.98, 0.9))
        lay = AppScreen(self.app, "Выберите позицию склада")
        mv.add_widget(lay)
        lay.content.add_widget(_list_scroll(ws))
        mv.open()

    def _pick_wh(self, btn):
        it = btn.wh
        mv = ModalView(auto_dismiss=True, size_hint=(0.94, 0.4))
        box = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        box.add_widget(Label(text="Количество (%s):" % it["unit"], color=C_TEXT))
        ti = TextInput(text="1", multiline=False, font_size=dp(16))
        box.add_widget(ti)
        btns = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        btns.add_widget(_btn("Отмена", mv.dismiss))
        btns.add_widget(_btn("Отправить", lambda *a: self._do_send(mv, it, ti.text.strip()),
                             background_color=C_ACCENT, background_normal=""))
        box.add_widget(btns)
        mv.add_widget(box)
        mv.open()

    def _do_send(self, mv, it, qty):
        if not qty:
            return
        store.moves_add(self.app.conn, self.oid, [{
            "wh_id": it["id"], "name": it["name"], "unit": it["unit"],
            "qty": qty, "cell": it.get("cell", ""), "project": "",
            "spec_text": "", "created": datetime.now().strftime("%d.%m.%Y %H:%M")}])
        mv.dismiss()
        self.refresh()


class WarehouseScreen(AppScreen):
    def __init__(self, app, **kw):
        super().__init__(app, "Склад", **kw)
        self.refresh()

    def refresh(self):
        self.content.clear_widgets()
        self.query = getattr(self, "query", "")
        ti = TextInput(text=self.query, multiline=False, font_size=dp(16),
                       size_hint_y=None, height=dp(44), hint_text="Поиск по складу")
        ti.bind(text=lambda inst, v: self._set_query(v))
        self.content.add_widget(ti)
        items = store.warehouse_items_list(self.app.conn)
        if self.query:
            ms = store.warehouse_matches_fuzzy(self.app.conn, self.query, limit=20)
            shown = [it for _, it in ms]
        else:
            shown = items
        ws = [_row(it["name"][:60], sub="остаток: %s %s · ячейка %s" % (
            it["qty"], it["unit"], it.get("cell", ""))) for it in shown]
        if not ws:
            ws.append(Label(text="Склад не загружен или пуст.\nОстатки загружаются на ПК "
                                "и приходят синхронизацией.",
                            color=(0.4, 0.4, 0.45, 1)))
        self.content.add_widget(_list_scroll(ws))

    def _set_query(self, v):
        self.query = v
        Clock.unschedule(getattr(self, "_refill", None))
        self._refill = Clock.schedule_once(lambda *a: self._do_refill(), 0.4)

    def _do_refill(self):
        self.refresh()


class SearchScreen(AppScreen):
    def __init__(self, app, **kw):
        super().__init__(app, "Поиск", back=False, **kw)
        self.refresh()

    def refresh(self):
        self.content.clear_widgets()
        self.query = getattr(self, "query", "")
        ti = TextInput(text=self.query, multiline=False, font_size=dp(16),
                       size_hint_y=None, height=dp(44), hint_text="Поиск по всему")
        ti.bind(text=lambda inst, v: self._set_query(v))
        self.content.add_widget(ti)
        res = store.search(self.app.conn, self.query) if self.query.strip() else []
        ws = []
        for r in res:
            ws.append(_row("[%s] %s" % (r["kind"], r["title"][:60]),
                           sub="", color=C_CARD))
            if r["object_id"]:
                ws[-1].bind(on_press=lambda *a, rr=r: self.app.open_object(rr["object_id"]))
        if not res and self.query.strip():
            ws.append(Label(text="Ничего не найдено.", color=(0.4, 0.4, 0.45, 1)))
        self.content.add_widget(_list_scroll(ws))

    def _set_query(self, v):
        self.query = v
        Clock.unschedule(getattr(self, "_refill", None))
        self._refill = Clock.schedule_once(lambda *a: self._hard_refresh(), 0.4)

    def _hard_refresh(self):
        self.refresh()


class SyncScreen(AppScreen):
    def __init__(self, app, **kw):
        super().__init__(app, "Синхронизация", **kw)
        self.refresh()

    def refresh(self):
        self.content.clear_widgets()
        login = store.get_setting(self.app.conn, "yd_login", "")
        pw = store.get_setting(self.app.conn, "yd_pass", "")
        box = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(8))
        self.ti_login = TextInput(text=login, multiline=False, font_size=dp(16),
                                  size_hint_y=None, height=dp(44), hint_text="логин Яндекса")
        self.ti_pass = TextInput(text=pw, multiline=False, font_size=dp(16), password=True,
                                 size_hint_y=None, height=dp(44),
                                 hint_text="пароль приложения (Файлы)")
        box.add_widget(self.ti_login)
        box.add_widget(self.ti_pass)
        h = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        h.add_widget(_btn("Сохранить", self._save))
        h.add_widget(_btn("⟳ Загрузить", self._pull, background_color=C_ACCENT,
                          background_normal=""))
        box.add_widget(h)
        h2 = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        h2.add_widget(_btn("↑ Отправить", self._push))
        box.add_widget(h2)
        self.status = Label(text=getattr(self, "status_text", ""),
                            font_size=dp(14), color=C_TEXT, halign="left")
        box.add_widget(self.status)
        self.content.add_widget(box)

    def _save(self, *a):
        store.set_setting(self.app.conn, "yd_login", self.ti_login.text.strip())
        store.set_setting(self.app.conn, "yd_pass", self.ti_pass.text.strip())
        self._msg("Логин и пароль сохранены")

    def _msg(self, s):
        self.status_text = s
        self.refresh()

    def _pull(self, *a):
        self._save()
        l, p = self.ti_login.text.strip(), self.ti_pass.text.strip()
        if not l or not p:
            self._msg("Заполните логин и пароль")
            return
        self._msg("Загрузка с Диска…")
        try:
            ydsync.lock_get(l, p)
            n, w = ydsync.pull_all(l, p, progress=lambda s: self._msg("…" + s))
            self.app.reconnect()
            self._msg("Загружено файлов: %d%s" % (n, (" · " + "; ".join(w)) if w else ""))
        except ydsync.SyncError as e:
            self._msg("Ошибка: %s" % e)

    def _push(self, *a):
        self._save()
        l, p = self.ti_login.text.strip(), self.ti_pass.text.strip()
        if not l or not p:
            self._msg("Заполните логин и пароль")
            return
        self._msg("Отправка на Диск…")
        try:
            n, w = ydsync.push_all(l, p, progress=lambda s: self._msg("…" + s))
            ydsync.lock_set(l, p, "mobile@" + datetime.now().strftime("%d.%m %H:%M"))
            self._msg("Отправлено файлов: %d%s" % (n, (" · " + "; ".join(w)) if w else ""))
        except ydsync.SyncError as e:
            self._msg("Ошибка: %s" % e)


class HomeScreen(AppScreen):
    def __init__(self, app, **kw):
        super().__init__(app, "SiteManager", back=False, **kw)
        self.refresh()

    def refresh(self):
        self.content.clear_widgets()
        objs = store.objects_list(self.app.conn)
        ws = []
        for o in objs:
            np = len(store.projects_list(self.app.conn, o["id"]))
            ws.append(_row(o["name"], self._open, sub="%d проектов" % np))
        if not objs:
            ws.append(Label(text="База пуста. Настройте синхронизацию\nи загрузите базу с Диска.",
                            color=(0.4, 0.4, 0.45, 1)))
        self.content.add_widget(_list_scroll(ws))
        bar = BoxLayout(size_hint_y=None, height=dp(60), spacing=dp(6),
                        padding=[dp(4), dp(4)])
        bar.add_widget(_btn("＋ Объект", self._add_obj, font_size=dp(13)))
        bar.add_widget(_btn("Склад", self._wh, font_size=dp(13)))
        bar.add_widget(_btn("Поиск", self._search, font_size=dp(13)))
        bar.add_widget(_btn("Синхр.", self._sync, font_size=dp(13),
                            background_color=C_ACCENT, background_normal=""))
        self.add_widget(bar)

    def _open(self, btn):
        for o in store.objects_list(self.app.conn):
            if o["name"] == btn.children[0].children[0].text:
                self.app.open_object(o["id"])
                return

    def _add_obj(self, *a):
        Diag(self.app, "Новый объект", on_ok=self._do_add).open()

    def _do_add(self, name):
        if name:
            store.objects_add(self.app.conn, name)
        self.refresh()

    def _wh(self, *a):
        self.app.nav.push(WarehouseScreen(self.app), "Склад")

    def _search(self, *a):
        self.app.nav.push(SearchScreen(self.app), "Поиск")

    def _sync(self, *a):
        self.app.nav.push(SyncScreen(self.app), "Синхронизация")


class SiteManagerApp(App):
    title = "SiteManager"

    def build(self):
        # на Android база живёт в каталоге приложения
        if platform == "android":
            try:
                d = self.user_data_dir or "."
            except Exception:
                d = "."
            store.APP_DIR = d
            store.DB_PATH = os.path.join(d, "sitemanager.db")
            ydsync.APP_DIR = d
        self.conn = store.connect()
        store.init_db(self.conn)
        self.nav = Nav(self)
        self._build_ui()
        return self.root_layout

    def _build_ui(self):
        from kivy.uix.floatlayout import FloatLayout
        self.root_layout = FloatLayout()
        self.render()

    def render(self):
        from kivy.uix.floatlayout import FloatLayout
        self.root_layout.clear_widgets()
        if self.nav.stack:
            w, _ = self.nav.stack[-1]
        else:
            w = PinScreen(self) if store.get_pin() else PinScreen(self)
            self.nav.stack = [(w, "SiteManager")]
        self.root_layout.add_widget(w)

    def enter(self):
        self.conn = store.connect()
        store.init_db(self.conn)
        self.nav.reset(HomeScreen(self), "SiteManager")

    def reconnect(self):
        try:
            self.conn.close()
        except Exception:
            pass
        self.conn = store.connect()
        store.init_db(self.conn)

    def open_object(self, oid):
        self.nav.push(ObjectScreen(self, oid), "Объект")

    def open_project(self, pid):
        self.nav.push(ProjectScreen(self, pid), "Проект")

    def open_spec(self, pid):
        self.nav.push(SpecScreen(self, pid), "Спецификация")

    def open_pdf(self, pid):
        self.nav.push(PdfScreen(self, pid), "PDF")

    def open_checklist(self, oid):
        self.nav.push(CheckScreen(self, oid), "Чек-лист")

    def open_contractors(self, oid):
        self.nav.push(ContractorsScreen(self, oid), "Подрядчики")

    def open_orders(self, oid=None, pid=None):
        self.nav.push(OrdersScreen(self, oid, pid), "Заявки")

    def open_memos(self, oid):
        self.nav.push(MemosScreen(self, oid), "Записки")

    def open_moves(self, oid):
        self.nav.push(MovesScreen(self, oid), "Перемещения")


class MemosScreen(AppScreen):
    def __init__(self, app, oid, **kw):
        self.oid = oid
        super().__init__(app, "Записки", **kw)
        self.refresh()

    def refresh(self):
        self.content.clear_widgets()
        ms = store.memos_list(self.app.conn, self.oid)
        ws = [_row(m["title"] or "Без названия",
                   sub="%s · %s" % (m["to_whom"], m["created"])) for m in ms]
        if not ws:
            ws.append(Label(text="Записок нет. Создаются на ПК и приходят синхронизацией.",
                            color=(0.4, 0.4, 0.45, 1)))
        self.content.add_widget(_list_scroll(ws))


if __name__ == "__main__":
    SiteManagerApp().run()
