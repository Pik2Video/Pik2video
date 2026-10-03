# src/pik2video/gui/common/dialogs.py


from PySide6.QtWidgets import QMessageBox


def confirm(
    parent,
    text: str,
    title: str = "Подтверждение",
    translator=None,
    yes_label: str = "",
    no_label: str = "",
) -> bool:
    """
    Универсальное окно подтверждения.
    Возвращает True если пользователь нажал "Да".

    yes_label / no_label — переопределяют текст кнопок.
    Если не заданы, берётся из translator или дефолт.
    """
    msg = QMessageBox(parent)
    msg.setIcon(QMessageBox.Question)
    msg.setText(text)

    if translator:
        msg.setWindowTitle(translator.tr("confirm_title"))
        default_yes = translator.tr("confirm_yes")
        default_no = translator.tr("confirm_no")
    else:
        msg.setWindowTitle(title)
        default_yes = "Да"
        default_no = "Нет"

    btn_yes = msg.addButton(yes_label or default_yes, QMessageBox.YesRole)
    btn_no = msg.addButton(no_label or default_no, QMessageBox.NoRole)

    msg.setDefaultButton(btn_no)
    msg.exec()

    return msg.clickedButton() == btn_yes

def info(parent, text: str, title: str = "Информация", translator=None):
    """
    Информационное сообщение.
    """
    msg = QMessageBox(parent)
    
    if translator:
        msg.setWindowTitle(translator.tr("info_title"))
        msg.setText(text)
        msg.setIcon(QMessageBox.Information)
        msg.addButton(translator.tr("info_ok"), QMessageBox.AcceptRole)
    else:
        msg.setWindowTitle(title)
        msg.setText(text)
        msg.setIcon(QMessageBox.Information)
        msg.addButton("OK", QMessageBox.AcceptRole)
    
    msg.exec()


def warning(parent, text: str, title: str = "Предупреждение", translator=None):
    """
    Предупреждение.
    """
    msg = QMessageBox(parent)
    
    if translator:
        msg.setWindowTitle(translator.tr("warning_title"))
        msg.setText(text)
        msg.setIcon(QMessageBox.Warning)
        msg.addButton(translator.tr("warning_ok"), QMessageBox.AcceptRole)
    else:
        msg.setWindowTitle(title)
        msg.setText(text)
        msg.setIcon(QMessageBox.Warning)
        msg.addButton("OK", QMessageBox.AcceptRole)
    
    msg.exec()


def error(parent, text: str, title: str = "Ошибка", translator=None):
    """
    Сообщение об ошибке.
    """
    msg = QMessageBox(parent)
    
    if translator:
        msg.setWindowTitle(translator.tr("error_title"))
        msg.setText(text)
        msg.setIcon(QMessageBox.Critical)
        msg.addButton(translator.tr("error_ok"), QMessageBox.AcceptRole)
    else:
        msg.setWindowTitle(title)
        msg.setText(text)
        msg.setIcon(QMessageBox.Critical)
        msg.addButton("OK", QMessageBox.AcceptRole)
    
    msg.exec()
