from PySide6.QtWidgets import QMessageBox


def confirm(parent, text: str, title: str = "Подтверждение", translator=None) -> bool:
    """
    Универсальное окно подтверждения.
    Возвращает True если пользователь нажал "Да".
    """
    msg = QMessageBox(parent)
    
    # Если есть translator, переводим кнопки
    if translator:
        msg.setWindowTitle(translator.tr("confirm_title"))
        msg.setText(text)  # текст уже должен быть переведен до вызова
        msg.setIcon(QMessageBox.Question)
        
        btn_yes = msg.addButton(translator.tr("confirm_yes"), QMessageBox.YesRole)
        btn_no = msg.addButton(translator.tr("confirm_no"), QMessageBox.NoRole)
    else:
        msg.setWindowTitle(title)
        msg.setText(text)
        msg.setIcon(QMessageBox.Question)
        
        btn_yes = msg.addButton("Да", QMessageBox.YesRole)
        btn_no = msg.addButton("Нет", QMessageBox.NoRole)
    
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