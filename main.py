import sys
import subprocess
import argparse

from rapidfuzz import fuzz, utils
from database import Database

from PyQt6.QtCore import Qt, QSize, QEvent
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QLabel,
)


SERVER_NAME = "pylauncher_spotlight_instance"

class LauncherWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.db = Database()
        self.db.init_db()

        self.setWindowTitle("OpenLauncher")
        self.setFixedWidth(640)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.search = QLineEdit()
        self.search.setPlaceholderText("App suchen...")
        self.search.textChanged.connect(self.update_results)
        self.search.returnPressed.connect(self.launch_selected)
        self.search.installEventFilter(self)

        self.results = QListWidget()
        self.results.itemDoubleClicked.connect(lambda _: self.launch_selected())
        self.results.installEventFilter(self)
        self.results.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.hint = QLabel("Tab/Pfeil: Auswahl    Enter: Starten    Esc: Schließen")

        layout = QVBoxLayout()
        layout.addWidget(self.search)
        layout.addWidget(self.results)
        layout.addWidget(self.hint)

        container = QWidget()
        container.setLayout(layout)
        container.setObjectName("container")

        outer = QVBoxLayout()
        outer.addWidget(container)
        self.setLayout(outer)

        self.setStyleSheet("""
            QWidget#container {
                background: #202124;
                border-radius: 18px;
                padding: 16px;
            }

            QLineEdit {
                background: #2b2c2f;
                color: white;
                border: none;
                border-radius: 12px;
                padding: 16px;
                font-size: 24px;
            }

            QListWidget {
                background: transparent;
                color: white;
                border: none;
                font-size: 18px;
                padding-top: 10px;
            }

            QListWidget::item {
                padding: 12px;
                border-radius: 10px;
            }

            QListWidget::item:selected {
                background: #3c4043;
            }

            QLabel {
                color: #9aa0a6;
                font-size: 12px;
                padding-left: 8px;
            }
        """)

        self.update_results()

    def sizeHint(self):
        return QSize(640, 420)

    def center_on_screen(self):
        screen = QApplication.primaryScreen().availableGeometry()
        frame = self.frameGeometry()
        frame.moveCenter(screen.center())
        self.move(frame.topLeft())

    def show_launcher(self):
        self.center_on_screen()
        self.search.clear()
        self.update_results()
        self.show()
        self.raise_()
        self.activateWindow()
        self.search.setFocus()

    def toggle_launcher(self):
        if self.isVisible():
            self.hide()
        else:
            self.show_launcher()

    def select_next_result(self):
        count = self.results.count()

        if count == 0:
            return

        current = self.results.currentRow()

        if current < 0:
            self.results.setCurrentRow(0)
        else:
            self.results.setCurrentRow((current + 1) % count)

    def select_previous_result(self):
        count = self.results.count()

        if count == 0:
            return

        current = self.results.currentRow()

        if current < 0:
            self.results.setCurrentRow(0)
        else:
            self.results.setCurrentRow((current - 1) % count)

    def eventFilter(self, source, event):
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()

            if key in (Qt.Key.Key_Tab, Qt.Key.Key_Down):
                self.select_next_result()
                return True

            if key in (Qt.Key.Key_Backtab, Qt.Key.Key_Up):
                self.select_previous_result()
                return True

            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.launch_selected()
                return True

            if key == Qt.Key.Key_Escape:
                self.hide()
                return True

        return super().eventFilter(source, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            return

        super().keyPressEvent(event)

    def update_results(self):
        query = self.search.text().strip()

        self.results.clear()

        if not query:
            rows = self.db.search_apps("")
        else:
            candidates = self.db.get_all_apps()
            scored_rows = []

            query_lower = query.lower()

            for app_id, name, command in candidates:
                haystack = f"{name} {command}"

                score = fuzz.WRatio(
                    query,
                    haystack,
                    processor=utils.default_process,
                )

                if query_lower in name.lower():
                    score += 25
                elif query_lower in command.lower():
                    score += 10

                if score >= 55:
                    scored_rows.append((score, app_id, name, command))

            scored_rows.sort(key=lambda row: row[0], reverse=True)

            rows = [
                (app_id, name, command)
                for score, app_id, name, command in scored_rows[:10]
            ]

        for app_id, name, command in rows:
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, {
                "id": app_id,
                "name": name,
                "command": command,
            })
            self.results.addItem(item)

        if self.results.count() > 0:
            self.results.setCurrentRow(0)
                
                
    def launch_selected(self):
        item = self.results.currentItem()

        if not item:
            return

        data = item.data(Qt.ItemDataRole.UserRole)
        app_id = data["id"]
        command = data["command"]

        self.db.increase_usage(app_id)

        subprocess.Popen(command, shell=True, start_new_session=True)

        self.hide()


class SingleInstance:
    def __init__(self, window):
        self.window = window
        self.server = QLocalServer()

        QLocalServer.removeServer(SERVER_NAME)
        self.server.listen(SERVER_NAME)
        self.server.newConnection.connect(self.handle_connection)

    def handle_connection(self):
        socket = self.server.nextPendingConnection()

        if socket:
            socket.waitForReadyRead(500)
            message = bytes(socket.readAll()).decode("utf-8").strip()

            if message == "toggle":
                self.window.toggle_launcher()

            socket.disconnectFromServer()


def send_to_existing_instance(message):
    socket = QLocalSocket()
    socket.connectToServer(SERVER_NAME)

    if socket.waitForConnected(300):
        socket.write(message.encode("utf-8"))
        socket.flush()
        socket.waitForBytesWritten(300)
        socket.disconnectFromServer()
        return True

    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--toggle", action="store_true")
    parser.add_argument("--add", nargs=2, metavar=("NAME", "COMMAND"))
    parser.add_argument("--delete", metavar="NAME")
    args = parser.parse_args()

    if args.add:
        db = Database()
        db.init_db()
        name, command = args.add
        db.add_app(name, command)
        print(f"App gespeichert: {name} -> {command}")
        return

    if args.delete:
        db = Database()
        db.init_db()

        deleted_count = db.delete_app(args.delete)

        if deleted_count > 0:
            print(f"App gelöscht: {args.delete}")
        else:
            print(f"Keine App mit diesem Namen gefunden: {args.delete}")

        return

    if args.toggle:
        if send_to_existing_instance("toggle"):
            return

    app = QApplication(sys.argv)

    window = LauncherWindow()
    instance = SingleInstance(window)

    window.show_launcher()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
