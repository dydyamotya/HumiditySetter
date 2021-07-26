import sys
from PySide6 import QtWidgets
import logging
from PySide6.QtCore import QSettings
from widgets import MainWindow

log_format_string = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

if __name__ == "__main__":
    logging.basicConfig(format=log_format_string, level=logging.INFO)
    logger = logging.getLogger()
    handler = logging.FileHandler("default.log", mode="a")
    formatter = logging.Formatter(fmt=log_format_string)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.debug("Program started")
    app = QtWidgets.QApplication()
    settings = QSettings("MotyaSoft", "HumiditySetter")

    widget = MainWindow(settings=settings)
    widget.show()

    sys.exit(app.exec_())
