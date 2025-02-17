import functools
from typing import override

from PySide6.QtCore import QObject, QPointF, QRectF, QSize, Qt, Signal, QRect
from PySide6.QtGui import QAction, QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QGraphicsObject,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QMainWindow,
    QMenu,
    QPushButton,
    QStyleOptionGraphicsItem,
    QVBoxLayout,
    QWidget,
)

from kevinbotlib_dashboard.grid_theme import Themes


class WidgetItem(QGraphicsObject):
    item_deleted = Signal(object)

    def __init__(self, title, grid: "GridGraphicsView", span_x=1, span_y=1):
        super().__init__()

        self.info = {}
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
    def __init__(self, parent=None, theme: Themes = Themes.Dark):
        super().__init__(parent)
        self.grid_size = 48
        self.rows, self.cols = 10, 10
        self.theme = theme
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate)
        self.setBackgroundBrush(QColor(theme.value.background))
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
        grid_size = self.grid_size
        rows, cols = self.rows, self.cols
        pen = QPen(QColor(self.theme.value.border), 1, Qt.PenStyle.DashLine)
        for i in range(cols + 1):
            x = i * grid_size
            self.scene().addLine(x, 0, x, rows * grid_size, pen)
        for i in range(rows + 1):
            y = i * grid_size
            self.scene().addLine(0, y, cols * grid_size, y, pen)
        self.scene().setSceneRect(0, 0, cols * grid_size, rows * grid_size)

    def can_resize_to(self, new_rows, new_cols):
        """Check if all current widgets would fit in the new dimensions"""
        for item in self.scene().items():
            if isinstance(item, WidgetItem):
                # Check if widget would be out of bounds
                if (item.pos().x() + item.span_x * self.grid_size > new_cols * self.grid_size or
                    item.pos().y() + item.span_y * self.grid_size > new_rows * self.grid_size):
                    return False
        return True

    def resize_grid(self, rows, cols):
        """Attempt to resize the grid while preserving widget instances"""
        # First check if resize is possible
        if not self.can_resize_to(rows, cols):
            print(f"Cannot resize to {rows}x{cols} - widgets would be out of bounds")
            return False
            
        widgets = [item for item in self.scene().items() if isinstance(item, WidgetItem)]
        
        for widget in widgets:
            self.scene().removeItem(widget)
        
        self.scene().clear()
        
        self.rows = rows
        self.cols = cols
        
        self.draw_grid()
        
        self.highlight_rect = self.scene().addRect(
            0, 0, self.grid_size, self.grid_size, 
            QPen(Qt.PenStyle.NoPen), 
            QBrush(QColor(0, 255, 0, 100))
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
        final_span_x = max(
            item.span_x,
            ((item.min_width + self.view.grid_size - 1) // self.view.grid_size)
        )
        final_span_y = max(
            item.span_y,
            ((item.min_height + self.view.grid_size - 1) // self.view.grid_size)
        )
        
        # Pre-apply the spans to ensure correct collision detection
        item.set_span(final_span_x, final_span_y)

        # Iterate through possible positions with corrected spans
        for row in range(rows - final_span_y + 1):
            for col in range(cols - final_span_x + 1):
                test_pos = QPointF(col * grid_size, row * grid_size)
                
                # Create a rect that covers the entire final span area
                span_rect = QRectF(
                    test_pos,
                    QPointF(
                        test_pos.x() + (final_span_x * grid_size),
                        test_pos.y() + (final_span_y * grid_size)
                    )
                )
                
                # Temporarily position the item for accurate collision testing
                original_pos = item.pos()
                item.setPos(test_pos)
                
                # Get all items at the test position
                colliding_items = [i for i in self.view.scene().items(span_rect)
                                if isinstance(i, WidgetItem) and i != item]
                
                # Reset position
                item.setPos(original_pos)
                
                if not colliding_items:
                    # Position is valid, place the widget
                    item.setPos(test_pos)
                    self.view.scene().addItem(item)
                    item.item_deleted.connect(functools.partial(self.remove_widget))
                    return

        # If we get here, no valid position was found

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


class WidgetPalette(QWidget):
    def __init__(self, graphics_view, parent=None):
        super().__init__(parent)
        self.graphics_view = graphics_view
        self.controller = WidgetGridController(self.graphics_view)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        resize_layout = QHBoxLayout()
        btn_8x8 = QPushButton("8x8")
        btn_12x12 = QPushButton("12x12")
        btn_8x8.clicked.connect(lambda: self.graphics_view.resize_grid(8, 8))
        btn_12x12.clicked.connect(lambda: self.graphics_view.resize_grid(12, 12))
        resize_layout.addWidget(btn_8x8)
        resize_layout.addWidget(btn_12x12)
        layout.addLayout(resize_layout)

        widgets = ["A", "B", "C", "D", "E"]
        for widget_name in widgets:
            button = QPushButton(widget_name)
            button.clicked.connect(lambda _, name=widget_name: self.add_widget(name))
            layout.addWidget(button)
        layout.addStretch()

    def add_widget(self, widget_name):
        self.controller.add(WidgetItem(widget_name, self.graphics_view))
        print(self.controller.get_widgets())

    def remove_widget(self, widget):
        self.graphics_view.scene().removeItem(widget)


class Application(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("KevinbotLib Dashboard")

        main_widget = QWidget()
        self.setCentralWidget(main_widget)

        layout = QHBoxLayout(main_widget)

        graphics_view = GridGraphicsView()
        palette = WidgetPalette(graphics_view)

        layout.addWidget(graphics_view)
        layout.addWidget(palette)
