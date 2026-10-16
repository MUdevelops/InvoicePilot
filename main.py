"""Invoice Pilot - offline invoicing & financial dashboard.   Run:  python main.py   (Python 3.11.9)"""
import base64
import io
import math
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import tkinter as tk
from datetime import date, timedelta
from tkinter import filedialog, ttk

if sys.version_info < (3, 11):
    sys.exit("Invoice Pilot needs Python 3.11 or newer (3.11.9 recommended).")
try:
    import customtkinter as ctk
    from PIL import Image, ImageDraw, ImageTk
    import database as db
except ImportError as exc:
    sys.exit(f"Missing dependency: {exc}\nRun:  pip install -r requirements.txt")

FONT = "Segoe UI"
# ------------------------------------------------------------------ theme (light, dark)
P = {
    "bg": ("#EEF2F9", "#0A0F1E"), "panel": ("#FFFFFF", "#121A2E"), "panel2": ("#F2F5FB", "#1A2440"),
    "border": ("#DCE3F0", "#24314F"), "text": ("#0F172A", "#EAF0FF"), "muted": ("#64748B", "#8FA0C4"),
    "accent": ("#2563EB", "#3B82F6"), "accent_h": ("#1D4ED8", "#2563EB"), "cyan": ("#0891B2", "#22D3EE"),
    "green": ("#16A34A", "#34D399"), "amber": ("#D97706", "#FBBF24"), "red": ("#DC2626", "#F87171"),
    "violet": ("#7C3AED", "#A78BFA"), "input": ("#FFFFFF", "#0D1426"), "row_alt": ("#F7F9FD", "#151F37"),
    "sel": ("#DBEAFE", "#1F3B73"), "head": ("#E7EDF8", "#1B2745"), "danger_bg": ("#FEE2E2", "#3A1C26"),
    "danger_h": ("#FCA5A5", "#5B2433"), "sec_h": ("#DDE6F6", "#25335A"), "side": ("#0B1226", "#080C19"),
}
STATUS_COL = {"paid": "green", "unpaid": "accent", "partial": "amber", "overdue": "red", "void": "muted",
              "draft": "muted", "received": "green", "reversed": "muted", "accepted": "green", "sent": "accent",
              "declined": "red", "expired": "amber", "converted": "violet"}
HUB = []                      # callbacks run after a theme change


def R(name):
    """Resolve a palette colour for widgets that cannot take (light, dark) tuples."""
    return P[name][0 if ctk.get_appearance_mode() == "Light" else 1]


def F(size=13, weight="normal"):
    return ctk.CTkFont(family=FONT, size=size, weight=weight)


# ------------------------------------------------------------------ icons (drawn, no files)
def _draw_icon(name, rgb, px=192):
    s, im = px / 24, Image.new("RGBA", (px, px), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c, w = rgb + (255,), int(2.1 * px / 24)
    L = lambda *pts: d.line([(x * s, y * s) for x, y in pts], fill=c, width=w, joint="curve")
    RR = lambda a, b, e, f, r=3, fill=None: d.rounded_rectangle([a * s, b * s, e * s, f * s], r * s, outline=c, width=w, fill=fill)
    if name == "home":
        L((3, 11), (12, 3.5), (21, 11)); L((6, 9.5), (6, 20.5), (18, 20.5), (18, 9.5)); L((10.5, 20.5), (10.5, 14.5), (13.5, 14.5), (13.5, 20.5))
    elif name == "plus":
        L((12, 5), (12, 19)); L((5, 12), (19, 12))
    elif name == "doc":
        RR(5, 3, 19, 21, 2.5); L((8.5, 9), (15.5, 9)); L((8.5, 13), (15.5, 13)); L((8.5, 17), (13, 17))
    elif name == "quote":
        RR(5, 4.5, 19, 21, 2.5); RR(9, 2.5, 15, 6.5, 1.2, fill=c); L((8.5, 13.5), (11, 16)); L((11, 16), (15.5, 10.5))
    elif name == "users":
        d.ellipse([8.3 * s, 4 * s, 15.7 * s, 11.4 * s], outline=c, width=w); d.arc([4.5 * s, 13 * s, 19.5 * s, 28 * s], 180, 360, fill=c, width=w)
    elif name == "box":
        L((12, 3), (20, 7.5), (20, 16.5), (12, 21), (4, 16.5), (4, 7.5), (12, 3)); L((4, 7.5), (12, 12), (20, 7.5)); L((12, 12), (12, 21))
    elif name == "card":
        RR(3, 5.5, 21, 18.5, 2.5); L((3, 10), (21, 10)); L((6.5, 15), (10.5, 15))
    elif name == "wallet":
        RR(3, 6, 21, 19, 3); L((3, 9.5), (16, 9.5), (17.5, 7)); d.ellipse([16 * s, 12.6 * s, 18.4 * s, 15 * s], fill=c)
    elif name == "chart":
        for x0, y0, x1 in ((5, 12, 8.4), (10.3, 6, 13.7), (15.6, 9.5, 19)):
            d.rounded_rectangle([x0 * s, y0 * s, x1 * s, 20.5 * s], 0.8 * s, fill=c)
        L((3, 21.5), (21, 21.5))
    elif name == "gear":
        d.ellipse([8.8 * s, 8.8 * s, 15.2 * s, 15.2 * s], outline=c, width=w)
        d.ellipse([6 * s, 6 * s, 18 * s, 18 * s], outline=c, width=w)
        for k in range(8):
            a = k * math.pi / 4
            L((12 + 6.3 * math.cos(a), 12 + 6.3 * math.sin(a)), (12 + 9 * math.cos(a), 12 + 9 * math.sin(a)))
    elif name == "menu":
        L((4, 7), (20, 7)); L((4, 12), (20, 12)); L((4, 17), (20, 17))
    elif name == "sun":
        d.ellipse([7.5 * s, 7.5 * s, 16.5 * s, 16.5 * s], outline=c, width=w)
        for k in range(8):
            a = k * math.pi / 4
            L((12 + 7 * math.cos(a), 12 + 7 * math.sin(a)), (12 + 10 * math.cos(a), 12 + 10 * math.sin(a)))
    elif name == "moon":
        d.ellipse([4 * s, 3 * s, 20 * s, 19 * s], fill=c); d.ellipse([9 * s, 1 * s, 24 * s, 15 * s], fill=(0, 0, 0, 0))
    return im


_ICON_CACHE = {}


def icon(name, light="#475569", dark="#C7D2FE", size=20):
    key = (name, light, dark, size)
    if key not in _ICON_CACHE:
        mk = lambda hx: _draw_icon(name, tuple(int(hx[i:i + 2], 16) for i in (1, 3, 5))).resize((size * 3, size * 3), Image.LANCZOS)
        _ICON_CACHE[key] = ctk.CTkImage(light_image=mk(light), dark_image=mk(dark), size=(size, size))
    return _ICON_CACHE[key]


# ------------------------------------------------------------------ small widget factories
def lbl(parent, text="", size=13, weight="normal", color="text", **kw):
    return ctk.CTkLabel(parent, text=text, font=F(size, weight), text_color=P[color], **kw)


def btn(parent, text, command, kind="primary", width=0, **kw):
    st = {"primary": dict(fg_color=P["accent"], hover_color=P["accent_h"], text_color="white"),
          "accent": dict(fg_color=P["cyan"], hover_color=P["accent"], text_color=("white", "#04121F")),
          "secondary": dict(fg_color=P["panel2"], hover_color=P["sec_h"], text_color=P["text"]),
          "danger": dict(fg_color=P["danger_bg"], hover_color=P["danger_h"], text_color=P["red"]),
          "ghost": dict(fg_color="transparent", hover_color=P["panel2"], text_color=P["accent"])}[kind]
    return ctk.CTkButton(parent, text=text, command=command, corner_radius=9, height=34, font=F(13, "bold"),
                         width=width, **st, **kw)


def ent(parent, placeholder="", width=180, var=None, **kw):
    return ctk.CTkEntry(parent, placeholder_text=placeholder, width=width, height=34, corner_radius=9, fg_color=P["input"],
                        border_color=P["border"], text_color=P["text"], placeholder_text_color=P["muted"], font=F(13),
                        textvariable=var, **kw)


def cmb(parent, values, width=180, command=None):
    return ctk.CTkComboBox(parent, values=values or [""], width=width, height=34, corner_radius=9, state="readonly",
                           fg_color=P["input"], border_color=P["border"], button_color=P["accent"],
                           button_hover_color=P["accent_h"], dropdown_font=F(13), font=F(13), text_color=P["text"],
                           dropdown_fg_color=P["panel"], dropdown_text_color=P["text"],
                           dropdown_hover_color=P["sel"], command=command)


def card(parent, **kw):
    return ctk.CTkFrame(parent, fg_color=P["panel"], corner_radius=16, border_width=1, border_color=P["border"], **kw)


def textbox(parent, height=64):
    return ctk.CTkTextbox(parent, height=height, corner_radius=9, border_width=1, border_color=P["border"],
                          fg_color=P["input"], text_color=P["text"], font=F(13))


def bar(parent):
    return ctk.CTkFrame(parent, fg_color="transparent")


def run_safely(parent, func, *args, **kw):
    try:
        return True, func(*args, **kw)
    except db.ValidationError as exc:
        error(parent, str(exc), "Please check your input")
    except sqlite3.IntegrityError:
        error(parent, "That record conflicts with an existing one (for example a duplicate number). Please try again.")
    except db.BackupError as exc:
        error(parent, str(exc), "Backup problem")
    except PermissionError:
        error(parent, "Permission denied. Close the file if it is open in another program and try again.")
    except Exception as exc:  # noqa: BLE001 - last-resort guard so the UI never crashes
        error(parent, f"{type(exc).__name__}: {exc}")
    return False, None


def open_path(path, print_it=False):
    path = str(path)
    if sys.platform.startswith("win"):
        os.startfile(path, "print") if print_it else os.startfile(path)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def ask_save(parent, title, name, ext, label):
    return filedialog.asksaveasfilename(parent=parent, title=title, initialfile=name, defaultextension=ext,
                                        filetypes=[(label, "*" + ext), ("All files", "*.*")])


def sym():
    return db.get_settings().get("currency_symbol", "Rs.") or "Rs."


def mny(v):
    return db.money(v, sym())


# ------------------------------------------------------------------ dialogs
class Dialog(ctk.CTkToplevel):
    def __init__(self, parent, title, width=520, height=480):
        super().__init__(parent)
        self.title(title)
        self.configure(fg_color=P["bg"])
        top = parent.winfo_toplevel()
        x = top.winfo_rootx() + max(0, (top.winfo_width() - width) // 2)
        y = top.winfo_rooty() + max(0, (top.winfo_height() - height) // 3)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(min(width, 420), min(height, 300))
        self.transient(top)
        self.after(150, self._grab)

    def _grab(self):
        try:
            self.grab_set()
            self.focus_force()
        except tk.TclError:
            pass


class Box(Dialog):
    """Themed message / confirmation box."""

    def __init__(self, parent, title, text, kind="info", ask=False):
        lines = max(2, sum(len(p) // 52 + 1 for p in text.split("\n")))
        super().__init__(parent, title, 440, min(120 + lines * 20 + 50, 560))
        self.resizable(False, False)
        self.result = False
        col = {"info": "accent", "error": "red", "ask": "amber"}["ask" if ask else kind]
        body = ctk.CTkFrame(self, fg_color=P["panel"], corner_radius=14, border_width=1, border_color=P["border"])
        body.pack(fill="both", expand=True, padx=14, pady=(14, 8))
        ctk.CTkFrame(body, width=5, fg_color=P[col], corner_radius=3).pack(side="left", fill="y", padx=(12, 0), pady=14)
        inner = bar(body)
        inner.pack(side="left", fill="both", expand=True, padx=14, pady=14)
        lbl(inner, title, 16, "bold").pack(anchor="w")
        lbl(inner, text, 13, color="muted", wraplength=340, justify="left").pack(anchor="w", pady=(6, 0))
        foot = bar(self)
        foot.pack(fill="x", padx=14, pady=(0, 14))
        if ask:
            btn(foot, "Yes, continue", lambda: self._close(True)).pack(side="right")
            btn(foot, "Cancel", lambda: self._close(False), "secondary").pack(side="right", padx=8)
        else:
            btn(foot, "OK", lambda: self._close(True), width=90).pack(side="right")
        self.protocol("WM_DELETE_WINDOW", lambda: self._close(False))
        self.after(120, lambda: self.lift())
        self.wait_window(self)

    def _close(self, v):
        self.result = v
        self.destroy()


def info(parent, text, title="Invoice Pilot"):
    Box(parent, title, text, "info")


def error(parent, text, title="Something went wrong"):
    Box(parent, title, text, "error")


def confirm(parent, text, title="Please confirm") -> bool:
    return Box(parent, title, text, ask=True).result


class FormDialog(Dialog):
    """fields: [(key, label, kind, options)] kind: text | multiline | combo."""

    def __init__(self, parent, title, fields, values=None, on_save=None, width=540, save_text="Save"):
        height = 140 + sum(118 if f[2] == "multiline" else 66 for f in fields)
        super().__init__(parent, title, width, min(height, 720))
        self.on_save, self.widgets, values = on_save, {}, values or {}
        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=(12, 0))
        for key, lab, kind, opts in fields:
            lbl(body, lab, 12, "bold", "muted").pack(anchor="w", pady=(6, 2))
            if kind == "multiline":
                w = textbox(body, 76)
                w.insert("1.0", values.get(key, "") or "")
            elif kind == "combo":
                w = cmb(body, opts, 300)
                w.set(values.get(key) or opts[0])
            else:
                w = ent(body, width=300)
                w.insert(0, str(values.get(key, "") or ""))
            w.pack(fill="x")
            self.widgets[key] = (kind, w)
        foot = bar(self)
        foot.pack(fill="x", padx=16, pady=14)
        btn(foot, save_text, self._save).pack(side="right")
        btn(foot, "Cancel", self.destroy, "secondary").pack(side="right", padx=8)

    def _save(self):
        vals = {k: (w.get("1.0", "end").strip() if kind == "multiline" else w.get().strip())
                for k, (kind, w) in self.widgets.items()}
        ok, _ = run_safely(self, self.on_save, vals)
        if ok:
            self.destroy()


# ------------------------------------------------------------------ tables
def style_tree():
    st = ttk.Style()
    try:
        st.theme_use("clam")
    except tk.TclError:
        pass
    st.configure("IP.Treeview", background=R("panel"), fieldbackground=R("panel"), foreground=R("text"), rowheight=34,
                 borderwidth=0, font=(FONT, 10))
    st.layout("IP.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    st.configure("IP.Treeview.Heading", background=R("head"), foreground=R("text"), font=(FONT, 10, "bold"),
                 relief="flat", padding=(8, 8), borderwidth=0)
    st.map("IP.Treeview", background=[("selected", R("sel"))], foreground=[("selected", R("text"))])
    st.map("IP.Treeview.Heading", background=[("active", R("sel"))])
    st.configure("IP.Vertical.TScrollbar", background=R("border"), troughcolor=R("panel"), bordercolor=R("panel"),
                 arrowcolor=R("muted"), lightcolor=R("border"), darkcolor=R("border"), relief="flat")


class DataTable(ctk.CTkFrame):
    """columns: [(key, title, width, anchor)]. Shows an empty-state message when there are no rows."""

    def __init__(self, parent, columns, on_double=None, height=12, empty="Nothing here yet."):
        super().__init__(parent, fg_color=P["panel"], corner_radius=12, border_width=1, border_color=P["border"])
        self.empty_text = empty
        self.tree = ttk.Treeview(self, columns=[c[0] for c in columns], show="headings", style="IP.Treeview",
                                 selectmode="browse", height=height)
        for key, title, width, anchor in columns:
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, anchor=anchor, stretch=True, minwidth=56)
        sb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview, style="IP.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", padx=(0, 2), pady=3)
        self.tree.pack(side="left", fill="both", expand=True, padx=(3, 0), pady=3)
        if on_double:
            self.tree.bind("<Double-1>", lambda e: on_double())
        self.msg = tk.Label(self, text=empty, font=(FONT, 11))
        HUB.append(self.retag)
        self.retag()

    def retag(self):
        try:
            for name, col in STATUS_COL.items():
                self.tree.tag_configure(name, foreground=R(col))
            self.tree.tag_configure("odd", background=R("row_alt"))
            self.msg.configure(bg=R("panel"), fg=R("muted"))
        except tk.TclError:
            pass

    def set_rows(self, rows):
        """rows: [(iid, values, status_tag_or_None)]."""
        self.tree.delete(*self.tree.get_children())
        for n, (iid, values, tag) in enumerate(rows):
            self.tree.insert("", "end", iid=str(iid), values=values, tags=(["odd"] if n % 2 else []) + ([tag] if tag else []))
        if rows:
            self.msg.place_forget()
        else:
            self.msg.configure(text=self.empty_text)
            self.msg.place(relx=0.5, rely=0.55, anchor="center")

    def selected(self):
        sel = self.tree.selection()
        return sel[0] if sel else None


class RangeBar(ctk.CTkFrame):
    PRESETS = ["This month", "Last 30 days", "This quarter", "This year", "All time", "Custom"]

    def __init__(self, parent, on_change, default="This month"):
        super().__init__(parent, fg_color="transparent")
        self.on_change = on_change
        self.preset = cmb(self, self.PRESETS, 140, self._pick)
        self.preset.pack(side="left")
        self.e_from, self.e_to = ent(self, "From (DD-MM-YYYY)", 132), ent(self, "To (DD-MM-YYYY)", 132)
        self.e_from.pack(side="left", padx=(8, 4))
        self.e_to.pack(side="left", padx=4)
        btn(self, "Apply", self._custom, "secondary", width=62).pack(side="left", padx=(4, 0))
        self.preset.set(default)
        self._fill(default)

    def _fill(self, v):
        t = date.fromisoformat(db.today_iso())
        q = 3 * ((t.month - 1) // 3) + 1
        spans = {"This month": (t.replace(day=1), t), "Last 30 days": (t - timedelta(days=30), t),
                 "This quarter": (t.replace(month=q, day=1), t), "This year": (t.replace(month=1, day=1), t),
                 "All time": (None, None)}
        if v in spans:
            for e, d in zip((self.e_from, self.e_to), spans[v]):
                e.delete(0, "end")
                if d:
                    e.insert(0, db.fmt_date(d.isoformat()))

    def _pick(self, v):
        self._fill(v)
        if v != "Custom":
            self.on_change()

    def _custom(self):
        self.preset.set("Custom")
        self.on_change()

    def dates(self):
        a = db.parse_date(self.e_from.get(), "From date") if self.e_from.get().strip() else None
        b = db.parse_date(self.e_to.get(), "To date") if self.e_to.get().strip() else None
        if a and b and a > b:
            raise db.ValidationError("'From' date is after 'To' date.")
        return a, b

    def label(self):
        a, b = self.e_from.get().strip(), self.e_to.get().strip()
        return f"Period: {a or 'start'} to {b or 'today'}" if (a or b) else "Period: all time"


# ------------------------------------------------------------------ KPI card & charts
class KPICard(ctk.CTkFrame):
    def __init__(self, parent, title, color, ico):
        super().__init__(parent, fg_color=P["panel"], corner_radius=16, border_width=1, border_color=P["border"])
        self.color, self._job = color, None
        ctk.CTkFrame(self, height=4, fg_color=P[color], corner_radius=2).pack(fill="x", padx=18, pady=(0, 0))
        top = bar(self)
        top.pack(fill="x", padx=16, pady=(12, 0))
        lbl(top, title, 11, "bold", "muted").pack(side="left")
        ctk.CTkLabel(top, text="", image=icon(ico, "#64748B", "#8FA0C4", 18)).pack(side="right")
        self.value = lbl(self, "-", 23, "bold")
        self.value.pack(anchor="w", padx=16, pady=(4, 0))
        self.hint = lbl(self, "", 11, color="muted", wraplength=230, justify="left")
        self.hint.pack(anchor="w", padx=16, pady=(0, 12))

    def set(self, target, fmt, hint="", animate=True):
        self.hint.configure(text=hint)
        if self._job:
            self.after_cancel(self._job)
        if target is None:
            return self.value.configure(text="-")
        steps = 10 if animate else 1

        def tick(i=1):
            e = 1 - (1 - i / steps) ** 3
            self.value.configure(text=fmt(int(target * e)) if i < steps else fmt(target))
            self._job = self.after(22, tick, i + 1) if i < steps else None
        tick()


def _nice_scale(mx, n=4):
    if mx <= 0:
        return 1, 1
    raw = mx / n
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if raw <= m * mag)
    k = 1
    while step * k < mx:
        k += 1
    return step, k


def _mlabel(ym):
    names = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
    return f"{names[int(ym[5:7]) - 1]} {ym[2:4]}"


class Chart(tk.Canvas):
    """Lightweight canvas charts: kind = bars | donut | hbars. Animated, hover tooltips, theme aware."""

    def __init__(self, parent, kind, height=250):
        super().__init__(parent, height=height, highlightthickness=0, bd=0)
        self.kind, self.data, self.p, self.job, self.hits = kind, None, 1.0, None, []
        self.bind("<Configure>", lambda e: self.render())
        self.bind("<Motion>", self._hover)
        self.bind("<Leave>", lambda e: self.delete("tip"))
        HUB.append(self.render)

    def set(self, data, animate=True):
        self.data = data
        if self.job:
            self.after_cancel(self.job)
        self.p = 0.0 if animate else 1.0
        self._step()

    def _step(self):
        self.p = min(1.0, self.p + 0.14)
        self.render()
        self.job = self.after(24, self._step) if self.p < 1 else None

    def render(self):
        try:
            self.delete("all")
            self.configure(bg=R("panel"))
            self.hits = []
            w, h = self.winfo_width(), self.winfo_height()
            if w < 80 or h < 60:
                return
            if not self.data or self.data.get("empty"):
                msg = (self.data or {}).get("msg", "No data yet")
                self.create_text(w / 2, h / 2 - 8, text=msg, fill=R("muted"), font=(FONT, 11, "bold"))
                self.create_text(w / 2, h / 2 + 12, text="Charts fill in from your real records.", fill=R("muted"), font=(FONT, 9))
                return
            getattr(self, "_" + self.kind)(w, h, self.data, 1 - (1 - self.p) ** 3)
        except tk.TclError:
            pass

    def _hover(self, ev):
        self.delete("tip")
        for x0, y0, x1, y1, text in self.hits:
            if x0 <= ev.x <= x1 and y0 <= ev.y <= y1:
                t = self.create_text(min(ev.x + 14, self.winfo_width() - 8), max(ev.y - 12, 22), text=text, fill=R("text"),
                                     font=(FONT, 9, "bold"), anchor="e" if ev.x > self.winfo_width() * 0.6 else "w", tags="tip")
                bx = self.bbox(t)
                r = self.create_rectangle(bx[0] - 7, bx[1] - 5, bx[2] + 7, bx[3] + 5, fill=R("panel2"), outline=R("border"), tags="tip")
                self.tag_lower(r, t)
                return

    def _bars(self, w, h, d, e):
        ml, mr, mt, mb = 48, 12, 14, 30
        pw, ph = w - ml - mr, h - mt - mb
        series, labels, n = d["series"], d["labels"], len(d["labels"])
        mx = max([max(s["values"]) for s in series] + [1])
        step, k = _nice_scale(mx)
        top = step * k
        for i in range(k + 1):
            y = mt + ph - ph * i / k
            self.create_line(ml, y, w - mr, y, fill=R("border"), dash=(2, 4) if i else None)
            self.create_text(ml - 6, y, text=db.short_num(int(step * i)), fill=R("muted"), font=(FONT, 8), anchor="e")
        slot = pw / n
        gw = min(slot * 0.74, 46 * len(series))
        bw = gw / len(series)
        every = 1 if slot >= 40 else 2 if slot >= 22 else 3
        for i, lab in enumerate(labels):
            cx = ml + slot * (i + 0.5)
            if i % every == 0:
                self.create_text(cx, h - mb + 14, text=lab, fill=R("muted"), font=(FONT, 8))
            for j, s in enumerate(series):
                v = s["values"][i]
                x0 = cx - gw / 2 + j * bw + 1
                bh = ph * (v / top) * e
                if v > 0:
                    self.create_rectangle(x0, mt + ph - max(bh, 2), x0 + bw - 2, mt + ph, fill=R(s["color"]), outline="")
                self.hits.append((x0 - 2, mt, x0 + bw, mt + ph, f"{lab}\n{s['name']}: {d['sym']} {db.from_minor(v):,.2f}"))
        if len(series) > 1 or d.get("legend"):
            x = ml
            for s in series:
                self.create_rectangle(x, 3, x + 9, 12, fill=R(s["color"]), outline="")
                t = self.create_text(x + 14, 8, text=s["name"], fill=R("muted"), font=(FONT, 8, "bold"), anchor="w")
                x = self.bbox(t)[2] + 16

    def _donut(self, w, h, d, e):
        items, total = d["items"], sum(i[2] for i in d["items"])
        size = min(h - 24, w * 0.52)
        cx, cy = 14 + size / 2, h / 2
        thick = size * 0.17
        box = (cx - size / 2 + thick / 2, cy - size / 2 + thick / 2, cx + size / 2 - thick / 2, cy + size / 2 - thick / 2)
        start = 90.0
        for label, col, n in items:
            if n <= 0:
                continue
            ext = -min(359.9, 360.0 * n / total) * e
            self.create_arc(*box, start=start, extent=ext, style="arc", outline=R(col), width=thick)
            start += ext
        self.create_text(cx, cy - 8, text=str(total), fill=R("text"), font=(FONT, int(size * 0.17), "bold"))
        self.create_text(cx, cy + size * 0.1, text="invoices", fill=R("muted"), font=(FONT, 9))
        x, y = cx + size / 2 + 26, max(14, cy - 13 * len(items))
        for label, col, n in items:
            self.create_oval(x, y + 4, x + 11, y + 15, fill=R(col), outline="")
            self.create_text(x + 18, y + 10, text=label, fill=R("text"), font=(FONT, 10), anchor="w")
            self.create_text(w - 14, y + 10, text=f"{n}  ({n * 100 / total:.0f}%)", fill=R("muted"), font=(FONT, 9, "bold"), anchor="e")
            y += 26

    def _hbars(self, w, h, d, e):
        items = d["items"]
        mx = max([i[1] for i in items] + [1])
        rh = min(38, (h - 8) / max(len(items), 1))
        lw = min(150, w * 0.32)
        for n, (label, val, col, text) in enumerate(items):
            y = 6 + n * rh
            self.create_text(8, y + rh / 2, text=(label if len(label) <= 20 else label[:19] + "..."), fill=R("text"),
                             font=(FONT, 10), anchor="w")
            x0, x1 = lw, w - 96
            self.create_rectangle(x0, y + rh / 2 - 6, x1, y + rh / 2 + 6, fill=R("panel2"), outline="")
            if val > 0:
                self.create_rectangle(x0, y + rh / 2 - 6, x0 + max(6, (x1 - x0) * val / mx * e), y + rh / 2 + 6, fill=R(col), outline="")
            self.create_text(w - 8, y + rh / 2, text=text, fill=R("muted"), font=(FONT, 9, "bold"), anchor="e")
            self.hits.append((0, y, w, y + rh, f"{label}: {text}"))


# ================================================================== helpers for documents
def make_pdf(kind, doc_id, path=None):
    d = db.get_invoice(doc_id) if kind == "invoice" else db.get_estimate(doc_id)
    if not d:
        raise db.ValidationError("Record not found.")
    path = path or db.sub_dir("exports") / f"{d['number']}.pdf"
    return db.generate_doc_pdf(d, db.get_settings(), path, kind)


def client_dialog(parent, client=None, on_done=None):
    fields = [("name", "Client name *", "text", None), ("phone", "Phone", "text", None), ("email", "Email", "text", None),
              ("address", "Billing address", "multiline", None), ("ntn", "NTN (optional)", "text", None),
              ("strn", "STRN (optional)", "text", None), ("notes", "Notes", "multiline", None)]

    def save(vals):
        cid = db.save_customer(vals, client["id"] if client else None)
        if on_done:
            on_done(cid)
    FormDialog(parent, "Edit client" if client else "New client", fields, client, save)


# ================================================================== dashboard
class DashboardPage(ctk.CTkScrollableFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app, self.first = app, True
        top = bar(self)
        top.pack(fill="x", pady=(0, 10))
        self.range = RangeBar(top, self.refresh, "This month")
        self.range.pack(side="left")
        q = bar(top)
        q.pack(side="right")
        for text, cmd, kind in (("+ Invoice", lambda: app.new_doc("invoice"), "primary"), ("+ Quote", lambda: app.new_doc("quote"), "secondary"),
                                ("Record Payment", lambda: app.show("payments"), "secondary"), ("+ Expense", self.add_expense, "secondary"),
                                ("+ Client", lambda: client_dialog(self, None, lambda _i: self.refresh()), "secondary")):
            btn(q, text, cmd, kind).pack(side="left", padx=3)
        self.banner = card(self)
        lbl(self.banner, "Welcome aboard! Add a client and create your first invoice - every chart and KPI below is built "
                         "only from your real records.", 13, "bold", "accent", wraplength=900, justify="left").pack(padx=16, pady=12, anchor="w")
        grid = bar(self)
        grid.pack(fill="x")
        spec = [("revenue", "TOTAL REVENUE", "accent", "chart"), ("collected", "REVENUE COLLECTED", "green", "wallet"),
                ("outstanding", "OUTSTANDING RECEIVABLES", "amber", "card"), ("overdue", "OVERDUE", "red", "doc"),
                ("paid", "PAID INVOICES", "green", "doc"), ("unpaid", "UNPAID INVOICES", "cyan", "doc"),
                ("expenses", "EXPENSES", "violet", "wallet"), ("net", "NET PROFIT", "accent", "chart")]
        self.kpi = {}
        for n, (key, title, col, ico) in enumerate(spec):
            k = KPICard(grid, title, col, ico)
            k.grid(row=n // 4, column=n % 4, padx=5, pady=5, sticky="nsew")
            self.kpi[key] = k
        for c in range(4):
            grid.grid_columnconfigure(c, weight=1, uniform="k")
        self.c_inc = self._chart_row(self, "Monthly income vs expenses", "Cash collected against recorded expenses", "bars",
                                     "Payment status", "Invoices in the selected period", "donut")
        self.c_rev = self._chart_row(self, "Revenue trend", "Invoiced revenue per month", "bars",
                                     "Receivables aging", "Open balances by days past due (today)", "hbars")
        row = bar(self)
        row.pack(fill="x", pady=5)
        row.grid_columnconfigure(0, weight=2, uniform="r")
        row.grid_columnconfigure(1, weight=3, uniform="r")
        c, self.c_top = self._chart_card(row, "Top clients", "By invoiced revenue in the selected period", "hbars", 230)
        c.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        rc = card(row)
        rc.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        lbl(rc, "Recent invoices & payment activity", 15, "bold").pack(anchor="w", padx=16, pady=(14, 0))
        lbl(rc, "Latest records across the whole system", 11, color="muted").pack(anchor="w", padx=16, pady=(0, 6))
        self.table = DataTable(rc, [("kind", "Type", 70, "w"), ("ref", "Reference", 120, "w"), ("party", "Client", 160, "w"),
                                    ("day", "Date", 90, "center"), ("amount", "Amount", 110, "e"), ("status", "Status", 90, "center")],
                               height=6, empty="No activity yet - create an invoice to get started.")
        self.table.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    def _chart_card(self, parent, title, sub, kind, h=250):
        c = card(parent)
        lbl(c, title, 15, "bold").pack(anchor="w", padx=16, pady=(14, 0))
        lbl(c, sub, 11, color="muted").pack(anchor="w", padx=16, pady=(0, 4))
        ch = Chart(c, kind, h)
        ch.pack(fill="both", expand=True, padx=10, pady=(0, 12))
        return c, ch

    def _chart_row(self, parent, t1, s1, k1, t2, s2, k2):
        row = bar(parent)
        row.pack(fill="x", pady=5)
        row.grid_columnconfigure(0, weight=3, uniform="c")
        row.grid_columnconfigure(1, weight=2, uniform="c")
        a, ca = self._chart_card(row, t1, s1, k1)
        b, cb = self._chart_card(row, t2, s2, k2)
        a.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        b.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        return ca, cb

    def add_expense(self):
        expense_dialog(self, None, self.refresh)

    def refresh(self):
        try:
            a, b = self.range.dates()
        except db.ValidationError as exc:
            return error(self, str(exc), "Please check your input")
        an, s = db.analytics(a, b), sym()
        m = lambda v: db.money(v, s)
        anim, self.first = True, False
        if an["has_data"]:
            self.banner.pack_forget()
        else:
            self.banner.pack(fill="x", pady=(0, 6), before=self.kpi["revenue"].master)
        k = self.kpi
        k["revenue"].set(an["revenue"], m, "Invoiced in selected period (excl. drafts/void)", anim)
        k["collected"].set(an["collected"], m, f"This month: {m(an['month_income'])}", anim)
        k["outstanding"].set(an["outstanding"], m, "Open balances as of today", anim)
        k["overdue"].set(an["overdue_amount"], m, f"{an['overdue_count']} invoice(s) past due date", anim)
        k["paid"].set(an["paid_count"], str, f"{m(an['paid_amount'])} fully paid", anim)
        k["unpaid"].set(an["unpaid_count"], str, f"{m(an['unpaid_amount'])} still to collect", anim)
        k["expenses"].set(an["expenses"], m, f"This month: {m(an['month_expenses'])}", anim)
        k["net"].set(an["net_profit"], m, "Collected minus expenses" if an["net_profit"] is not None
                     else "Needs recorded payments or expenses", anim)
        ser = an["series"]
        labels = [_mlabel(x["month"]) for x in ser]
        if any(x["collected"] or x["expenses"] for x in ser):
            self.c_inc[0].set({"labels": labels, "sym": s, "series": [
                {"name": "Income (collected)", "color": "green", "values": [x["collected"] for x in ser]},
                {"name": "Expenses", "color": "amber", "values": [x["expenses"] for x in ser]}]})
        else:
            self.c_inc[0].set({"empty": True, "msg": "No income or expenses in this period"})
        if any(x["revenue"] for x in ser):
            self.c_rev[0].set({"labels": labels, "sym": s, "legend": True,
                               "series": [{"name": "Invoiced revenue", "color": "accent", "values": [x["revenue"] for x in ser]}]})
        else:
            self.c_rev[0].set({"empty": True, "msg": "No invoiced revenue in this period"})
        sc = an["status_counts"]
        order = [("paid", "Paid", "green"), ("partial", "Partially paid", "amber"), ("unpaid", "Sent", "accent"),
                 ("overdue", "Overdue", "red"), ("draft", "Draft", "muted")]
        items = [(lab, col, sc[key]) for key, lab, col in order if sc.get(key)]
        self.c_inc[1].set({"items": items} if items else {"empty": True, "msg": "No invoices in this period"})
        cols = ("green", "cyan", "amber", "red", "red")
        ag = [(n, v, cols[i], f"{db.money(v, s)}  ({c})") for i, (n, v, c) in enumerate(an["aging"])]
        self.c_rev[1].set({"items": ag} if sum(x[1] for x in ag) else {"empty": True, "msg": "No outstanding receivables"})
        top = [(c["name"], c["total"], "accent", db.money(c["total"], s)) for c in an["top_clients"]]
        self.c_top.set({"items": top} if top else {"empty": True, "msg": "No billed clients in this period"})
        self.table.set_rows([(n, [r["kind"], r["ref"], r["party"], db.fmt_date(r["day"]), m(r["amount"]),
                                  db.STATUS_LABELS.get(r["status"], r["status"].title())], r["status"])
                             for n, r in enumerate(an["recent"])])


# ================================================================== invoice / quotation editor
class LineRow:
    def __init__(self, page, parent, data=None):
        data = data or {}
        self.page, self.product_id = page, data.get("product_id")
        self.frame = bar(parent)
        self.desc, self.qty, self.price, self.tax = (ctk.StringVar(value=str(data.get(k, ""))) for k in ("description", "qty", "price", "tax"))
        f = self.frame
        f.grid_columnconfigure(0, weight=1)
        ent(f, "Description", 100, self.desc).grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=3)
        ent(f, "Qty", 66, self.qty).grid(row=0, column=1, padx=3)
        ent(f, "Unit price", 104, self.price).grid(row=0, column=2, padx=3)
        ent(f, "Tax %", 64, self.tax).grid(row=0, column=3, padx=3)
        self.total = lbl(f, "", 13, "bold", width=118, anchor="e")
        self.total.grid(row=0, column=4, padx=6)
        btn(f, "x", lambda: page.remove_row(self), "danger", width=32).grid(row=0, column=5)
        for v in (self.desc, self.qty, self.price, self.tax):
            v.trace_add("write", lambda *a: page.recalc())

    def blank(self):
        return not any(v.get().strip() for v in (self.desc, self.qty, self.price))

    def raw(self):
        return {"description": self.desc.get(), "qty": self.qty.get(), "unit_price_rs": self.price.get(),
                "tax_rate": self.tax.get(), "product_id": self.product_id}


class EditorPage(ctk.CTkFrame):
    """Create / edit an invoice (kind='invoice') or a quotation (kind='quote')."""

    def __init__(self, parent, app, kind):
        super().__init__(parent, fg_color="transparent")
        self.app, self.kind, self.editing_id, self.rows, self.cust_map = app, kind, None, [], {}
        self.quote = kind == "quote"
        self.heading = lbl(self, "", 20, "bold")
        self.heading.pack(anchor="w", pady=(0, 8))
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True)
        scroll.grid_columnconfigure(0, weight=1)
        scroll.grid_columnconfigure(1, weight=0, minsize=330)
        left = bar(scroll)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        c1 = card(left)
        c1.pack(fill="x", pady=(0, 10))
        lbl(c1, "Client & dates", 15, "bold").grid(row=0, column=0, columnspan=4, sticky="w", padx=16, pady=(14, 6))
        lbl(c1, "Client *", 12, "bold", "muted").grid(row=1, column=0, sticky="w", padx=16)
        self.customer = cmb(c1, [""], 300)
        self.customer.grid(row=2, column=0, padx=(16, 6), pady=(0, 8), sticky="w")
        btn(c1, "+ New client", self.new_client, "secondary").grid(row=2, column=1, padx=4, pady=(0, 8), sticky="w")
        lbl(c1, "Issue date", 12, "bold", "muted").grid(row=3, column=0, sticky="w", padx=16)
        lbl(c1, "Valid until" if self.quote else "Due date", 12, "bold", "muted").grid(row=3, column=1, sticky="w", padx=4)
        self.issue, self.due = ent(c1, "DD-MM-YYYY", 150), ent(c1, "DD-MM-YYYY", 150)
        self.issue.grid(row=4, column=0, padx=16, pady=(0, 14), sticky="w")
        self.due.grid(row=4, column=1, padx=4, pady=(0, 14), sticky="w")

        c2 = card(left)
        c2.pack(fill="x", pady=(0, 10))
        top = bar(c2)
        top.pack(fill="x", padx=16, pady=(14, 4))
        lbl(top, "Line items", 15, "bold").pack(side="left")
        btn(top, "+ Blank line", lambda: self.add_row(), "secondary").pack(side="right", padx=(6, 0))
        btn(top, "+ From catalog", self.pick_product, "accent").pack(side="right")
        hdr = bar(c2)
        hdr.pack(fill="x", padx=16)
        hdr.grid_columnconfigure(0, weight=1)
        for col, (t, wd) in enumerate((("DESCRIPTION", 0), ("QTY", 72), ("UNIT PRICE", 110), ("TAX %", 70), ("AMOUNT", 128), ("", 36))):
            lbl(hdr, t, 10, "bold", "muted", width=wd, anchor="w" if col == 0 else "center").grid(row=0, column=col, sticky="ew" if col == 0 else "")
        self.rows_frame = bar(c2)
        self.rows_frame.pack(fill="x", padx=16, pady=(2, 14))

        c3 = card(left)
        c3.pack(fill="x")
        lbl(c3, "Notes, payment terms & instructions", 15, "bold").pack(anchor="w", padx=16, pady=(14, 4))
        self.notes = self._text(c3, "Notes (shown on document)")
        self.instr = None if self.quote else self._text(c3, "Payment instructions")
        self.terms = self._text(c3, "Terms & conditions")

        right = card(scroll)
        right.grid(row=0, column=1, sticky="new")
        lbl(right, "Summary", 15, "bold").pack(anchor="w", padx=16, pady=(14, 8))
        lbl(right, "Discount", 12, "bold", "muted").pack(anchor="w", padx=16)
        self.dtype = ctk.CTkSegmentedButton(right, values=["None", "Fixed", "Percent"], command=lambda v: self.recalc(),
                                            selected_color=P["accent"], selected_hover_color=P["accent_h"],
                                            unselected_color=P["panel2"], unselected_hover_color=P["sec_h"],
                                            text_color=P["text"], font=F(12))
        self.dtype.set("None")
        self.dtype.pack(fill="x", padx=16, pady=(2, 6))
        self.dval = ctk.StringVar(value="0")
        ent(right, "Discount value", 100, self.dval).pack(fill="x", padx=16)
        self.dval.trace_add("write", lambda *a: self.recalc())
        lbl(right, "Default tax % for new lines (blank = none)", 12, "bold", "muted").pack(anchor="w", padx=16, pady=(10, 0))
        tr = bar(right)
        tr.pack(fill="x", padx=16)
        self.deftax = ent(tr, "e.g. 18", 80)
        self.deftax.pack(side="left")
        btn(tr, "Apply to all lines", self.apply_tax_all, "secondary").pack(side="left", padx=8)
        box = ctk.CTkFrame(right, fg_color=P["panel2"], corner_radius=12)
        box.pack(fill="x", padx=16, pady=14)
        self.lines = {}
        keys = [("subtotal", "Subtotal", 0), ("discount", "Discount", 0), ("tax", "Tax", 0), ("total", "Grand total", 1)]
        if not self.quote:
            keys += [("paid", "Amount paid", 0), ("balance", "Balance due", 1)]
        for key, text, bold in keys:
            r = bar(box)
            r.pack(fill="x", padx=12, pady=3)
            lbl(r, text, 13, "bold" if bold else "normal", "text" if bold else "muted").pack(side="left")
            self.lines[key] = lbl(r, "", 14 if bold else 13, "bold" if bold else "normal")
            self.lines[key].pack(side="right")
        self.msg = lbl(right, "", 12, color="red", wraplength=290, justify="left")
        self.msg.pack(anchor="w", padx=16)
        btn(right, "Save Quotation" if self.quote else "Save Invoice", lambda: self.save(False)).pack(fill="x", padx=16, pady=(8, 4))
        btn(right, "Save & Open PDF", lambda: self.save(False, True), "accent").pack(fill="x", padx=16, pady=4)
        if not self.quote:
            btn(right, "Save as Draft", lambda: self.save(True), "secondary").pack(fill="x", padx=16, pady=4)
        btn(right, "Reset form", self.reset, "ghost").pack(fill="x", padx=16, pady=(4, 14))
        self.reset()

    def _text(self, parent, title):
        lbl(parent, title, 12, "bold", "muted").pack(anchor="w", padx=16, pady=(6, 2))
        t = textbox(parent)
        t.pack(fill="x", padx=16, pady=(0, 8))
        return t

    @staticmethod
    def _set(tb, text):
        tb.delete("1.0", "end")
        tb.insert("1.0", text or "")

    def refresh(self):
        keep = self.customer.get()
        self.cust_map = {f"{c['name']}  (#{c['id']})": c["id"] for c in db.list_customers()}
        self.customer.configure(values=list(self.cust_map) or ["(add a client first)"])
        self.customer.set(keep if keep in self.cust_map else "")
        self.recalc()

    def new_client(self):
        def done(cid):
            self.refresh()
            for k, v in self.cust_map.items():
                if v == cid:
                    self.customer.set(k)
        client_dialog(self, None, done)

    def add_row(self, data=None):
        data = data or {}
        data.setdefault("tax", self.deftax.get().strip())
        r = LineRow(self, self.rows_frame, data)
        r.frame.pack(fill="x")
        self.rows.append(r)
        self.recalc()
        return r

    def remove_row(self, row):
        row.frame.destroy()
        self.rows.remove(row)
        if not self.rows:
            self.add_row()
        self.recalc()

    def apply_tax_all(self):
        for r in self.rows:
            r.tax.set(self.deftax.get().strip())

    def pick_product(self):
        d = Dialog(self, "Add from catalog", 680, 470)
        s = ent(d, "Search catalog...", 300)
        s.pack(anchor="w", padx=18, pady=(16, 8))
        t = DataTable(d, [("n", "Name", 240, "w"), ("sku", "SKU", 90, "w"), ("p", "Price", 120, "e"), ("tx", "Tax %", 60, "center")],
                      on_double=lambda: add(), empty="Your catalog is empty - add items under Products & Services.")
        t.pack(fill="both", expand=True, padx=18)
        items = {}

        def load(*_):
            items.clear()
            items.update({str(p["id"]): p for p in db.list_products(s.get())})
            t.set_rows([(p["id"], [p["name"], p["sku"], mny(p["unit_price"]), p["tax_rate"] if p["tax_rate"] is not None else "-"], None)
                        for p in items.values()])

        def add():
            iid = t.selected()
            if not iid:
                return info(d, "Select an item.")
            p = items[iid]
            tax = p["tax_rate"] if p["tax_rate"] is not None else self.deftax.get().strip()
            if len(self.rows) == 1 and self.rows[0].blank():
                self.remove_row(self.rows[0])
            self.add_row({"description": p["name"] + (f" - {p['description']}" if p["description"] else ""), "qty": "1",
                          "price": db.plain(p["unit_price"]), "tax": tax or "", "product_id": p["id"]})
        s.bind("<KeyRelease>", load)
        load()
        foot = bar(d)
        foot.pack(fill="x", padx=18, pady=12)
        btn(foot, "Done", d.destroy, "secondary").pack(side="right")
        btn(foot, "Add selected", add).pack(side="right", padx=8)

    def _discount(self):
        return self.dtype.get().lower(), (self.dval.get().strip() or "0")

    def recalc(self):
        s, items, problem = sym(), [], ""
        for r in self.rows:
            if r.blank():
                r.total.configure(text=db.money(0, s))
                continue
            try:
                q, p = db.to_decimal(r.qty.get() or "0"), db.to_decimal(r.price.get() or "0")
                if q < 0 or p < 0:
                    raise ValueError
                items.append({"qty": q, "unit_price": db.to_minor(p), "tax_rate": db.optional_rate(r.tax.get())})
                r.total.configure(text=db.money(db.line_total(q, db.to_minor(p)), s))
            except (ValueError, db.ValidationError):
                r.total.configure(text="invalid")
                problem = "Check quantity, price and tax values."
        try:
            t = db.calculate_totals(items, *self._discount())
        except (ValueError, db.ValidationError) as exc:
            return self.msg.configure(text=problem or str(exc))
        L = self.lines
        L["subtotal"].configure(text=db.money(t["subtotal"], s))
        L["discount"].configure(text="- " + db.money(t["discount_amount"], s))
        L["tax"].configure(text=db.money(t["tax_amount"], s))
        L["total"].configure(text=db.money(t["total"], s))
        if not self.quote:
            paid = db.get_invoice(self.editing_id)["amount_paid"] if self.editing_id else 0
            L["paid"].configure(text=db.money(paid, s))
            L["balance"].configure(text=db.money(t["total"] - paid, s))
        self.msg.configure(text=problem)

    def reset(self):
        self.editing_id = None
        s = db.get_settings()
        self.heading.configure(text=f"New {'quotation' if self.quote else 'invoice'}  -  {db.peek_number(self.kind)}")
        for r in list(self.rows):
            r.frame.destroy()
        self.rows.clear()
        today = date.fromisoformat(db.today_iso())
        days = int(s.get("quote_valid_days" if self.quote else "default_due_days") or 14)
        for e, v in ((self.issue, today), (self.due, today + timedelta(days=days))):
            e.delete(0, "end")
            e.insert(0, db.fmt_date(v.isoformat()))
        self.deftax.delete(0, "end")
        dt = (s.get("default_tax_rate") or "").strip()
        self.deftax.insert(0, "" if dt in ("", "0") else dt)
        self.dtype.set("None")
        self.dval.set("0")
        self._set(self.notes, "")
        if self.instr:
            self._set(self.instr, s.get("payment_instructions", ""))
        self._set(self.terms, s.get("invoice_terms", ""))
        self.customer.set("")
        self.add_row()

    def load(self, doc_id):
        d = db.get_estimate(doc_id) if self.quote else db.get_invoice(doc_id)
        if not d or d["status"] in ("void", "converted"):
            return error(self, "This record can no longer be edited.")
        self.reset()
        self.refresh()
        self.editing_id = doc_id
        self.heading.configure(text=f"Edit {'quotation' if self.quote else 'invoice'}  -  {d['number']}")
        key = f"{d['cust_name']}  (#{d['customer_id']})"
        if key not in self.cust_map:
            self.cust_map[key] = d["customer_id"]
            self.customer.configure(values=list(self.cust_map))
        self.customer.set(next((k for k, v in self.cust_map.items() if v == d["customer_id"]), key))
        for e, v in ((self.issue, d["issue_date"]), (self.due, d["valid_until"] if self.quote else d["due_date"])):
            e.delete(0, "end")
            e.insert(0, db.fmt_date(v))
        self.dtype.set(d["discount_type"].title())
        self.dval.set(d["discount_value"])
        self._set(self.notes, d["notes"])
        self._set(self.terms, d["terms"])
        if self.instr:
            self._set(self.instr, d["payment_instructions"])
        for r in list(self.rows):
            r.frame.destroy()
        self.rows.clear()
        for it in d["items"]:
            self.add_row({"description": it["description"], "qty": it["qty"], "price": db.plain(it["unit_price"]),
                          "tax": it["tax_rate"] or "", "product_id": it["product_id"]})
        self.recalc()

    def save(self, draft, open_pdf=False):
        def work():
            cid = self.cust_map.get(self.customer.get())
            if not cid:
                raise db.ValidationError("Please select (or create) a client.")
            dt, dv = self._discount()
            data = {"customer_id": cid, "issue_date": db.parse_date(self.issue.get(), "Issue date"), "discount_type": dt,
                    "discount_value": dv, "notes": self.notes.get("1.0", "end").strip(), "terms": self.terms.get("1.0", "end").strip()}
            raw = [r.raw() for r in self.rows if not r.blank()]
            if self.quote:
                data["valid_until"] = db.parse_date(self.due.get(), "Valid-until date")
                return db.save_estimate(data, raw, self.editing_id)
            data["due_date"] = db.parse_date(self.due.get(), "Due date")
            data["payment_instructions"] = self.instr.get("1.0", "end").strip()
            return db.save_invoice(data, raw, self.editing_id, as_draft=draft)
        ok, doc_id = run_safely(self, work)
        if not ok:
            return
        d = db.get_estimate(doc_id) if self.quote else db.get_invoice(doc_id)
        self.reset()
        self.app.show("estimates" if self.quote else "invoices")
        if open_pdf:
            ok2, path = run_safely(self, make_pdf, self.kind, doc_id)
            if ok2:
                open_path(path)
        else:
            lab = (db.QUOTE_LABELS if self.quote else db.STATUS_LABELS)[d["status"]]
            info(self.app, f"{'Quotation' if self.quote else 'Invoice'} {d['number']} saved ({lab}).")


# ================================================================== invoices list
class InvoicesPage(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        b1 = bar(self)
        b1.pack(fill="x", pady=(0, 6))
        self.search = ent(b1, "Search invoice no. or client...", 250)
        self.search.pack(side="left")
        self.search.bind("<KeyRelease>", lambda e: self.refresh())
        self.status = cmb(b1, ["All", "Draft", "Sent", "Partially Paid", "Paid", "Overdue", "Void"], 140, lambda v: self.refresh())
        self.status.set("All")
        self.status.pack(side="left", padx=8)
        self.range = RangeBar(b1, self.refresh, "All time")
        self.range.pack(side="left")
        btn(b1, "+ New Invoice", lambda: app.new_doc("invoice")).pack(side="right")
        b2 = bar(self)
        b2.pack(fill="x", pady=(0, 8))
        for text, cmd, kind in (("View", self.view, "primary"), ("Edit", self.edit, "secondary"), ("Mark Sent", self.sent, "secondary"),
                                ("Duplicate", self.dup, "secondary"), ("Record Payment", self.pay, "accent"), ("Save PDF", self.save_pdf, "secondary"),
                                ("Print", self.print, "secondary"), ("Void", self.void, "danger"), ("Delete Draft", self.delete, "danger")):
            btn(b2, text, cmd, kind).pack(side="left", padx=(0, 5))
        self.table = DataTable(self, [("n", "Invoice", 125, "w"), ("d", "Issued", 85, "center"), ("due", "Due", 85, "center"),
                                      ("c", "Client", 200, "w"), ("t", "Total", 110, "e"), ("p", "Paid", 110, "e"),
                                      ("b", "Balance", 110, "e"), ("s", "Status", 105, "center")], self.view,
                               empty="No invoices match - click '+ New Invoice' to create one.")
        self.table.pack(fill="both", expand=True)
        self.foot = lbl(self, "", 12, color="muted")
        self.foot.pack(anchor="w", pady=(6, 0))

    def refresh(self):
        try:
            a, b = self.range.dates()
        except db.ValidationError:
            a = b = None
        data, s = db.list_invoices(self.search.get(), self.status.get(), a, b), sym()
        self.table.set_rows([(r["id"], [r["number"], db.fmt_date(r["issue_date"]), db.fmt_date(r["due_date"]), r["cust_name"],
                                        db.money(r["total"], s), db.money(r["amount_paid"], s),
                                        db.money(r["balance"], s) if r["status"] not in ("void", "draft") else "-",
                                        db.STATUS_LABELS[r["status"]]], r["status"]) for r in data])
        live = [r for r in data if r["status"] not in ("void", "draft")]
        self.foot.configure(text=f"{len(data)} invoice(s)   |   Invoiced: {db.money(sum(r['total'] for r in live), s)}   |   "
                                 f"Outstanding: {db.money(sum(r['balance'] for r in live), s)}")

    def _sel(self):
        iid = self.table.selected()
        if not iid:
            info(self, "Select an invoice first.")
            return None
        return int(iid)

    def view(self):
        i = self._sel()
        if i:
            InvoiceDetail(self, self.app, i)

    def edit(self):
        i = self._sel()
        if i:
            self.app.edit_doc("invoice", i)

    def sent(self):
        i = self._sel()
        if i and run_safely(self, db.mark_sent, i)[0]:
            self.refresh()

    def dup(self):
        i = self._sel()
        if i and run_safely(self, db.duplicate_invoice, i)[0]:
            self.refresh()
            info(self, "Duplicated as a new draft. Select it and click Edit to adjust and finalise.")

    def pay(self):
        i = self._sel()
        if i:
            self.app.pages["payments"].preselect(i)
            self.app.show("payments")

    def save_pdf(self):
        i = self._sel()
        if i:
            path = ask_save(self, "Save invoice PDF", f"{db.get_invoice(i)['number']}.pdf", ".pdf", "PDF")
            if path and run_safely(self, make_pdf, "invoice", i, path)[0]:
                open_path(path)

    def print(self):
        i = self._sel()
        if i:
            ok, path = run_safely(self, make_pdf, "invoice", i)
            if ok:
                try:
                    open_path(path, print_it=True)
                except Exception:  # no print handler registered - open for manual printing
                    open_path(path)

    def void(self):
        i = self._sel()
        if not i:
            return
        inv = db.get_invoice(i)
        if confirm(self, f"Void invoice {inv['number']}?\nIt is excluded from revenue and balances but never deleted."
                         + (" Recorded payments stay in the history." if inv["payments"] else "")):
            run_safely(self, db.void_invoice, i)
            self.refresh()

    def delete(self):
        i = self._sel()
        if i and confirm(self, f"Permanently delete draft {db.get_invoice(i)['number']}? This cannot be undone."):
            run_safely(self, db.delete_draft_invoice, i)
            self.refresh()


class InvoiceDetail(Dialog):
    def __init__(self, parent, app, invoice_id):
        inv = db.get_invoice(invoice_id)
        super().__init__(parent, f"Invoice {inv['number']}", 860, 650)
        m = mny
        head = bar(self)
        head.pack(fill="x", padx=18, pady=(16, 4))
        lbl(head, inv["number"], 22, "bold").pack(side="left")
        lbl(head, f"   {db.STATUS_LABELS[inv['status']].upper()}", 13, "bold", STATUS_COL.get(inv["status"], "muted")).pack(side="left")
        lbl(self, f"{inv['cust_name']}   |   Issued {db.fmt_date(inv['issue_date'])}   |   Due {db.fmt_date(inv['due_date'])}", 13, color="muted").pack(anchor="w", padx=18)
        t = DataTable(self, [("d", "Description", 380, "w"), ("q", "Qty", 60, "center"), ("p", "Unit price", 120, "e"),
                             ("tx", "Tax %", 60, "center"), ("a", "Amount", 120, "e")], height=6)
        t.pack(fill="x", padx=18, pady=10)
        t.set_rows([(n, [i["description"], i["qty"], m(i["unit_price"]), i["tax_rate"] or "-", m(i["line_total"])], None) for n, i in enumerate(inv["items"])])
        tot = ctk.CTkFrame(self, fg_color=P["panel2"], corner_radius=12)
        tot.pack(anchor="e", padx=18)
        for lab, val, bold in (("Subtotal", inv["subtotal"], 0), ("Discount", -inv["discount_amount"], 0), ("Tax", inv["tax_amount"], 0),
                               ("Grand total", inv["total"], 1), ("Paid", inv["amount_paid"], 0), ("Balance due", inv["balance"], 1)):
            r = bar(tot)
            r.pack(fill="x", padx=14, pady=2)
            lbl(r, lab, 13, "bold" if bold else "normal", width=110, anchor="w").pack(side="left")
            lbl(r, m(val), 13, "bold" if bold else "normal", width=140, anchor="e").pack(side="right")
        lbl(self, "Payments", 14, "bold").pack(anchor="w", padx=18, pady=(10, 2))
        pt = DataTable(self, [("r", "Receipt", 120, "w"), ("d", "Date", 90, "center"), ("m", "Method", 110, "w"), ("ref", "Reference", 200, "w"),
                              ("a", "Amount", 120, "e"), ("s", "State", 80, "center")], height=3, empty="No payments recorded yet.")
        pt.pack(fill="x", padx=18)
        pt.set_rows([(p["id"], [p["receipt_no"], db.fmt_date(p["paid_date"]), p["method"], p["reference"], m(p["amount"]),
                                "Reversed" if p["voided"] else "OK"], "reversed" if p["voided"] else None) for p in inv["payments"]])
        foot = bar(self)
        foot.pack(fill="x", padx=18, pady=14, side="bottom")
        btn(foot, "Close", self.destroy, "secondary").pack(side="right")
        btn(foot, "Open PDF", lambda: self._open(invoice_id)).pack(side="right", padx=8)
        if inv["status"] in ("unpaid", "partial", "overdue"):
            btn(foot, "Record payment", lambda: (self.destroy(), app.pages["payments"].preselect(invoice_id), app.show("payments")), "accent").pack(side="right")

    def _open(self, invoice_id):
        ok, path = run_safely(self, make_pdf, "invoice", invoice_id)
        if ok:
            open_path(path)


# ================================================================== quotations list
class EstimatesPage(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        b1 = bar(self)
        b1.pack(fill="x", pady=(0, 6))
        self.search = ent(b1, "Search quote no. or client...", 250)
        self.search.pack(side="left")
        self.search.bind("<KeyRelease>", lambda e: self.refresh())
        self.status = cmb(b1, ["All", "Draft", "Sent", "Accepted", "Declined", "Expired", "Converted"], 140, lambda v: self.refresh())
        self.status.set("All")
        self.status.pack(side="left", padx=8)
        btn(b1, "+ New Quotation", lambda: app.new_doc("quote")).pack(side="right")
        b2 = bar(self)
        b2.pack(fill="x", pady=(0, 8))
        for text, cmd, kind in (("Edit", self.edit, "primary"), ("Mark Sent", lambda: self.setst("sent"), "secondary"),
                                ("Accepted", lambda: self.setst("accepted"), "secondary"), ("Declined", lambda: self.setst("declined"), "secondary"),
                                ("Convert to Invoice", self.convert, "accent"), ("Save PDF", self.pdf, "secondary"), ("Delete", self.delete, "danger")):
            btn(b2, text, cmd, kind).pack(side="left", padx=(0, 5))
        self.table = DataTable(self, [("n", "Quotation", 125, "w"), ("d", "Issued", 90, "center"), ("v", "Valid until", 90, "center"),
                                      ("c", "Client", 230, "w"), ("t", "Total", 120, "e"), ("s", "Status", 105, "center"), ("i", "Invoice", 120, "w")],
                               self.edit, empty="No quotations yet - click '+ New Quotation'.")
        self.table.pack(fill="both", expand=True)
        self.rows = {}

    def refresh(self):
        data, s = db.list_estimates(self.search.get(), self.status.get()), sym()
        self.rows = {str(r["id"]): r for r in data}
        inv_no = {r["id"]: r["number"] for r in db.list_invoices()}
        self.table.set_rows([(r["id"], [r["number"], db.fmt_date(r["issue_date"]), db.fmt_date(r["valid_until"]), r["cust_name"],
                                        db.money(r["total"], s), db.QUOTE_LABELS[r["status"]],
                                        inv_no.get(r["converted_invoice_id"], "")], r["status"]) for r in data])

    def _sel(self):
        iid = self.table.selected()
        if not iid:
            info(self, "Select a quotation first.")
            return None
        return int(iid)

    def edit(self):
        i = self._sel()
        if i:
            self.app.edit_doc("quote", i)

    def setst(self, st):
        i = self._sel()
        if i and run_safely(self, db.set_estimate_status, i, st)[0]:
            self.refresh()

    def convert(self):
        i = self._sel()
        if not i:
            return
        e = self.rows[str(i)]
        if confirm(self, f"Convert {e['number']} into an invoice?\nThe quotation will be marked Converted."):
            ok, inv_id = run_safely(self, db.convert_estimate, i)
            if ok:
                self.app.show("invoices")
                info(self.app, f"Created invoice {db.get_invoice(inv_id)['number']} from {e['number']}.")

    def pdf(self):
        i = self._sel()
        if i:
            path = ask_save(self, "Save quotation PDF", f"{self.rows[str(i)]['number']}.pdf", ".pdf", "PDF")
            if path and run_safely(self, make_pdf, "quote", i, path)[0]:
                open_path(path)

    def delete(self):
        i = self._sel()
        if i and confirm(self, f"Delete quotation {self.rows[str(i)]['number']}? This cannot be undone."):
            run_safely(self, db.delete_estimate, i)
            self.refresh()


# ================================================================== clients & products
class ClientsPage(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app, self.rows = app, {}
        b = bar(self)
        b.pack(fill="x", pady=(0, 10))
        self.search = ent(b, "Search name, phone, email, NTN...", 300)
        self.search.pack(side="left")
        self.search.bind("<KeyRelease>", lambda e: self.refresh())
        self.arch = ctk.CTkCheckBox(b, text="Show archived", command=self.refresh, fg_color=P["accent"], text_color=P["text"], font=F(12))
        self.arch.pack(side="left", padx=14)
        btn(b, "+ Add Client", lambda: client_dialog(self, None, lambda _i: self.refresh())).pack(side="right")
        btn(b, "Statement PDF", self.statement, "secondary").pack(side="right", padx=5)
        btn(b, "Archive / Restore", self.archive, "danger").pack(side="right", padx=5)
        btn(b, "Edit", self.edit, "secondary").pack(side="right", padx=5)
        btn(b, "View", self.view, "primary").pack(side="right", padx=5)
        self.table = DataTable(self, [("name", "Name", 210, "w"), ("phone", "Phone", 110, "w"), ("email", "Email", 190, "w"),
                                      ("ntn", "NTN", 90, "w"), ("count", "Invoices", 65, "center"), ("billed", "Billed", 120, "e"),
                                      ("balance", "Balance Due", 120, "e"), ("state", "Status", 75, "center")], self.view,
                               empty="No clients yet - click '+ Add Client'.")
        self.table.pack(fill="both", expand=True)

    def refresh(self):
        data, s = db.list_customers(self.search.get(), bool(self.arch.get())), sym()
        self.rows = {str(r["id"]): r for r in data}
        self.table.set_rows([(r["id"], [r["name"], r["phone"], r["email"], r["ntn"], r["invoice_count"], db.money(r["billed"], s),
                                        db.money(r["balance"], s), "Archived" if r["archived"] else "Active"],
                              "overdue" if r["balance"] > 0 else None) for r in data])

    def _sel(self):
        iid = self.table.selected()
        if not iid:
            info(self, "Select a client first.")
            return None
        return self.rows[iid]

    def edit(self):
        c = self._sel()
        if c:
            client_dialog(self, c, lambda _i: self.refresh())

    def archive(self):
        c = self._sel()
        if c:
            flag = not c["archived"]
            if confirm(self, f"{'Archive' if flag else 'Restore'} '{c['name']}'? Their invoice history is kept."):
                run_safely(self, db.set_customer_archived, c["id"], flag)
                self.refresh()

    def view(self):
        c = self._sel()
        if not c:
            return
        d, s = Dialog(self, f"Client - {c['name']}", 800, 540), sym()
        lbl(d, c["name"], 20, "bold").pack(anchor="w", padx=18, pady=(16, 0))
        lbl(d, "   |   ".join(x for x in (c["phone"], c["email"], c["address"].replace("\n", ", "),
                                          f"NTN {c['ntn']}" if c["ntn"] else "", f"STRN {c['strn']}" if c["strn"] else "") if x) or "No contact details saved",
            12, color="muted", wraplength=740, justify="left").pack(anchor="w", padx=18)
        lbl(d, f"Billed {db.money(c['billed'], s)}   |   Balance due {db.money(c['balance'], s)}", 14, "bold", "accent").pack(anchor="w", padx=18, pady=8)
        t = DataTable(d, [("n", "Invoice", 140, "w"), ("d", "Date", 100, "center"), ("due", "Due", 100, "center"), ("t", "Total", 120, "e"),
                          ("p", "Paid", 120, "e"), ("s", "Status", 100, "center")], empty="No invoices for this client yet.")
        t.pack(fill="both", expand=True, padx=18, pady=(0, 16))
        t.set_rows([(i["id"], [i["number"], db.fmt_date(i["issue_date"]), db.fmt_date(i["due_date"]), db.money(i["total"], s),
                               db.money(i["amount_paid"], s), db.STATUS_LABELS[i["status"]]], i["status"]) for i in db.customer_invoices(c["id"])])

    def statement(self):
        c = self._sel()
        if c:
            path = ask_save(self, "Save statement", f"Statement_{c['name'].replace(' ', '_')}.pdf", ".pdf", "PDF")
            if path and run_safely(self, lambda: db.generate_report_pdf(db.customer_statement(c["id"]), db.get_settings(), path))[0]:
                open_path(path)


class ProductsPage(ctk.CTkFrame):
    FIELDS = [("name", "Item name *", "text", None), ("sku", "SKU / code", "text", None), ("category", "Category", "text", None),
              ("unit_price", "Unit price *", "text", None), ("tax_rate", "Tax rate % (blank = none)", "text", None),
              ("description", "Description", "multiline", None)]

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.rows = {}
        b = bar(self)
        b.pack(fill="x", pady=(0, 10))
        self.search = ent(b, "Search name, SKU, category...", 300)
        self.search.pack(side="left")
        self.search.bind("<KeyRelease>", lambda e: self.refresh())
        self.arch = ctk.CTkCheckBox(b, text="Show archived", command=self.refresh, fg_color=P["accent"], text_color=P["text"], font=F(12))
        self.arch.pack(side="left", padx=14)
        btn(b, "+ Add Item", lambda: self._dialog()).pack(side="right")
        btn(b, "Archive / Restore", self.archive, "danger").pack(side="right", padx=5)
        btn(b, "Edit", self.edit, "secondary").pack(side="right", padx=5)
        self.table = DataTable(self, [("name", "Name", 230, "w"), ("sku", "SKU", 90, "w"), ("cat", "Category", 120, "w"), ("price", "Unit Price", 120, "e"),
                                      ("tax", "Tax %", 60, "center"), ("desc", "Description", 250, "w"), ("state", "Status", 75, "center")], self.edit,
                               empty="Your catalog is empty - click '+ Add Item'.")
        self.table.pack(fill="both", expand=True)

    def refresh(self):
        data, s = db.list_products(self.search.get(), bool(self.arch.get())), sym()
        self.rows = {str(r["id"]): r for r in data}
        self.table.set_rows([(r["id"], [r["name"], r["sku"], r["category"], db.money(r["unit_price"], s), r["tax_rate"] if r["tax_rate"] is not None else "-",
                                        (r["description"] or "")[:60], "Archived" if r["archived"] else "Active"], "void" if r["archived"] else None) for r in data])

    def _sel(self):
        iid = self.table.selected()
        if not iid:
            info(self, "Select an item first.")
            return None
        return self.rows[iid]

    def _dialog(self, item=None):
        vals = dict(item, unit_price=db.plain(item["unit_price"]), tax_rate=item["tax_rate"] or "") if item else None

        def save(v):
            db.save_product(v, item["id"] if item else None)
            self.refresh()
        FormDialog(self, "Edit item" if item else "New item", self.FIELDS, vals, save)

    def edit(self):
        p = self._sel()
        if p:
            self._dialog(p)

    def archive(self):
        p = self._sel()
        if p:
            flag = not p["archived"]
            if confirm(self, f"{'Archive' if flag else 'Restore'} '{p['name']}'? Existing invoices are not affected."):
                run_safely(self, db.set_product_archived, p["id"], flag)
                self.refresh()


# ================================================================== payments
class PaymentsPage(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app, self.open_map, self._pending, self.rows = app, {}, None, {}
        form = card(self)
        form.pack(fill="x", pady=(0, 12))
        lbl(form, "Record a payment", 15, "bold").grid(row=0, column=0, columnspan=5, sticky="w", padx=16, pady=(14, 6))
        for c, t in enumerate(("Invoice (open balances)", "Amount", "Date", "Method", "Reference / TxID")):
            lbl(form, t, 12, "bold", "muted").grid(row=1, column=c, sticky="w", padx=(16 if c == 0 else 6, 6))
        self.invoice = cmb(form, [""], 340, self._on_invoice)
        self.invoice.grid(row=2, column=0, padx=(16, 6), pady=(0, 8), sticky="w")
        self.amount = ent(form, "0.00", 120)
        self.amount.grid(row=2, column=1, padx=6, sticky="w")
        self.date = ent(form, "DD-MM-YYYY", 120)
        self.date.grid(row=2, column=2, padx=6, sticky="w")
        self.method = cmb(form, list(db.PAYMENT_METHODS), 150)
        self.method.set("Cash")
        self.method.grid(row=2, column=3, padx=6, sticky="w")
        self.ref = ent(form, "Optional", 190)
        self.ref.grid(row=2, column=4, padx=(6, 16), sticky="w")
        lbl(form, "Notes", 12, "bold", "muted").grid(row=3, column=0, sticky="w", padx=16)
        self.notes = ent(form, "Optional notes", 340)
        self.notes.grid(row=4, column=0, padx=16, pady=(0, 14), sticky="w")
        self.info = lbl(form, "", 12, color="muted")
        self.info.grid(row=4, column=1, columnspan=3, sticky="w", padx=6)
        btn(form, "Record Payment", self.record).grid(row=4, column=4, padx=16, pady=(0, 14), sticky="e")
        b = bar(self)
        b.pack(fill="x", pady=(0, 8))
        lbl(b, "Payment history", 15, "bold").pack(side="left")
        self.search = ent(b, "Search receipt, invoice, client, reference...", 300)
        self.search.pack(side="left", padx=14)
        self.search.bind("<KeyRelease>", lambda e: self.history())
        btn(b, "Reverse Payment", self.reverse, "danger").pack(side="right")
        btn(b, "Receipt PDF", self.receipt).pack(side="right", padx=6)
        self.table = DataTable(self, [("r", "Receipt", 115, "w"), ("d", "Date", 90, "center"), ("i", "Invoice", 115, "w"), ("c", "Client", 200, "w"),
                                      ("m", "Method", 105, "w"), ("ref", "Reference", 150, "w"), ("a", "Amount", 115, "e"), ("s", "State", 75, "center")],
                               self.receipt, empty="No payments recorded yet.")
        self.table.pack(fill="both", expand=True)

    def preselect(self, invoice_id):
        self._pending = invoice_id

    def refresh(self):
        s = sym()
        self.open_map = {f"{r['number']}  |  {r['cust_name']}  |  due {db.money(r['balance'], s)}": r for r in db.open_invoices_for_payment()}
        vals = list(self.open_map) or ["(no invoices with an open balance)"]
        self.invoice.configure(values=vals)
        if self._pending:
            for k, r in self.open_map.items():
                if r["id"] == self._pending:
                    self.invoice.set(k)
            self._pending = None
        elif self.invoice.get() not in self.open_map:
            self.invoice.set(vals[0] if self.open_map else "")
        if not self.date.get():
            self.date.insert(0, db.fmt_date(db.today_iso()))
        self._on_invoice()
        self.history()

    def _on_invoice(self, *_):
        r, s = self.open_map.get(self.invoice.get()), sym()
        self.amount.delete(0, "end")
        if r:
            self.amount.insert(0, db.plain(r["balance"]))
            self.info.configure(text=f"Total {db.money(r['total'], s)}  |  Paid {db.money(r['amount_paid'], s)}  |  Balance {db.money(r['balance'], s)}")
        else:
            self.info.configure(text="")

    def history(self):
        data, s = db.list_payments(self.search.get()), sym()
        self.rows = {str(p["id"]): p for p in data}
        self.table.set_rows([(p["id"], [p["receipt_no"], db.fmt_date(p["paid_date"]), p["invoice_number"], p["cust_name"], p["method"], p["reference"],
                                        db.money(p["amount"], s), "Reversed" if p["voided"] else "OK"], "reversed" if p["voided"] else "received") for p in data])

    def record(self):
        r = self.open_map.get(self.invoice.get())
        if not r:
            return info(self, "Choose an invoice with an open balance.")
        ok, pid = run_safely(self, lambda: db.add_payment(r["id"], db.to_minor(db.positive_decimal(self.amount.get(), "Amount")),
                                                          db.parse_date(self.date.get(), "Payment date"), self.method.get(), self.ref.get(), self.notes.get()))
        if ok:
            self.ref.delete(0, "end")
            self.notes.delete(0, "end")
            self.refresh()
            if confirm(self, "Payment recorded. Open the receipt PDF now?", "Payment saved"):
                self._receipt(pid)

    def _receipt(self, pid, path=None):
        def work():
            rc = db.get_receipt_data(pid)
            return db.generate_receipt_pdf(rc, db.get_settings(), path or db.sub_dir("exports") / f"{rc['receipt_no']}.pdf")
        ok, p = run_safely(self, work)
        if ok:
            open_path(p)

    def receipt(self):
        iid = self.table.selected()
        if not iid:
            return info(self, "Select a payment first.")
        path = ask_save(self, "Save receipt", f"{self.rows[iid]['receipt_no']}.pdf", ".pdf", "PDF")
        if path:
            self._receipt(int(iid), path)

    def reverse(self):
        iid = self.table.selected()
        if not iid:
            return info(self, "Select a payment first.")
        p = self.rows[iid]
        if p["voided"]:
            return info(self, "That payment is already reversed.")
        if confirm(self, f"Reverse payment {p['receipt_no']}?\nThe record stays in history, but the invoice balance is restored."):
            run_safely(self, db.void_payment, int(iid))
            self.refresh()


# ================================================================== expenses
def expense_dialog(parent, exp=None, on_done=None):
    fields = [("expense_date", "Date (DD-MM-YYYY) *", "text", None), ("category", "Category *", "combo", list(db.EXPENSE_CATEGORIES)),
              ("vendor", "Vendor / paid to", "text", None), ("amount", "Amount *", "text", None), ("description", "Description", "multiline", None)]
    vals = ({"expense_date": db.fmt_date(exp["expense_date"]), "category": exp["category"], "vendor": exp["vendor"],
             "amount": db.plain(exp["amount"]), "description": exp["description"]} if exp else {"expense_date": db.fmt_date(db.today_iso())})

    def save(v):
        db.save_expense(v, exp["id"] if exp else None)
        if on_done:
            on_done()
    FormDialog(parent, "Edit expense" if exp else "New expense", fields, vals, save)


class ExpensesPage(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.rows = {}
        b = bar(self)
        b.pack(fill="x", pady=(0, 6))
        self.search = ent(b, "Search vendor, description...", 230)
        self.search.pack(side="left")
        self.search.bind("<KeyRelease>", lambda e: self.refresh())
        self.cat = cmb(b, ["All"] + list(db.EXPENSE_CATEGORIES), 150, lambda v: self.refresh())
        self.cat.set("All")
        self.cat.pack(side="left", padx=8)
        self.range = RangeBar(b, self.refresh, "This year")
        self.range.pack(side="left")
        btn(b, "+ Add Expense", lambda: expense_dialog(self, None, self.refresh)).pack(side="right")
        b2 = bar(self)
        b2.pack(fill="x", pady=(0, 8))
        btn(b2, "Edit", self.edit, "secondary").pack(side="left", padx=(0, 5))
        btn(b2, "Delete", self.delete, "danger").pack(side="left")
        self.table = DataTable(self, [("d", "Date", 95, "center"), ("c", "Category", 130, "w"), ("v", "Vendor", 190, "w"),
                                      ("x", "Description", 330, "w"), ("a", "Amount", 130, "e")], self.edit,
                               empty="No expenses in this selection - click '+ Add Expense'.")
        self.table.pack(fill="both", expand=True)
        self.foot = lbl(self, "", 12, color="muted")
        self.foot.pack(anchor="w", pady=(6, 0))

    def refresh(self):
        try:
            a, b = self.range.dates()
        except db.ValidationError:
            a = b = None
        data, s = db.list_expenses(self.search.get(), self.cat.get(), a, b), sym()
        self.rows = {str(r["id"]): r for r in data}
        self.table.set_rows([(r["id"], [db.fmt_date(r["expense_date"]), r["category"], r["vendor"], (r["description"] or "")[:80], db.money(r["amount"], s)], None) for r in data])
        by = {}
        for r in data:
            by[r["category"]] = by.get(r["category"], 0) + r["amount"]
        top = max(by.items(), key=lambda x: x[1]) if by else None
        self.foot.configure(text=f"{len(data)} expense(s)   |   Total: {db.money(sum(r['amount'] for r in data), s)}" +
                                 (f"   |   Largest category: {top[0]} ({db.money(top[1], s)})" if top else ""))

    def _sel(self):
        iid = self.table.selected()
        if not iid:
            info(self, "Select an expense first.")
            return None
        return self.rows[iid]

    def edit(self):
        e = self._sel()
        if e:
            expense_dialog(self, e, self.refresh)

    def delete(self):
        e = self._sel()
        if e and confirm(self, f"Delete this {e['category']} expense of {mny(e['amount'])}? This cannot be undone."):
            run_safely(self, db.delete_expense, e["id"])
            self.refresh()


# ================================================================== reports
class ReportsPage(ctk.CTkFrame):
    NAMES = ["Revenue (invoiced)", "Payments received", "Outstanding payments", "Overdue invoices", "Receivables aging",
             "Expenses", "Tax summary", "Client performance", "Client statement", "Monthly summary"]

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.report, self.cust_map = None, {}
        bx = card(self)
        bx.pack(fill="x", pady=(0, 10))
        inner = bar(bx)
        inner.pack(fill="x", padx=14, pady=12)
        self.kind = cmb(inner, self.NAMES, 200, lambda v: self._toggle())
        self.kind.set(self.NAMES[0])
        self.kind.pack(side="left")
        self.client = cmb(inner, [""], 200)
        self.range = RangeBar(inner, self.run, "This month")
        self.range.pack(side="left", padx=8)
        btn(inner, "Run", self.run, width=60).pack(side="left", padx=4)
        btn(inner, "Export PDF", self.pdf, "secondary").pack(side="right")
        btn(inner, "Export CSV", self.csv, "secondary").pack(side="right", padx=6)
        self.title = lbl(self, "", 16, "bold")
        self.title.pack(anchor="w", pady=(2, 4))
        self.holder = bar(self)
        self.holder.pack(fill="both", expand=True)
        self.table = None
        self.totals = lbl(self, "", 13, "bold", "accent", justify="left")
        self.totals.pack(anchor="w", pady=(8, 0))

    def refresh(self):
        self.cust_map = {f"{c['name']}  (#{c['id']})": c["id"] for c in db.list_customers(include_archived=True)}
        self.client.configure(values=list(self.cust_map) or [""])
        if self.client.get() not in self.cust_map:
            self.client.set(next(iter(self.cust_map), ""))
        self._toggle()
        self.run(silent=True)

    def _toggle(self):
        if self.kind.get() == "Client statement":
            self.client.pack(side="left", padx=(8, 0), after=self.kind)
        else:
            self.client.pack_forget()

    def _build(self):
        a, b = self.range.dates()
        k = self.kind.get()
        simple = {"Outstanding payments": db.outstanding_report, "Overdue invoices": db.overdue_report, "Receivables aging": db.aging_report}
        ranged = {"Revenue (invoiced)": db.sales_report, "Payments received": db.payments_report, "Expenses": db.expenses_report,
                  "Tax summary": db.tax_report, "Client performance": db.client_report, "Monthly summary": db.monthly_summary}
        if k in simple:
            return simple[k]()
        if k == "Client statement":
            cid = self.cust_map.get(self.client.get())
            if not cid:
                raise db.ValidationError("Choose a client for the statement.")
            return db.customer_statement(cid, a, b)
        return ranged[k](a, b)

    def run(self, silent=False):
        try:
            rep = self._build()
        except Exception as exc:  # noqa: BLE001
            if not silent:
                run_safely(self, lambda: (_ for _ in ()).throw(exc))
            return
        self.report = rep
        self.title.configure(text=rep["title"])
        if self.table:
            self.table.destroy()
        right = {"Total", "Paid", "Balance", "Amount", "Invoiced", "Difference", "Collected", "Expenses", "Outstanding", "Share",
                 "Days Overdue", "Taxable Sales", "Tax Charged", "Total Billed", "Invoices"}
        cols = [(f"c{i}", h, 110 if i else 150, "e" if h in right or h.startswith("Net") else "w") for i, h in enumerate(rep["headers"])]
        self.table = DataTable(self.holder, cols, empty="No records for this selection.")
        self.table.pack(fill="both", expand=True)
        self.table.set_rows([(n, r, None) for n, r in enumerate(rep["rows"])])
        self.totals.configure(text="\n".join(f"{a.strip()}: {b}" for a, b in rep["totals"]))

    def _name(self, ext):
        return self.report["title"].split(" (")[0].replace(" ", "_") + ext

    def csv(self):
        if not self.report:
            return info(self, "Run a report first.")
        path = ask_save(self, "Export CSV", self._name(".csv"), ".csv", "CSV")
        if path and run_safely(self, db.export_csv, self.report, path)[0]:
            info(self, f"Saved:\n{path}")

    def pdf(self):
        if not self.report:
            return info(self, "Run a report first.")
        path = ask_save(self, "Export PDF", self._name(".pdf"), ".pdf", "PDF")
        if path and run_safely(self, db.generate_report_pdf, self.report, db.get_settings(), path, self.range.label())[0]:
            open_path(path)


# ================================================================== settings (+ data management)
class SettingsPage(ctk.CTkFrame):
    FIELDS = [
        ("Business profile", [("business_name", "Business name", "text"), ("business_address", "Address", "multi"), ("business_phone", "Phone", "text"),
                              ("business_whatsapp", "WhatsApp", "text"), ("business_email", "Email", "text"), ("business_ntn", "NTN (optional)", "text"),
                              ("business_strn", "STRN (optional)", "text")]),
        ("Numbering, currency & tax", [("currency_symbol", "Default currency symbol (shown as 'Rs. 1,500.00')", "text"),
                                       ("invoice_prefix", "Invoice number prefix (letters/digits)", "text"),
                                       ("invoice_next", "Next invoice sequence number (minimum)", "text"),
                                       ("quote_prefix", "Quotation number prefix", "text"), ("quote_valid_days", "Quotation validity (days)", "text"),
                                       ("default_tax_rate", "Default tax rate % (0 = no tax)", "text"), ("tax_label", "Tax label (GST / Sales Tax)", "text"),
                                       ("default_due_days", "Default payment terms (days)", "text")]),
        ("Document text", [("payment_instructions", "Payment instructions", "multi"), ("invoice_terms", "Invoice terms & conditions", "multi"),
                           ("invoice_footer", "Document footer", "multi")]),
    ]

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app, self.w, self.logo, self.files = app, {}, "", {}
        sc = ctk.CTkScrollableFrame(self, fg_color="transparent")
        sc.pack(fill="both", expand=True)
        c = card(sc)
        c.pack(fill="x", pady=(0, 10))
        lbl(c, "Appearance", 15, "bold").pack(anchor="w", padx=16, pady=(14, 4))
        row = bar(c)
        row.pack(anchor="w", padx=16, pady=(0, 14))
        self.theme = ctk.CTkSegmentedButton(row, values=["Light", "Dark"], command=lambda v: app.set_theme(v.lower()), selected_color=P["accent"],
                                            selected_hover_color=P["accent_h"], unselected_color=P["panel2"], unselected_hover_color=P["sec_h"],
                                            text_color=P["text"], font=F(12))
        self.theme.pack(side="left")
        lbl(row, "  Saved automatically and restored on next launch.", 12, color="muted").pack(side="left")
        for title, fields in self.FIELDS:
            c = card(sc)
            c.pack(fill="x", pady=(0, 10))
            lbl(c, title, 15, "bold").pack(anchor="w", padx=16, pady=(14, 4))
            for key, text, kind in fields:
                lbl(c, text, 12, "bold", "muted").pack(anchor="w", padx=16, pady=(6, 2))
                w = textbox(c, 66) if kind == "multi" else ent(c, width=420)
                w.pack(fill="x", padx=16, pady=(0, 4), anchor="w")
                self.w[key] = (kind, w)
            ctk.CTkFrame(c, height=8, fg_color="transparent").pack()
        c = card(sc)
        c.pack(fill="x", pady=(0, 10))
        lbl(c, "Branding / logo (shown on PDFs)", 15, "bold").pack(anchor="w", padx=16, pady=(14, 4))
        self.logo_lbl = lbl(c, "No logo selected", 12, color="muted")
        self.logo_lbl.pack(anchor="w", padx=16)
        r = bar(c)
        r.pack(anchor="w", padx=16, pady=(6, 14))
        btn(r, "Choose logo...", self.choose_logo, "secondary").pack(side="left")
        btn(r, "Remove logo", self.clear_logo, "danger").pack(side="left", padx=8)
        btn(sc, "Save Settings", self.save).pack(anchor="e", pady=(0, 14))

        c = card(sc)
        c.pack(fill="x", pady=(0, 10))
        lbl(c, "Data management & backup", 15, "bold").pack(anchor="w", padx=16, pady=(14, 2))
        lbl(c, str(db.data_dir()), 12, color="muted").pack(anchor="w", padx=16)
        r = bar(c)
        r.pack(anchor="w", padx=16, pady=12)
        btn(r, "Back up now...", self.backup_as).pack(side="left")
        btn(r, "Quick backup", self.quick, "secondary").pack(side="left", padx=8)
        btn(r, "Restore from file...", self.restore_file, "danger").pack(side="left")
        btn(r, "Open data folder", lambda: open_path(db.data_dir()), "ghost").pack(side="left", padx=8)
        self.table = DataTable(c, [("n", "Saved backups (app folder)", 380, "w"), ("t", "Created", 150, "center"), ("s", "Size", 80, "e")], height=4,
                               empty="No backups yet - click 'Quick backup'.")
        self.table.pack(fill="x", padx=14, pady=(0, 8))
        btn(c, "Restore selected backup", self.restore_selected, "danger").pack(anchor="e", padx=14, pady=(0, 14))

    def refresh(self):
        s = db.get_settings()
        for key, (kind, w) in self.w.items():
            if kind == "multi":
                w.delete("1.0", "end")
                w.insert("1.0", s.get(key, ""))
            else:
                w.delete(0, "end")
                w.insert(0, s.get(key, ""))
        self.logo = s.get("logo_path", "")
        self.logo_lbl.configure(text=self.logo or "No logo selected")
        self.theme.set("Dark" if ctk.get_appearance_mode() == "Dark" else "Light")
        self.files, rows = {}, []
        from datetime import datetime
        for p in sorted(db.sub_dir("backups").glob("*.db"), key=lambda x: x.stat().st_mtime, reverse=True):
            st = p.stat()
            self.files[p.name] = p
            rows.append((p.name, [p.name, datetime.fromtimestamp(st.st_mtime).strftime("%d-%m-%Y %H:%M"), f"{st.st_size / 1024:.0f} KB"], None))
        self.table.set_rows(rows)

    def choose_logo(self):
        p = filedialog.askopenfilename(parent=self, title="Choose logo", filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.gif")])
        if not p:
            return

        def work():
            with Image.open(p) as im:
                im.verify()
            dest = db.sub_dir("assets") / f"logo{os.path.splitext(p)[1].lower()}"
            shutil.copyfile(p, dest)
            return str(dest)
        ok, dest = run_safely(self, work)
        if ok:
            self.logo = dest
            self.logo_lbl.configure(text=dest + "   (click Save Settings to apply)")

    def clear_logo(self):
        self.logo = ""
        self.logo_lbl.configure(text="No logo selected   (click Save Settings to apply)")

    def save(self):
        def work():
            v = {k: (w.get("1.0", "end").strip() if kind == "multi" else w.get().strip()) for k, (kind, w) in self.w.items()}
            if not v["business_name"]:
                raise db.ValidationError("Business name is required.")
            if not v["currency_symbol"]:
                raise db.ValidationError("Currency symbol is required.")
            for k, name in (("invoice_prefix", "Invoice prefix"), ("quote_prefix", "Quotation prefix")):
                import re
                if not re.fullmatch(r"[A-Za-z0-9]{1,8}", v[k]):
                    raise db.ValidationError(f"{name} must be 1-8 letters or digits.")
            v["default_tax_rate"] = db.optional_rate(v["default_tax_rate"], "Default tax rate") or "0"
            for k, name, zero in (("default_due_days", "Payment terms", True), ("quote_valid_days", "Quotation validity", True), ("invoice_next", "Next invoice number", False)):
                v[k] = str(int(db.positive_decimal(v[k] or "0", name, allow_zero=zero)))
            v["logo_path"] = self.logo
            db.save_settings(v)
        if run_safely(self, work)[0]:
            self.app.refresh_current()
            info(self, "Settings saved.")

    def backup_as(self):
        path = ask_save(self, "Save backup", db.default_backup_name(), ".db", "Database backup")
        if path and run_safely(self, db.backup_database, path)[0]:
            info(self, f"Backup saved:\n{path}")

    def quick(self):
        path = db.sub_dir("backups") / db.default_backup_name()
        if run_safely(self, db.backup_database, path)[0]:
            self.refresh()
            info(self, f"Backup saved:\n{path}")

    def _restore(self, path):
        if not confirm(self, "Restore this backup?\n\nAll current data will be replaced. A safety copy of your current database is saved first.", "Confirm restore"):
            return
        ok, safety = run_safely(self, db.restore_database, path)
        if ok:
            self.app.after_restore()
            info(self, "Restore complete." + (f"\nPrevious data kept at:\n{safety}" if safety else ""))

    def restore_file(self):
        p = filedialog.askopenfilename(parent=self, title="Choose backup", filetypes=[("Database backup", "*.db"), ("All files", "*.*")])
        if p and run_safely(self, db.validate_backup, p)[0]:
            self._restore(p)

    def restore_selected(self):
        iid = self.table.selected()
        if not iid:
            return info(self, "Select a backup from the list.")
        self._restore(self.files[iid])


# ================================================================== app shell
NAV = [("dashboard", "home", "Dashboard"), ("invoices", "doc", "Invoices"), ("estimates", "quote", "Quotations"),
       ("clients", "users", "Clients"), ("products", "box", "Products & Services"), ("payments", "card", "Payments"),
       ("expenses", "wallet", "Expenses"), ("reports", "chart", "Reports"), ("settings", "gear", "Settings")]
META = {"dashboard": ("Dashboard", "Live financial overview from your local records"),
        "invoices": ("Invoices", "Create, send, track and print invoices"), "estimates": ("Quotations", "Estimates you can convert into invoices"),
        "clients": ("Clients", "Contacts, billing details and balances"), "products": ("Products & Services", "Reusable catalog for fast invoicing"),
        "payments": ("Payments", "Record full or partial payments and issue receipts"), "expenses": ("Expenses", "Track business spending by category"),
        "reports": ("Reports", "Revenue, receivables, expenses, tax and client performance"), "settings": ("Settings", "Branding, numbering, tax, theme and backups"),
        "invoice_edit": ("Invoice", "Totals update live as you type"), "quote_edit": ("Quotation", "Totals update live as you type")}
PARENT = {"invoice_edit": "invoices", "quote_edit": "estimates"}
SIDE_TXT, SIDE_ACTIVE, SIDE_HOVER, SIDE_PILL = "#9FB0D6", "#FFFFFF", "#17223F", "#3D6BFF"


def _logo_image():
    return Image.open(io.BytesIO(base64.b64decode(LOGO_B64))).convert("RGBA")


def _mix(c1, c2, t):
    a, b = [tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) for c in (c1, c2)]
    return "#%02x%02x%02x" % tuple(int(x + (y - x) * max(0, min(1, t))) for x, y in zip(a, b))


class Splash(tk.Toplevel):
    """Animated 5-second branded splash. Time-based, so it never freezes the build running behind it."""
    W, H, DURATION = 640, 400, 5.0
    PHASES = ((0.0, "Initializing database..."), (0.3, "Loading workspace..."), (0.6, "Preparing dashboard..."), (0.85, "Almost ready..."))

    def __init__(self, root, ready, done):
        super().__init__(root)
        self.ready, self.done, self.t0, self.fading = ready, done, None, None
        self.overrideredirect(True)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{self.W}x{self.H}+{(sw - self.W) // 2}+{(sh - self.H) // 2}")
        try:
            self.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.cv = tk.Canvas(self, width=self.W, height=self.H, highlightthickness=0, bd=0, bg="#070B17")
        self.cv.pack()
        bg = Image.new("RGB", (self.W, self.H))
        d = ImageDraw.Draw(bg)
        for y in range(self.H):
            d.line([(0, y), (self.W, y)], fill=tuple(int(a + (b - a) * y / self.H) for a, b in zip((12, 22, 52), (5, 8, 18))))
        self.bg = ImageTk.PhotoImage(bg)
        self.cv.create_image(0, 0, image=self.bg, anchor="nw")
        self.logo = _logo_image()
        self.frames = {}
        self.after(30, self._tick)

    def _logo_frame(self, scale):
        k = round(scale * 20)
        if k not in self.frames:
            w = max(8, int(170 * k / 20))
            self.frames[k] = ImageTk.PhotoImage(self.logo.resize((w, int(w * self.logo.height / self.logo.width)), Image.LANCZOS))
        return self.frames[k]

    def _tick(self):
        if self.t0 is None:
            self.t0 = time.perf_counter()
        t = time.perf_counter() - self.t0
        cv, W = self.cv, self.W
        cv.delete("dyn")
        pulse = 0.5 + 0.5 * math.sin(t * 3)
        for i, r in enumerate((150, 120, 92)):
            cv.create_oval(W / 2 - r, 130 - r * 0.62, W / 2 + r, 130 + r * 0.62, outline=_mix("#070B17", "#2563EB", 0.18 + 0.1 * pulse - i * 0.04), width=2, tags="dyn")
        s = min(1.0, t / 0.9)
        s = 1 - (1 - s) ** 3
        img = self._logo_frame(0.55 + 0.45 * s)
        cv.create_image(W / 2, 130 - 12 * (1 - s), image=img, tags="dyn")
        a = max(0, min(1, (t - 0.5) / 0.6))
        cv.create_text(W / 2 - 62, 238, text="Invoice", fill=_mix("#070B17", "#FFFFFF", a), font=(FONT, 30, "bold"), tags="dyn")
        cv.create_text(W / 2 + 70, 238, text="Pilot", fill=_mix("#070B17", "#22A7FF", a), font=(FONT, 30, "bold"), tags="dyn")
        a2 = max(0, min(1, (t - 1.1) / 0.7))
        cv.create_text(W / 2, 276, text=db.TAGLINE, fill=_mix("#070B17", "#8FA0C4", a2), font=(FONT, 12), tags="dyn")
        p = min(1.0, t / self.DURATION)
        x0, x1, y = 120, W - 120, 330
        cv.create_rectangle(x0, y, x1, y + 6, fill="#16213D", outline="", tags="dyn")
        cv.create_rectangle(x0, y, x0 + (x1 - x0) * p, y + 6, fill="#2F7BFF", outline="", tags="dyn")
        cv.create_rectangle(x0, y, x0 + (x1 - x0) * p * 0.45, y + 6, fill="#22D3EE", outline="", tags="dyn")
        label = [txt for at, txt in self.PHASES if p >= at][-1]
        cv.create_text(x0, y + 22, text=label, fill="#8FA0C4", font=(FONT, 9), anchor="w", tags="dyn")
        cv.create_text(x1, y + 22, text=f"{int(p * 100)}%", fill="#8FA0C4", font=(FONT, 9, "bold"), anchor="e", tags="dyn")
        cv.create_text(W / 2, self.H - 18, text=f"v{db.APP_VERSION}", fill="#3B4B73", font=(FONT, 8), tags="dyn")
        if t >= self.DURATION and self.ready():
            return self._fade()
        self.after(16, self._tick)

    def _fade(self, i=0):
        try:
            self.attributes("-alpha", max(0.0, 1 - i / 8))
        except tk.TclError:
            i = 8
        if i >= 8:
            self.destroy()
            return self.done()
        self.after(20, self._fade, i + 1)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.withdraw()
        style_tree()
        self.title(f"{db.APP_TITLE} - {db.TAGLINE}")
        self.geometry("1380x860")
        self.minsize(1120, 700)
        self.configure(fg_color=P["bg"])
        self.pages, self.current, self.nav, self.collapsed, self.booted = {}, None, {}, False, False
        try:
            self._icon = ImageTk.PhotoImage(_logo_image().resize((64, 39), Image.LANCZOS))
            self.after(300, lambda: self.iconphoto(True, self._icon))
        except Exception:  # noqa: BLE001 - icon is cosmetic only
            pass
        self.steps = [self._shell] + [(lambda k=k, c=c: self._make(k, c)) for k, c in (
            ("dashboard", DashboardPage), ("invoices", InvoicesPage), ("estimates", EstimatesPage), ("clients", ClientsPage),
            ("products", ProductsPage), ("payments", PaymentsPage), ("expenses", ExpensesPage), ("reports", ReportsPage), ("settings", SettingsPage))]
        self.steps += [lambda: self._make("invoice_edit", lambda p, a: EditorPage(p, a, "invoice")),
                       lambda: self._make("quote_edit", lambda p, a: EditorPage(p, a, "quote")), self._finish_boot]
        self.splash = Splash(self, lambda: self.booted, self._reveal)
        self.after(40, self._boot)

    # ---- startup (runs in small slices while the splash animates)
    def _boot(self):
        if self.steps:
            try:
                self.steps.pop(0)()
            except Exception:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                self.booted = True
                return
            self.after(12, self._boot)

    def _finish_boot(self):
        self.show("dashboard")
        self.booted = True

    def _reveal(self):
        self.deiconify()
        self.lift()
        try:
            self.attributes("-alpha", 0.0)
            self._fade_in()
        except tk.TclError:
            pass

    def _fade_in(self, i=1):
        self.attributes("-alpha", min(1.0, i / 8))
        if i < 8:
            self.after(20, self._fade_in, i + 1)

    # ---- layout
    def _shell(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.side = ctk.CTkFrame(self, width=252, fg_color=P["side"], corner_radius=24, border_width=1, border_color=("#1B2748", "#18223F"))
        self.side.grid(row=0, column=0, sticky="nsw", padx=(14, 0), pady=14)
        self.side.pack_propagate(False)
        brand = bar(self.side)
        brand.pack(fill="x", padx=14, pady=(22, 18))
        self.logo_img = ctk.CTkImage(light_image=_logo_image(), dark_image=_logo_image(), size=(48, 29))
        ctk.CTkLabel(brand, text="", image=self.logo_img).pack(side="left")
        self.brand_txt = bar(brand)
        self.brand_txt.pack(side="left", padx=8)
        ctk.CTkLabel(self.brand_txt, text="Invoice", font=F(18, "bold"), text_color="white").pack(side="left")
        ctk.CTkLabel(self.brand_txt, text=" Pilot", font=F(18, "bold"), text_color="#22A7FF").pack(side="left")
        for key, ico, text in NAV:
            row = bar(self.side)
            row.pack(fill="x", padx=10, pady=2)
            ind = ctk.CTkFrame(row, width=4, height=26, fg_color="transparent", corner_radius=2)
            ind.pack(side="left", padx=(0, 4))
            b = ctk.CTkButton(row, text="  " + text, image=icon(ico, SIDE_TXT, SIDE_TXT, 20), compound="left", anchor="w", height=42, corner_radius=14,
                              font=F(14, "bold"), fg_color="transparent", text_color=SIDE_TXT, hover_color=SIDE_HOVER, command=lambda k=key: self.show(k))
            b.pack(side="left", fill="x", expand=True)
            self.nav[key] = (b, ind, ico, text)
        foot = bar(self.side)
        foot.pack(side="bottom", fill="x", padx=10, pady=(0, 14))
        self.collapse_btn = ctk.CTkButton(foot, text="  Collapse", image=icon("menu", SIDE_TXT, SIDE_TXT, 18), compound="left", anchor="w", height=36,
                                          corner_radius=12, font=F(12, "bold"), fg_color="transparent", text_color=SIDE_TXT, hover_color=SIDE_HOVER,
                                          command=self.toggle_sidebar)
        self.collapse_btn.pack(fill="x")
        self.ver = ctk.CTkLabel(foot, text=f"v{db.APP_VERSION}  |  works offline", font=F(10), text_color="#566690")
        self.ver.pack(pady=(6, 0))

        main = bar(self)
        main.grid(row=0, column=1, sticky="nsew", padx=18, pady=(14, 14))
        top = bar(main)
        top.pack(fill="x", pady=(2, 12))
        tb = bar(top)
        tb.pack(side="left")
        self.h_title = lbl(tb, "", 25, "bold")
        self.h_title.pack(anchor="w")
        self.h_sub = lbl(tb, "", 12, color="muted")
        self.h_sub.pack(anchor="w")
        self.theme_btn = ctk.CTkButton(top, text="", width=130, height=36, corner_radius=18, font=F(12, "bold"), compound="left",
                                       fg_color=P["panel"], hover_color=P["panel2"], text_color=P["text"], border_width=1, border_color=P["border"],
                                       command=lambda: self.set_theme("light" if ctk.get_appearance_mode() == "Dark" else "dark"))
        self.theme_btn.pack(side="right")
        self.biz = lbl(top, "", 12, "bold", "muted")
        self.biz.pack(side="right", padx=14)
        self.content = bar(main)
        self.content.pack(fill="both", expand=True)
        self._theme_button()

    def _make(self, key, cls):
        self.pages[key] = cls(self.content, self)

    def toggle_sidebar(self):
        self.collapsed = not self.collapsed
        c = self.collapsed
        self.side.configure(width=82 if c else 252)
        self.brand_txt.pack_forget() if c else self.brand_txt.pack(side="left", padx=8)
        for key, (b, ind, ico, text) in self.nav.items():
            b.configure(text="" if c else "  " + text, anchor="center" if c else "w")
        self.collapse_btn.configure(text="" if c else "  Collapse", anchor="center" if c else "w")
        self.ver.configure(text="" if c else f"v{db.APP_VERSION}  |  works offline")

    # ---- navigation
    def show(self, key):
        if self.current:
            self.pages[self.current].pack_forget()
        self.current = key
        active = PARENT.get(key, key)
        for k, (b, ind, ico, text) in self.nav.items():
            on = k == active
            b.configure(fg_color=SIDE_PILL if on else "transparent", text_color=SIDE_ACTIVE if on else SIDE_TXT,
                        image=icon(ico, SIDE_ACTIVE if on else SIDE_TXT, SIDE_ACTIVE if on else SIDE_TXT, 20),
                        hover_color=SIDE_PILL if on else SIDE_HOVER)
            ind.configure(fg_color="#22D3EE" if on else "transparent")
        self.h_title.configure(text=META[key][0])
        self.h_sub.configure(text=META[key][1])
        self.biz.configure(text=db.get_settings().get("business_name", ""))
        page = self.pages[key]
        page.pack(fill="both", expand=True)
        if hasattr(page, "refresh"):
            page.refresh()

    def refresh_current(self):
        page = self.pages[self.current]
        if hasattr(page, "refresh"):
            page.refresh()
        self.biz.configure(text=db.get_settings().get("business_name", ""))

    def new_doc(self, kind):
        self.pages[kind + "_edit"].reset()
        self.show(kind + "_edit")

    def edit_doc(self, kind, doc_id):
        d = db.get_estimate(doc_id) if kind == "quote" else db.get_invoice(doc_id)
        if not d or d["status"] in ("void", "converted"):
            return error(self, "Void invoices and converted quotations can no longer be edited.")
        self.pages[kind + "_edit"].load(doc_id)
        self.show(kind + "_edit")

    def after_restore(self):
        for k in ("invoice_edit", "quote_edit"):
            self.pages[k].reset()
        self.set_theme(db.get_settings().get("theme", "dark"), save=False)
        self.refresh_current()

    # ---- theme
    def _theme_button(self):
        dark = ctk.get_appearance_mode() == "Dark"
        self.theme_btn.configure(text="  Light mode" if dark else "  Dark mode",
                                 image=icon("sun" if dark else "moon", "#334155", "#E2E8F0", 18))

    def set_theme(self, mode, save=True):
        mode = mode if mode in ("light", "dark") else "dark"
        ctk.set_appearance_mode(mode)
        if save:
            run_safely(self, db.save_settings, {"theme": mode})
        style_tree()
        self.configure(fg_color=P["bg"])
        self._theme_button()
        for cb in HUB:
            cb()
        page = self.pages.get(self.current)
        if page is not None and hasattr(page, "theme"):
            page.theme.set("Dark" if mode == "dark" else "Light")


def main():
    try:
        db.init_db()
        mode = db.get_settings().get("theme", "dark")
        ctk.set_appearance_mode(mode if mode in ("light", "dark") else "dark")
        ctk.set_default_color_theme("blue")
        App().mainloop()
    except Exception:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        try:
            from tkinter import messagebox
            messagebox.showerror("Invoice Pilot", "An unexpected error occurred:\n\n" + traceback.format_exc()[-800:])
        except Exception:  # noqa: BLE001
            pass
        raise


# Embedded brand mark (PNG, base64) - no external image files needed.
LOGO_B64 = (
    "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"
)


if __name__ == "__main__":
    main()
