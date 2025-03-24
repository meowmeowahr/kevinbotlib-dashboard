import functools
from collections.abc import Callable
from typing import override

from kevinbotlib.comm import CommunicationClient
from kevinbotlib.logger import Logger
from PySide6.QtCore import (
    QModelIndex,
    QObject,
    QPointF,
    QRect,
    QRectF,
    QRegularExpression,
    QSettings,
    QSize,
    Qt,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import QAction, QBrush, QCloseEvent, QColor, QPainter, QPen, QRegularExpressionValidator
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QGraphicsObject,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStyleOptionGraphicsItem,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from kevinbotlib_dashboard.grid_theme import Themes
from kevinbotlib_dashboard.toast import Notifier, Severity
from kevinbotlib_dashboard.tree import DictTreeModel
from kevinbotlib_dashboard.widgets import Divider


class WidgetItem(QGraphicsObject):
    item_deleted = Signal(object)

    def __init__(self, title: str, grid: "GridGraphicsView", span_x=1, span_y=1, data=None):
        if data is None:
            data = {}
        super().__init__()

        self.info = data
        self.kind = "base"

        self.title = title
        self.grid_size = grid.grid_size
        self.span_x = span_x
        self.span_y = span_y
        self.width = grid.grid_size * span_x
        self.height = grid.grid_size * span_y
        self.margin = grid.theme.value.padding
        self.setAcceptHoverEvents(True)
        self.setFlags(
            QGraphicsObject.GraphicsItemFlag.ItemIsMovable | QGraphicsObject.GraphicsItemFlag.ItemIsSelectable
        )
        self.setZValue(1)
        self.resizing = False
        self.resize_grip_size = 15
        self.min_width = self.grid_size * 2  # Minimum width in pixels
        self.min_height = self.grid_size * 2  # Minimum height in pixels
        self.view = grid

    def boundingRect(self):  # noqa: N802
        return QRectF(0, 0, self.width, self.height)

    def paint(self, painter: QPainter, _option: QStyleOptionGraphicsItem, /, _widget: QWidget | None = None):  # type: ignore
        painter.setBrush(QBrush(QColor(self.view.theme.value.item_background)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(
            QRect(self.margin, self.margin, self.width - 2 * self.margin, self.height - 2 * self.margin), 10, 10
        )

        title_rect = QRect(self.margin, self.margin, self.width - 2 * self.margin, 30)

        painter.setBrush(QBrush(QColor(self.view.theme.value.primary)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(title_rect, 10, 10)
        painter.drawRect(QRect(title_rect.x(), title_rect.y() + 10, title_rect.width(), title_rect.height() - 10))

        painter.setPen(QPen(QColor(self.view.theme.value.foreground)))
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignCenter, self.title)

    @override
    def mousePressEvent(self, event):
        grip_rect = QRectF(
            self.width - self.resize_grip_size,
            self.height - self.resize_grip_size,
            self.resize_grip_size,
            self.resize_grip_size,
        )
        self.start_pos = self.pos()
        self.start_span = self.span_x, self.span_y
        if grip_rect.contains(event.pos()):
            self.resizing = True
            self.start_resize_pos = event.pos()
            self.start_width = self.width
            self.start_height = self.height
            event.accept()
        else:
            super().mousePressEvent(event)

    @override
    def mouseMoveEvent(self, event):
        self.setZValue(2)
        if self.resizing:
            delta_x = event.pos().x() - self.start_resize_pos.x()
            delta_y = event.pos().y() - self.start_resize_pos.y()

            new_width = max(self.min_width, self.start_width + delta_x)  # Enforce minimum width
            new_height = max(self.min_height, self.start_height + delta_y)  # Enforce minimum height

            new_span_x = round(new_width / self.grid_size)
            new_span_y = round(new_height / self.grid_size)

            new_width = new_span_x * self.grid_size  # Recalculate width
            new_height = new_span_y * self.grid_size  # Recalculate height

            if new_width != self.width or new_height != self.height:
                self.width = new_width
                self.height = new_height
                self.span_x = new_span_x
                self.span_y = new_span_y
                self.prepareGeometryChange()
            self.view.update_highlight(self.pos(), self, new_span_x, new_span_y)
            event.accept()
        else:
            self.view.update_highlight(self.pos(), self, self.span_x, self.span_y)
            super().mouseMoveEvent(event)

    @override
    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.setZValue(1)
        if self.resizing:
            self.resizing = False
            if self.view.is_valid_drop_position(self.pos(), self, self.span_x, self.span_y):
                self.snap_to_grid()
            else:
                self.setPos(self.start_pos)
                self.set_span(*self.start_span)
        elif self.view.is_valid_drop_position(self.pos(), self, self.span_x, self.span_y):
            self.snap_to_grid()
        else:
            self.setPos(self.start_pos)
        self.view.hide_highlight()

    @override
    def hoverEnterEvent(self, event):
        self.hovering = True
        self.update()
        super().hoverEnterEvent(event)

    @override
    def hoverLeaveEvent(self, event):
        self.hovering = False
        self.update()
        super().hoverLeaveEvent(event)

    def set_span(self, x, y):
        self.span_x = x
        self.span_y = y
        self.width = self.grid_size * x
        self.height = self.grid_size * y
        self.update()

    def snap_to_grid(self):
        grid_size = self.grid_size
        new_x = round(self.pos().x() / grid_size) * grid_size
        new_y = round(self.pos().y() / grid_size) * grid_size
        rows, cols = self.view.rows, self.view.cols
        new_x = max(0, min(new_x, (cols - self.span_x) * grid_size))
        new_y = max(0, min(new_y, (rows - self.span_y) * grid_size))
        self.setPos(new_x, new_y)

    @override
    def contextMenuEvent(self, event):
        menu = QMenu(self.view)
        delete_action = QAction("Delete", self)
        delete_action.triggered.connect(self.delete_self)
        menu.addAction(delete_action)

        menu.exec(event.screenPos())

    def delete_self(self):
        self.item_deleted.emit(self)


class GridGraphicsView(QGraphicsView):
    def __init__(self, parent=None, grid_size: int = 48, rows=10, cols=10, theme: Themes = Themes.Dark):
        super().__init__(parent)
        self.grid_size = grid_size
        self.rows, self.cols = rows, cols
        self.theme = theme

        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate)
        self.setBackgroundBrush(QColor(theme.value.background))

        self.grid_lines = []
        self.draw_grid()

        self.highlight_rect = self.scene().addRect(
            0, 0, self.grid_size, self.grid_size, QPen(Qt.PenStyle.NoPen), QBrush(QColor(0, 255, 0, 100))
        )
        self.highlight_rect.setZValue(3)
        self.highlight_rect.hide()

    def is_valid_drop_position(self, position, dragging_widget=None, span_x=1, span_y=1):
        grid_size = self.grid_size
        rows, cols = self.rows, self.cols
        new_x = round(position.x() / grid_size) * grid_size
        new_y = round(position.y() / grid_size) * grid_size
        new_x = max(0, min(new_x, (cols - span_x) * grid_size))
        new_y = max(0, min(new_y, (rows - span_y) * grid_size))
        if new_x + span_x * grid_size > cols * grid_size or new_y + span_y * grid_size > rows * grid_size:
            return False
        bounding_rect = QRectF(QPointF(new_x, new_y), QSize(span_x * grid_size, span_y * grid_size))
        items = self.scene().items(bounding_rect)
        return all(not (isinstance(item, WidgetItem) and item != dragging_widget) for item in items)

    def update_highlight(self, position, dragging_widget=None, span_x=1, span_y=1):
        grid_size = self.grid_size
        rows, cols = self.rows, self.cols
        new_x = round(position.x() / grid_size) * grid_size
        new_y = round(position.y() / grid_size) * grid_size
        new_x = max(0, min(new_x, (cols - span_x) * grid_size))
        new_y = max(0, min(new_y, (rows - span_y) * grid_size))
        valid_position = self.is_valid_drop_position(position, dragging_widget, span_x, span_y)
        self.highlight_rect.setBrush(QBrush(QColor(0, 255, 0, 100) if valid_position else QColor(255, 0, 0, 100)))
        self.highlight_rect.setRect(new_x, new_y, grid_size * span_x, grid_size * span_y)
        self.highlight_rect.show()

    def hide_highlight(self):
        self.highlight_rect.hide()

    def draw_grid(self):
        for item in reversed(self.grid_lines):
            self.scene().removeItem(item)
            self.grid_lines.remove(item)

        grid_size = self.grid_size
        rows, cols = self.rows, self.cols
        pen = QPen(QColor(self.theme.value.border), 1, Qt.PenStyle.DashLine)
        for i in range(cols + 1):
            x = i * grid_size
            self.grid_lines.append(self.scene().addLine(x, 0, x, rows * grid_size, pen))
        for i in range(rows + 1):
            y = i * grid_size
            self.grid_lines.append(self.scene().addLine(0, y, cols * grid_size, y, pen))
        self.scene().setSceneRect(0, 0, cols * grid_size, rows * grid_size)

    def set_grid_size(self, size: int):
        self.grid_size = size
        self.draw_grid()
        self.highlight_rect = self.scene().addRect(
            0, 0, self.grid_size, self.grid_size, QPen(Qt.PenStyle.NoPen), QBrush(QColor(0, 255, 0, 100))
        )
        self.highlight_rect.setZValue(3)
        self.highlight_rect.hide()
        for item in self.scene().items():
            if isinstance(item, WidgetItem):
                old_x = item.pos().x() // item.grid_size
                old_y = item.pos().y() // item.grid_size
                item.grid_size = size
                item.set_span(item.span_x, item.span_y)
                item.setPos(old_x * self.grid_size, old_y * self.grid_size)

    def can_resize_to(self, new_rows, new_cols):
        """Check if all current widgets would fit in the new dimensions"""
        for item in self.scene().items():
            if not isinstance(item, WidgetItem):
                continue
            if (
                item.pos().x() + item.span_x * self.grid_size > new_cols * self.grid_size
                or item.pos().y() + item.span_y * self.grid_size > new_rows * self.grid_size
            ):
                return False
        return True

    def resize_grid(self, rows, cols):
        """Attempt to resize the grid while preserving widget instances"""
        # First check if resize is possible
        if not self.can_resize_to(rows, cols):
            return False

        widgets = [item for item in self.scene().items() if isinstance(item, WidgetItem)]

        for widget in widgets:
            self.scene().removeItem(widget)

        self.scene().clear()
        self.grid_lines.clear()

        self.rows = rows
        self.cols = cols

        self.draw_grid()

        self.highlight_rect = self.scene().addRect(
            0, 0, self.grid_size, self.grid_size, QPen(Qt.PenStyle.NoPen), QBrush(QColor(0, 255, 0, 100))
        )
        self.highlight_rect.setZValue(3)
        self.highlight_rect.hide()

        for widget in widgets:
            self.scene().addItem(widget)

        return True


class WidgetGridController(QObject):
    def __init__(self, view: GridGraphicsView) -> None:
        super().__init__()
        self.view: GridGraphicsView = view

    def add(self, item: WidgetItem):
        grid_size = self.view.grid_size
        rows, cols = self.view.rows, self.view.cols

        # Calculate final spans before position checking
        final_span_x = max(item.span_x, ((item.min_width + self.view.grid_size - 1) // self.view.grid_size))
        final_span_y = max(item.span_y, ((item.min_height + self.view.grid_size - 1) // self.view.grid_size))

        # Pre-apply the spans to ensure correct collision detection
        item.set_span(final_span_x, final_span_y)

        # Iterate through possible positions with corrected spans
        for row in range(rows - final_span_y + 1):
            for col in range(cols - final_span_x + 1):
                test_pos = QPointF(col * grid_size, row * grid_size)

                # Create a rect that covers the entire final span area
                span_rect = QRectF(
                    test_pos,
                    QPointF(test_pos.x() + (final_span_x * grid_size), test_pos.y() + (final_span_y * grid_size)),
                )

                # Temporarily position the item for accurate collision testing
                original_pos = item.pos()
                item.setPos(test_pos)

                # Get all items at the test position
                colliding_items = [
                    i for i in self.view.scene().items(span_rect) if isinstance(i, WidgetItem) and i != item
                ]

                # Reset position
                item.setPos(original_pos)

                if not colliding_items:
                    # Position is valid, place the widget
                    item.setPos(test_pos)
                    self.view.scene().addItem(item)
                    item.item_deleted.connect(functools.partial(self.remove_widget))
                    return

        # If we get here, no valid position was found

    def add_to_pos(self, item: WidgetItem, x, y):
        grid_size = self.view.grid_size
        item.setPos(x * grid_size, y * grid_size)
        self.view.scene().addItem(item)
        item.item_deleted.connect(functools.partial(self.remove_widget))

    def remove_widget(self, widget):
        self.view.scene().removeItem(widget)

    def get_widgets(self) -> list:
        widgets = []
        for item in self.view.scene().items():
            if isinstance(item, WidgetItem):
                widget_info = {
                    "pos": (item.pos().x() // item.grid_size, item.pos().y() // item.grid_size),
                    "span_x": item.span_x,
                    "span_y": item.span_y,
                    "info": item.info,
                    "kind": item.kind,
                    "title": item.title,
                }
                widgets.append(widget_info)
        return widgets

    def load(self, item_loader: Callable[[dict], WidgetItem], items: list[dict]):
        for item in items:
            widget_item = item_loader(item)
            self.add_to_pos(widget_item, item["pos"][0], item["pos"][1])


class WidgetPalette(QWidget):
    def __init__(self, graphics_view, parent=None):
        super().__init__(parent)
        self.graphics_view = graphics_view
        self.controller = WidgetGridController(self.graphics_view)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        self.tree = QTreeView()
        self.tree.setHeaderHidden(True)
        layout.addWidget(self.tree)

        self.model = DictTreeModel({})
        self.tree.setModel(self.model)

    def add_widget(self, widget_name):
        self.controller.add(WidgetItem(widget_name, self.graphics_view))

    def remove_widget(self, widget):
        self.graphics_view.scene().removeItem(widget)


class SettingsWindow(QDialog):
    on_applied = Signal()

    def __init__(self, parent, settings: QSettings):
        super().__init__(parent=parent)

        self.settings = settings

        self.root_layout = QVBoxLayout()
        self.setLayout(self.root_layout)

        self.form = QFormLayout()
        self.root_layout.addLayout(self.form)

        self.form.addRow(Divider("Grid"))

        self.grid_size = QSpinBox(minimum=8, maximum=256, singleStep=2, value=self.settings.value("grid", 48, int))  # type: ignore
        self.form.addRow("Grid Size", self.grid_size)

        self.grid_rows = QSpinBox(minimum=1, maximum=256, singleStep=2, value=self.settings.value("rows", 10, int))  # type: ignore
        self.form.addRow("Grid Rows", self.grid_rows)

        self.grid_cols = QSpinBox(minimum=1, maximum=256, singleStep=2, value=self.settings.value("cols", 10, int))  # type: ignore
        self.form.addRow("Grid Columns", self.grid_cols)

        self.form.addRow(Divider("Network"))

        self.net_ip = QLineEdit(self.settings.value("ip", "10.0.0.2", str), placeholderText="***.***.***.***")  # type: ignore
        ip_range = "(?:[0-1]?[0-9]?[0-9]|2[0-4][0-9]|25[0-5])"
        ip_regex = QRegularExpression("^" + ip_range + "\\." + ip_range + "\\." + ip_range + "\\." + ip_range + "$")
        ip_validator = QRegularExpressionValidator(ip_regex)
        self.net_ip.setValidator(ip_validator)
        self.form.addRow("IP Address", self.net_ip)

        self.net_port = QSpinBox(minimum=1024, maximum=65535, value=self.settings.value("port", 8765, int))  # type: ignore
        self.form.addRow("Port", self.net_port)

        self.button_layout = QHBoxLayout()
        self.button_layout.addStretch()
        self.root_layout.addLayout(self.button_layout)

        self.apply_button = QPushButton("Apply")
        self.apply_button.clicked.connect(self.apply)
        self.button_layout.addWidget(self.apply_button)

    def apply(self):
        self.on_applied.emit()


class Application(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("KevinbotLib Dashboard")

        self.settings = QSettings("kevinbotlib", "dashboard")

        self.logger = Logger()

        self.client = CommunicationClient(
            host=self.settings.value("ip", "10.0.0.2", str),  # type: ignore
            port=self.settings.value("port", 8765, int),  # type: ignore
            on_disconnect=self.on_disconnect,
            on_connect=self.on_connect,
        )
        self.client.connect()

        self.notifier = Notifier(self)

        self.menu = self.menuBar()
        self.menu.setNativeMenuBar(False)

        self.file_menu = self.menu.addMenu("&File")

        self.save_action = self.file_menu.addAction("Save Layout", self.save_slot)
        self.save_action.setShortcut("Ctrl+S")

        self.edit_menu = self.menu.addMenu("&Edit")

        self.settings_action = self.edit_menu.addAction("Settings", self.open_settings)
        self.settings_action.setShortcut("Ctrl+,")

        self.status = self.statusBar()

        self.connection_status = QLabel("Robot Disconnected")
        self.status.addWidget(self.connection_status)

        self.ip_status = QLabel(str(self.settings.value("ip", "10.0.0.2", str)), alignment=Qt.AlignmentFlag.AlignCenter)
        self.status.addWidget(self.ip_status, 1)

        self.latency_status = QLabel("Latency: 0.00")
        self.status.addPermanentWidget(self.latency_status)

        main_widget = QWidget()
        self.setCentralWidget(main_widget)

        layout = QHBoxLayout(main_widget)

        self.graphics_view = GridGraphicsView(
            grid_size=self.settings.value("grid", 48, int),  # type: ignore
            rows=self.settings.value("rows", 10, int),  # type: ignore
            cols=self.settings.value("cols", 10, int),  # type: ignore
        )
        palette = WidgetPalette(self.graphics_view)
        self.model = palette.model
        self.tree = palette.tree

        layout.addWidget(self.graphics_view)
        layout.addWidget(palette)

        self.latency_timer = QTimer()
        self.latency_timer.setInterval(1000)
        self.latency_timer.timeout.connect(self.update_latency)
        self.latency_timer.start()

        self.update_timer = QTimer()
        self.update_timer.setInterval(100)
        self.update_timer.timeout.connect(self.update_tree)
        self.update_timer.start()

        self.controller = WidgetGridController(self.graphics_view)
        self.controller.load(self.item_loader, self.settings.value("layout", [], type=list))  # type: ignore

        self.settings_window = SettingsWindow(self, self.settings)
        self.settings_window.on_applied.connect(self.refresh_settings)

    def update_latency(self):
        if self.client.websocket:
            self.latency_status.setText(f"Latency: {self.client.websocket.latency:.2f}ms")

    @Slot()
    def update_tree(self):
        # Get the latest data
        data_store = self.client.get_keys()
        data = {}

        # here we process what data can be displayed
        for key, value in [(key, self.client.get_raw(key)) for key in data_store]:
            if not value:
                continue

            if "struct" in value and "dashboard" in value["struct"]:
                structured = {}
                for viewable in value["struct"]["dashboard"]:
                    display = ""
                    if "element" in viewable:
                        raw = value[viewable["element"]]
                        if "format" in viewable:
                            fmt = viewable["format"]
                            if fmt == "percent":
                                display = f"{raw * 100:.2f}%"
                            elif fmt == "degrees":
                                display = f"{raw}°"
                            elif fmt == "radians":
                                display = f"{raw} rad"
                            elif fmt.startswith("limit:"):
                                limit = int(fmt.split(":")[1])
                                display = raw[:limit]
                            else:
                                display = raw

                    structured[viewable["element"]] = display
                data[key] = structured
            else:
                self.logger.error(f"Could not display {key}, it dosen't contain a structure")

        def to_hierarchical_dict(flat_dict: dict):
            """Convert a flat dictionary into a hierarchical one based on '/'."""
            hierarchical_dict = {}
            for key, value in flat_dict.items():
                parts = key.split("/")
                d = hierarchical_dict
                for part in parts[:-1]:
                    d = d.setdefault(part, {})
                d[parts[-1]] = {"items": value, "key": key}
            return hierarchical_dict

        # Convert flat dictionary to hierarchical

        expanded_indexes = []

        def store_expansion(parent):
            for row in range(self.model.rowCount(parent)):
                index = self.model.index(row, 0, parent)
                if self.tree.isExpanded(index):
                    expanded_indexes.append((self.get_index_path(index), True))
                store_expansion(index)

        store_expansion(QModelIndex())

        # Store selection
        selected_paths = self.get_selection_paths()

        # Update data...
        h = to_hierarchical_dict(data)
        self.model.update_data(h)

        # Restore states
        def restore_expansion():
            for path, was_expanded in expanded_indexes:
                index = self.get_index_from_path(path)
                if index.isValid() and was_expanded:
                    self.tree.setExpanded(index, True)

        restore_expansion()

        # Restore selection
        self.restore_selection(selected_paths)

    def get_selection_paths(self):
        return [
            self.get_index_path(index) for index in self.tree.selectionModel().selectedIndexes() if index.column() == 0
        ]

    def restore_selection(self, paths):
        selection_model = self.tree.selectionModel()
        selection_model.clear()
        for path in paths:
            index = self.get_index_from_path(path)
            if index.isValid():
                selection_model.select(index, selection_model.SelectionFlag.Select | selection_model.SelectionFlag.Rows)

    def get_index_path(self, index):
        path = []
        while index.isValid():
            path.append(index.row())
            index = self.model.parent(index)
        return tuple(reversed(path))

    def get_index_from_path(self, path):
        index = QModelIndex()
        for row in path:
            index = self.model.index(row, 0, index)
        return index

    def on_connect(self):
        self.connection_status.setText("Robot Connected")
        self.update_tree()

    def on_disconnect(self):
        self.connection_status.setText("Robot Disconnected")

    def refresh_settings(self):
        self.settings.setValue("ip", self.settings_window.net_ip.text())
        self.settings.setValue("port", self.settings_window.net_port.value())
        self.client.host = self.settings.value("ip", "10.0.0.2", str)  # type: ignore
        self.client.port = self.settings.value("port", 8765, int)  # type: ignore

        self.ip_status.setText(str(self.settings.value("ip", "10.0.0.2", str)))

        self.settings.setValue("grid", self.settings_window.grid_size.value())
        self.settings.setValue("rows", self.settings_window.grid_rows.value())
        self.settings.setValue("cols", self.settings_window.grid_cols.value())

        self.graphics_view.set_grid_size(self.settings.value("grid", 48, int))  # type: ignore
        if not self.graphics_view.resize_grid(
            self.settings.value("rows", 10, int), self.settings.value("cols", 10, int)
        ):  # type: ignore
            QMessageBox.critical(self.settings_window, "Error", "Cannot resize grid to the specified dimensions.")
            self.settings.setValue("rows", self.graphics_view.rows)
            self.settings.setValue("cols", self.graphics_view.cols)

    def item_loader(self, item: dict) -> WidgetItem:
        kind = item["kind"]
        title = item["title"]
        span_x = item["span_x"]
        span_y = item["span_y"]
        data = item["info"]

        match kind:
            case "base":
                return WidgetItem(title, self.graphics_view, span_x, span_y, data)

        return WidgetItem(title, self.graphics_view, span_x, span_y)

    @override
    def closeEvent(self, event: QCloseEvent):
        reply = QMessageBox.question(
            self,
            "Save Layout",
            "Do you want to save the current layout before exiting?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.save_slot()
            event.accept()
        elif reply == QMessageBox.StandardButton.No:
            event.accept()
        else:
            event.ignore()

    def save_slot(self):
        self.settings.setValue("layout", self.controller.get_widgets())
        self.notifier.toast("Layout Saved", "Layout saved successfully", severity=Severity.Success)

    def open_settings(self):
        self.settings_window.show()
