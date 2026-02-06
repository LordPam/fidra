"""Helpers for QCompleter behavior."""

from PySide6.QtCore import QObject, QEvent, Qt


class TabAcceptCompleterFilter(QObject):
    """Accept completer suggestion on Tab without moving focus."""

    def __init__(self, widget, completer):
        super().__init__(widget)
        self._widget = widget
        self._completer = completer

    def _accept_current(self) -> bool:
        completer = self._completer
        if not completer:
            return False

        model = completer.completionModel()
        if model is None or model.rowCount() == 0:
            return False

        completer.setCurrentRow(0)
        text = completer.currentCompletion()
        if not text:
            return False

        if hasattr(self._widget, "setText"):
            self._widget.setText(text)
        elif hasattr(self._widget, "setEditText"):
            self._widget.setEditText(text)

        popup = completer.popup()
        if popup:
            popup.hide()
        return True

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Tab:
            if self._accept_current():
                return True
        return super().eventFilter(obj, event)


def install_tab_accept(widget, completer) -> TabAcceptCompleterFilter:
    """Install the Tab-to-accept completer filter on a widget."""
    filt = TabAcceptCompleterFilter(widget, completer)
    widget.installEventFilter(filt)
    popup = completer.popup() if completer else None
    if popup:
        popup.installEventFilter(filt)
    return filt
