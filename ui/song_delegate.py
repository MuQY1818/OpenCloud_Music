from PySide6.QtWidgets import QStyledItemDelegate
from PySide6.QtGui import QPainter, QColor, QFont
from PySide6.QtCore import QRect, Qt, QSize

class SongItemDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        painter.save()
        rect = option.rect

        # 选中时画蓝色高亮
        if option.state & QStyledItemDelegate.State_Selected:
            margin = 6
            highlight_rect = rect.adjusted(margin, margin, -margin, -margin)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(QColor("#3D82F0"))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(highlight_rect, 12, 12)

        # 歌名
        title = index.data(Qt.DisplayRole)
        # 歌手（我们用 UserRole 存）
        artist = index.data(Qt.UserRole)

        # 歌名字体
        font = painter.font()
        font.setBold(True)
        font.setPointSize(14)
        painter.setFont(font)
        painter.setPen(QColor("white"))
        title_rect = QRect(rect.left(), rect.top() + 12, rect.width(), 22)
        painter.drawText(title_rect, Qt.AlignHCenter | Qt.AlignVCenter, title)

        # 歌手字体
        font.setBold(False)
        font.setPointSize(11)
        painter.setFont(font)
        painter.setPen(QColor("#B3B3B3"))
        artist_rect = QRect(rect.left(), rect.top() + 36, rect.width(), 18)
        painter.drawText(artist_rect, Qt.AlignHCenter | Qt.AlignVCenter, artist)

        painter.restore()

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), 60) 