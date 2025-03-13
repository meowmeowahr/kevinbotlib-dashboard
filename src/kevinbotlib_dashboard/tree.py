from typing import Any, override

from PySide6.QtCore import QAbstractItemModel, QModelIndex, QPersistentModelIndex, Qt


class TreeItem:
    def __init__(self, data: Any, key: str = "", parent: "TreeItem | None" = None):
        self.data = data
        self.key = key
        self.parent_item = parent

        self.child_items: list[TreeItem] = []
        if isinstance(data, dict):
            for k, v in data.items():
                self.child_items.append(TreeItem(v, k, self))
        self.userdata = None

        if len(self.child_items) > 0:
            for child in self.child_items:
                if child.key == "key":
                    self.userdata = child.data
                    self.child_items.clear()  # This is the sendable, dont show any more data

    def child(self, row: int) -> "TreeItem":
        if 0 <= row < len(self.child_items):
            return self.child_items[row]
        return None

    def child_count(self) -> int:
        return len(self.child_items)

    def row(self) -> int:
        if self.parent_item:
            return self.parent_item.child_items.index(self)
        return 0

    def parent(self) -> "TreeItem":
        return self.parent_item


class DictTreeModel(QAbstractItemModel):
    def __init__(self, data: dict):
        super().__init__()
        self.root_item = TreeItem(data)

    def index(self, row: int, column: int, parent: QModelIndex = QModelIndex()) -> QModelIndex:  # noqa: B008
        if not self.hasIndex(row, column, parent):
            return QModelIndex()

        parent_item = self.root_item if not parent.isValid() else parent.internalPointer()

        child_item = parent_item.child(row)
        if child_item:
            return self.createIndex(row, column, child_item)
        return QModelIndex()

    def parent(self, index: QModelIndex) -> QModelIndex:
        if not index.isValid():
            return QModelIndex()

        child_item = index.internalPointer()
        parent_item = child_item.parent()

        if parent_item == self.root_item:
            return QModelIndex()

        return self.createIndex(parent_item.row(), 0, parent_item)

    @override
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.column() > 0:
            return 0

        parent_item = self.root_item if not parent.isValid() else parent.internalPointer()

        return parent_item.child_count()

    @override
    def columnCount(self, /, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 1

    @override
    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None

        item = index.internalPointer()

        if role == Qt.ItemDataRole.DisplayRole:
            if isinstance(item.data, dict):
                # Show userdata alongside the key if it exists
                if item.userdata is not None:
                    return f"{item.key} [{item.userdata}]"
                return f"{item.key}"
        elif role == Qt.ItemDataRole.UserRole:
            return item.userdata

        return None

    def update_data(self, new_data: dict):
        self.beginResetModel()
        self.root_item = TreeItem(new_data)
        self.endResetModel()
