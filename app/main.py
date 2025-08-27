from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QQmlApplicationEngine
import sys

def run():
    app = QApplication(sys.argv)
    engine = QQmlApplicationEngine()
    engine.load("app/ui/MainView.qml")
    if not engine.rootObjects():
        sys.exit(-1)
    sys.exit(app.exec())

if __name__ == "__main__":
    run()
