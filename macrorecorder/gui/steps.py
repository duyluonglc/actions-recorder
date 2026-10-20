"""Step list: a list of two-line cards (number, icon, title, detail, marker, note)."""

from __future__ import annotations

import json

from PySide6.QtCore import QAbstractListModel, QMimeData, QModelIndex, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPalette, QPen
from PySide6.QtWidgets import QAbstractItemView, QListView, QStyle, QStyledItemDelegate

from ..actions import Action
from ..i18n import tr
from ..macro import group_ranges

MIME = "application/x-actionsrecorder-rows"
ACCENT = QColor("#6d5ae6")
PLAYING = QColor("#22a06b")

ActionRole = Qt.UserRole + 1
DepthRole = Qt.UserRole + 2
GroupColorRole = Qt.UserRole + 3
CurrentRole = Qt.UserRole + 4


NEW_MIME = "application/x-actionsrecorder-new"


class StepModel(QAbstractListModel):
    rows_dropped = Signal(list, int)
    new_dropped = Signal(str, dict, int)

    def __init__(self):
        super().__init__()
        self.actions: list[Action] = []
        self.current = -1
        self.locked = False
        self.depth: list[int] = []
        self.group_of: list[int] = []

    def set_actions(self, actions: list[Action]) -> None:
        self.beginResetModel()
        self.actions = actions
        self._structure()
        self.endResetModel()

    def _structure(self) -> None:
        n = len(self.actions)
        self.depth = [0] * n
        self.group_of = [-1] * n
        for s, e in sorted(group_ranges(self.actions).items()):
            for i in range(s + 1, e + 1):
                self.depth[i] += 1
                self.group_of[i] = s
            if e < n and self.actions[e].kind == "group_end":
                self.depth[e] -= 1

    def refresh_rows(self, rows) -> None:
        self._structure()
        for r in rows:
            if 0 <= r < len(self.actions):
                self.dataChanged.emit(self.index(r), self.index(r))

    def set_current(self, row: int) -> None:
        old, self.current = self.current, row
        for r in (old, row):
            if 0 <= r < len(self.actions):
                self.dataChanged.emit(self.index(r), self.index(r))

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.actions)

    def flags(self, index):
        if self.locked:                   # recording / running: look, don't touch
            return Qt.ItemIsEnabled | Qt.ItemIsSelectable if index.isValid() else Qt.NoItemFlags
        if not index.isValid():
            return Qt.ItemIsDropEnabled
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        r = index.row()
        a = self.actions[r]
        if role == ActionRole:
            return a
        if role == DepthRole:
            return self.depth[r] if r < len(self.depth) else 0
        if role == CurrentRole:
            return r == self.current
        if role == GroupColorRole:
            g = r if a.kind == "group" else (self.group_of[r] if r < len(self.group_of) else -1)
            return QColor(self.actions[g].params.get("color") or "#3e63dd") if g >= 0 else None
        if role == Qt.DisplayRole:
            return f"{a.name} {a.describe()}"
        if role == Qt.ToolTipRole:
            tip = f"<b>{a.name}</b><br>{a.describe()}"
            if a.comment:
                tip += f"<br><i>{a.comment}</i>"
            return tip
        return None

    # drag & drop
    def supportedDropActions(self):
        return Qt.MoveAction

    def mimeTypes(self):
        return [MIME, NEW_MIME]

    def canDropMimeData(self, data, action, row, column, parent):
        return data.hasFormat(MIME) or data.hasFormat(NEW_MIME)

    def mimeData(self, indexes):
        md = QMimeData()
        md.setData(MIME, json.dumps(sorted({i.row() for i in indexes})).encode())
        return md

    def supportedDragActions(self):
        return Qt.MoveAction

    def dropMimeData(self, data, action, row, column, parent):
        if self.locked:
            return False
        if row < 0:
            row = parent.row() if parent.isValid() else len(self.actions)
        if data.hasFormat(NEW_MIME):
            d = json.loads(bytes(data.data(NEW_MIME)).decode())
            self.new_dropped.emit(d["kind"], d.get("extra") or {}, row)
            return False
        if not data.hasFormat(MIME):
            return False
        self.rows_dropped.emit(json.loads(bytes(data.data(MIME)).decode()), row)
        return False


class StepDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        a: Action = index.data(ActionRole)
        if a.kind == "group_end":
            return QSize(200, 22)
        return QSize(200, 48)

    def paint(self, p: QPainter, option, index):
        a: Action = index.data(ActionRole)
        depth = index.data(DepthRole) or 0
        gcolor = index.data(GroupColorRole)
        current = index.data(CurrentRole)
        pal = option.palette
        r = option.rect
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        selected = bool(option.state & QStyle.State_Selected)
        hover = bool(option.state & QStyle.State_MouseOver)
        text = pal.color(QPalette.Text)
        dim = QColor(text)
        dim.setAlphaF(0.55)

        card = r.adjusted(6 + depth * 18, 2, -6, -2)
        # background
        if a.kind == "group" and gcolor:
            bg = QColor(gcolor)
            bg.setAlphaF(0.18)
            p.setPen(Qt.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(card, 7, 7)
        if selected:
            sel = QColor(ACCENT)
            sel.setAlphaF(0.22)
            p.setPen(QPen(ACCENT, 1.2))
            p.setBrush(sel)
            p.drawRoundedRect(card, 7, 7)
        elif hover:
            hv = QColor(text)
            hv.setAlphaF(0.06)
            p.setPen(Qt.NoPen)
            p.setBrush(hv)
            p.drawRoundedRect(card, 7, 7)
        if current:
            pl = QColor(PLAYING)
            pl.setAlphaF(0.25)
            p.setPen(Qt.NoPen)
            p.setBrush(pl)
            p.drawRoundedRect(card, 7, 7)
            p.setBrush(PLAYING)
            p.drawRoundedRect(QRect(card.left(), card.top() + 4, 4, card.height() - 8), 2, 2)
        # group stripe on the left of members
        if gcolor and a.kind != "group":
            p.setPen(Qt.NoPen)
            p.setBrush(gcolor)
            p.drawRect(QRect(r.left() + 6 + (depth - 1) * 18 + 6, r.top(), 3, r.height()))

        if not a.enabled:
            p.setOpacity(0.45)

        base = QFont(option.font)
        if a.kind == "group_end":
            f = QFont(base)
            f.setPointSizeF(base.pointSizeF() * 0.85)
            p.setFont(f)
            p.setPen(dim)
            p.drawText(card.adjusted(44, 0, 0, 0), Qt.AlignVCenter, "└ " + tr("End of group"))
            p.restore()
            return

        # number badge
        num = QRect(card.left() + 6, card.top() + (card.height() - 20) // 2, 30, 20)
        small = QFont(base)
        small.setPointSizeF(base.pointSizeF() * 0.85)
        p.setFont(small)
        p.setPen(dim)
        p.drawText(num, Qt.AlignCenter, str(index.row() + 1))

        # icon
        icon_rect = QRect(card.left() + 40, card.top() + (card.height() - 26) // 2, 26, 26)
        ic = QFont(base)
        ic.setPointSizeF(base.pointSizeF() * 1.35)
        p.setFont(ic)
        p.setPen(text)
        glyph = ("▸" if a.params.get("collapsed") else "▾") if a.kind == "group" else a.spec.icon
        p.drawText(icon_rect, Qt.AlignCenter, glyph)

        x = icon_rect.right() + 10
        right = card.right() - 10
        # marker chip (label)
        if a.label:
            chip_font = QFont(small)
            chip_font.setBold(True)
            fm = QFontMetrics(chip_font)
            w = fm.horizontalAdvance("⚑ " + a.label) + 14
            chip = QRect(right - w, card.top() + 7, w, fm.height() + 4)
            p.setPen(Qt.NoPen)
            cc = QColor("#e8a317")
            cc.setAlphaF(0.22)
            p.setBrush(cc)
            p.drawRoundedRect(chip, chip.height() / 2, chip.height() / 2)
            p.setFont(chip_font)
            p.setPen(QColor("#c77d00") if text.lightness() < 128 else QColor("#f0b84a"))
            p.drawText(chip, Qt.AlignCenter, "⚑ " + a.label)
            right = chip.left() - 8

        title_font = QFont(base)
        title_font.setBold(True)
        if not a.enabled:
            title_font.setStrikeOut(True)
        fm = QFontMetrics(title_font)
        title = (a.params.get("name") or tr("Group")) if a.kind == "group" else a.name
        top = card.top() + (6 if a.kind != "group" else (card.height() - fm.height()) // 2)
        p.setFont(title_font)
        p.setPen(text)
        p.drawText(QRect(x, top, right - x, fm.height()), Qt.AlignVCenter,
                   fm.elidedText(title, Qt.ElideRight, right - x))
        if a.kind != "group":
            detail = a.describe()
            if a.comment:
                detail = f"{detail}   — {a.comment}" if detail else a.comment
            df = QFont(base)
            df.setPointSizeF(base.pointSizeF() * 0.92)
            dfm = QFontMetrics(df)
            p.setFont(df)
            p.setPen(dim)
            dr = QRect(x, top + fm.height() + 2, card.right() - 10 - x, dfm.height())
            p.drawText(dr, Qt.AlignVCenter, dfm.elidedText(detail, Qt.ElideRight, dr.width()))
        p.restore()


class StepList(QListView):
    edit_requested = Signal()
    delete_requested = Signal()

    def __init__(self, model: StepModel):
        super().__init__()
        self.setModel(model)
        self.setItemDelegate(StepDelegate(self))
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setAcceptDrops(True)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDropIndicatorShown(True)
        self.setMouseTracking(True)
        self.setUniformItemSizes(False)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setFrameShape(QListView.NoFrame)
        self.setObjectName("stepList")

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.edit_requested.emit()
            return
        if e.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete_requested.emit()
            return
        super().keyPressEvent(e)
