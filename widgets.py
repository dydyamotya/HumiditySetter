import logging

import PySide6
from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import QSettings, QEvent

from protocol import get_comports_names, Protocol, QtProtocol

module_logger = logging.getLogger(__name__)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, parent=None, settings=None):
        super(MainWindow, self).__init__(parent=parent)
        self.setWindowTitle("HumiditySetter")
        self.central_widget = MainWidget(parent=self)
        self.settings: QSettings = settings
        self.setCentralWidget(self.central_widget)
        self._read_settings()

    def _read_settings(self):
        settings = self.settings
        settings.beginGroup("Common")
        self.com_port = settings.value("com_port", "")
        settings.endGroup()

    def closeEvent(self, event:PySide6.QtGui.QCloseEvent) -> None:
        self.central_widget.protocol.close_event()


class MainWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        first_comport = ""
        super(MainWidget, self).__init__(parent=parent)
        self.setLayout(QtWidgets.QVBoxLayout())

        self.layout().addWidget(QtWidgets.QLabel("Ports:", self))
        try:
            first_comport = get_comports_names()[0]
        except IndexError:
            first_comport = ""
        finally:
            self.com_port_entry = QtWidgets.QLineEdit(first_comport, self)
            self.protocol = QtProtocol(first_comport if first_comport != "" else None)
            self.layout().addWidget(self.com_port_entry)

            self.original_keyPress = self.com_port_entry.keyPressEvent
            self.com_port_entry.keyPressEvent = self.com_port_entry_key_press

            self.second_com_port_entry = QtWidgets.QLineEdit(first_comport, self)
            self.layout().addWidget(self.second_com_port_entry)

            self.original_keyPress = self.second_com_port_entry.keyPressEvent
            self.second_com_port_entry.keyPressEvent = self.second_com_port_entry_key_press

        self.layout().addWidget(QtWidgets.QLabel("Conc:", self))

        self.flow_entry = QtWidgets.QLineEdit(self)
        self.original_flow_keypress = self.flow_entry.keyPressEvent
        self.flow_entry.keyPressEvent = self.flow_entry_key_press
        self.layout().addWidget(self.flow_entry)
        self.label_to_show_parametrs = QtWidgets.QLabel("Hello", self)
        self.layout().addWidget(self.label_to_show_parametrs)
        self.protocol.stats.connect(self.label_to_show_parametrs.setText)

    def flow_entry_key_press(self, event: QEvent):
        if event.type() == QEvent.KeyPress:
            if event.key() == QtCore.Qt.Key_Return:
                self.protocol.set_flow(self.flow_entry.text())
        self.original_flow_keypress(event)

    def com_port_entry_key_press(self, event: QEvent) -> None:
        if event.type() == QEvent.KeyPress:
            if event.key() == QtCore.Qt.Key_Return:
                self.protocol.set_port(self.com_port_entry.text())
        self.original_keyPress(event)

    def second_com_port_entry_key_press(self, event: QEvent) -> None:
        if event.type() == QEvent.KeyPress:
            if event.key() == QtCore.Qt.Key_Return:
                self.protocol.set_second_port(self.second_com_port_entry.text())
        self.original_keyPress(event)
