from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics, QPainter, QColor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy


class ElidedLabel(QLabel):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.full_text = text

    def setText(self, text):
        self.full_text = text
        super().setText(text)
        self.elide_text()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.elide_text()

    def elide_text(self):
        fm = QFontMetrics(self.font())
        elided_text = fm.elidedText(self.full_text, Qt.ElideRight, self.width())
        super().setText(elided_text)

# Custom Widget for Playlist Items
class SongItemWidget(QWidget):
    def __init__(self, title, artist, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(65)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)  # 自动填满宽度
        self.is_hovered = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 8, 30, 0)  # 左右边距加大
        layout.setSpacing(2)
        layout.addStretch(3)  # 上方拉伸更大

        self.title_label = ElidedLabel(title)
        self.title_label.setObjectName("songTitle")
        self.title_label.setAlignment(Qt.AlignCenter)
        
        self.artist_label = ElidedLabel(artist)
        self.artist_label.setObjectName("songArtist")
        self.artist_label.setAlignment(Qt.AlignCenter)

        layout.addWidget(self.title_label)
        layout.addWidget(self.artist_label)
        layout.addStretch(1)  # 下方拉伸更小
        
    def enterEvent(self, event):
        self.is_hovered = True
        self.update()
        super().enterEvent(event)
        
    def leaveEvent(self, event):
        self.is_hovered = False
        self.update()
        super().leaveEvent(event) 

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        margin = 6  # 四周留白
        rect = self.rect().adjusted(margin, margin, -margin, -margin)
        
        # 判断自己是否被选中
        from PySide6.QtCore import QRect
        list_widget = self.parent()
        if list_widget and hasattr(list_widget, 'parent') and list_widget.parent():
            list_widget = list_widget.parent()
        
        is_selected = False
        if hasattr(list_widget, 'currentRow'):
            # 通过遍历找到自己的行号
            for row in range(list_widget.count()):
                if list_widget.itemWidget(list_widget.item(row)) is self:
                    if list_widget.currentRow() == row:
                        is_selected = True
                    break
        
        if is_selected:
            # 选中状态 - 蓝色背景
            painter.setBrush(QColor("#3D82F0"))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(rect, 12, 12)
        elif self.is_hovered:
            # 悬浮状态 - 灰色背景
            painter.setBrush(QColor("#1A1A1A"))
            painter.setPen(QColor("#333333"))
            painter.drawRoundedRect(rect, 12, 12)
        
        super().paintEvent(event) 