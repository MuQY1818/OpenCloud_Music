import sys
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from ui.main_window import NCMPlayerApp

if __name__ == '__main__':
    # Set attribute to enable high-DPI scaling for better visuals
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    app = QApplication(sys.argv)
    
    # All the application logic is now in NCMPlayerApp
    window = NCMPlayerApp()
    window.show()
    
    sys.exit(app.exec())