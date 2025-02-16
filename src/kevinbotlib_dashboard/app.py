import functools
from typing import override

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal, QObject
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QAction
from PySide6.QtWidgets import (
    QGraphicsObject,
    QMenu,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QStyleOptionGraphicsItem,
    QVBoxLayout,
    QWidget,
)

class WidgetItem(QGraphicsObject):
    item_deleted = Signal(object)

    def __init__(self, title, grid: 'GridGraphicsView', span_x=1, span_y=1, margin=4):
        super().__init__()
        self.title = title
        self.grid_size = grid.grid_size
        self.span_x = span_x
        self.span_y = span_y
        self.width = grid.grid_size * span_x
        self.height = grid.grid_size * span_y
        self.margin = margin
        self.setAcceptHoverEvents(True)
        self.setFlags(
            QGraphicsObject.GraphicsItemFlag.ItemIsMovable | QGraphicsObject.GraphicsItemFlag.ItemIsSelectable
        )
        self.setZValue(1)
        self.resizing = False
        self.resize_grip_size = 15
        self.min_width = self.grid_size*2  # Minimum width in pixels
        self.min_height = self.grid_size*2 # Minimum height in pixels
        self.view = grid


    def boundingRect(self):  # noqa: N802
        return QRectF(0, 0, self.width, self.height)
    
    def paint(self, painter: QPainter, _option: QStyleOptionGraphicsItem, /, _widget: QWidget | None = None):  # type: ignore
        painter.setBrush(QBrush(QColor("white")))
        painter.setPen(QPen(QColor("#ccc"), 1))
        painter.drawRoundedRect(QRectF(self.margin, self.margin, self.width - 2 * self.margin, self.height - 2 * self.margin), 10, 10)

        title_rect = QRectF(self.margin, self.margin, self.width - 2 * self.margin, 30)

        painter.setBrush(QBrush(QColor("#f0f0f0"))) # Example background color for the title bar
        painter.setPen(Qt.PenStyle.NoPen) #NoPen for the rect
        painter.drawRoundedRect(title_rect, 10, 10) #Round the bottom corners slightly to prevent a sharp edge
        painter.drawRect(QRectF(title_rect.x(), title_rect.y()+10, title_rect.width(), title_rect.height()-10))

        painter.setPen(QPen(QColor("black")))
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
            new_height = max(self.min_height, self.start_height + delta_y) # Enforce minimum height

            new_span_x = round(new_width / self.grid_size)
            new_span_y = round(new_height / self.grid_size)

            new_width = new_span_x * self.grid_size # Recalculate width
            new_height = new_span_y * self.grid_size # Recalculate height

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
    def __init__(self, parent=None):
        super().__init__(parent)
        self.grid_size = 48
        self.rows, self.cols = 10, 10
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate)
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
        # return True

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
        pen = QPen(QColor("#e0e0e0"), 1, Qt.PenStyle.DashLine)
        for i in range(cols + 1):
            x = i * grid_size
            self.scene().addLine(x, 0, x, rows * grid_size, pen)
        for i in range(rows + 1):
            y = i * grid_size
            self.scene().addLine(0, y, cols * grid_size, y, pen)
        self.scene().setSceneRect(0, 0, cols * grid_size, rows * grid_size)

class WidgetGridController(QObject):
    def __init__(self, view: GridGraphicsView) -> None:
        super().__init__()
        self.view: GridGraphicsView = view

    def add(self, item: WidgetItem):
        grid_size = self.view.grid_size
        rows, cols = self.view.rows, self.view.cols

        for row in range(rows - item.span_x + 1):
            for col in range(cols - item.span_x + 1):
                valid_position = True
                for i in range(item.span_y):
                    for j in range(item.span_x):
                        pos = QPointF((col + j) * grid_size, (row + i) * grid_size)
                        rect = QRectF(pos, QPointF(pos.x() + grid_size, pos.y() + grid_size))
                        items = self.view.scene().items(rect)
                        if any(isinstance(item, WidgetItem) for item in items):
                            valid_position = False
                            break
                    if not valid_position:
                        break
                if valid_position:
                    item.setPos(col * grid_size, row * grid_size)
                    item.set_span(((item.min_width + self.view.grid_size - 1) // self.view.grid_size), ((item.min_height + self.view.grid_size - 1) // self.view.grid_size))
                    self.view.scene().addItem(item)
                    item.item_deleted.connect(functools.partial(self.remove_widget))
                    return

    def remove_widget(self, widget):
        self.view.scene().removeItem(widget)

class WidgetPalette(QWidget):
    def __init__(self, graphics_view, parent=None):
        super().__init__(parent)
        self.graphics_view = graphics_view
        self.controller = WidgetGridController(self.graphics_view)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        widgets = ["A", "B", "C", "D", "E"]
        for widget_name in widgets:
            button = QPushButton(widget_name)
            button.clicked.connect(lambda _, name=widget_name: self.add_widget(name))
            layout.addWidget(button)
        layout.addStretch()

    def add_widget(self, widget_name):
        self.controller.add(WidgetItem(widget_name, self.graphics_view))

    def remove_widget(self, widget):
        self.graphics_view.scene().removeItem(widget)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Widget Grid")

        main_widget = QWidget()
        self.setCentralWidget(main_widget)

        layout = QHBoxLayout(main_widget)

        graphics_view = GridGraphicsView()
        palette = WidgetPalette(graphics_view)

        layout.addWidget(graphics_view)
        layout.addWidget(palette)
