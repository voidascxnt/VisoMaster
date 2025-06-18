#!/usr/bin/env python3
import sys
import os
from pathlib import Path

# Fix typing compatibility issue for PyTorch
try:
    from typing import Self
except ImportError:
    # For Python < 3.11, add Self to typing_extensions
    try:
        from typing_extensions import Self
        import typing
        typing.Self = Self
    except ImportError:
        pass

from app.ui import main_ui
from PySide6 import QtWidgets 
import sys

import qdarktheme
from app.ui.core.proxy_style import ProxyStyle

if __name__=="__main__":

    app = QtWidgets.QApplication(sys.argv)
    app.setStyle(ProxyStyle())
    with open("app/ui/styles/dark_styles.qss", "r") as f:
        _style = f.read()
        _style = qdarktheme.load_stylesheet(custom_colors={"primary": "#4facc9"})+'\n'+_style
        app.setStyleSheet(_style)
    window = main_ui.MainWindow()
    window.show()
    app.exec()