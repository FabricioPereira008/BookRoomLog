"""Campo de data opcional usado nos formulários de jogo."""
from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import QDateEdit


class OptionalDateEdit(QDateEdit):
    """Campo de data que começa vazio ("Selecione a data") e só assume um valor quando o usuário interage."""
    BLANK = QDate(1970, 1, 1)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCalendarPopup(True)
        self.setDisplayFormat("dd/MM/yyyy")
        self.setMinimumDate(self.BLANK)
        self.setSpecialValueText("Selecione a data")
        self.setDate(self.BLANK)

    def is_blank(self) -> bool:
        return self.date() == self.BLANK

    def date_or_none(self):
        return None if self.is_blank() else self.date()

    def set_optional_date(self, value) -> None:
        self.setDate(value if value is not None and value.isValid() else self.BLANK)

    def _start_today(self) -> bool:
        if self.is_blank():
            self.setDate(QDate.currentDate())
            return True
        return False

    def mousePressEvent(self, event):
        # o calendário abre no mês atual, não em 1970; o clique que preenche não conta como passo das setas
        self._skip_step = self._start_today()
        super().mousePressEvent(event)
        self._skip_step = False

    def stepBy(self, steps):
        if getattr(self, "_skip_step", False) or self._start_today():
            return
        super().stepBy(steps)

    def wheelEvent(self, event):
        if self.is_blank():
            event.ignore()  # rolar a página não deve preencher a data sem querer
            return
        super().wheelEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.setDate(self.BLANK)
            return
        super().keyPressEvent(event)
