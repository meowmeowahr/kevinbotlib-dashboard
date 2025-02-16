# SPDX-FileCopyrightText: 2025-present meowmeowahr <meowmeowahr@gmail.com>
#
# SPDX-License-Identifier: LGPL-3.0-or-later

import sys

from PySide6.QtCore import QCommandLineParser
from PySide6.QtWidgets import QApplication

from kevinbotlib_dashboard.app import MainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)

    parser = QCommandLineParser()
    parser.addHelpOption()
    parser.process(app)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())
