import os
import sys
import traceback
import threading
import re
import random

# --- PySide6 Imports ---
from PySide6.QtCore import (
    Qt, QUrl, QSize, QPoint, QRect, QTimer, QPropertyAnimation, QEasingCurve, QObject, Signal
)
from PySide6.QtGui import (
    QGuiApplication, QPixmap, QIcon, QPainter, QColor, QBrush, 
    QPainterPath, QFontDatabase, QAction, QFontMetrics
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QListWidget, QListWidgetItem, QGraphicsDropShadowEffect,
    QSlider, QFrame, QMenu, QFileDialog, QLineEdit
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

# --- Other Libraries ---
import qtawesome as qta

# --- Local Imports ---
from ui.style import STYLE_SHEET
from ui.widgets import ElidedLabel, SongItemWidget
from core.metadata import (
    get_song_metadata, convert_ncm_to_mp3, 
    update_and_embed_metadata, get_cover_data_from_tags
)

# Main Application Window
class NCMPlayerApp(QMainWindow):
    # 定义信号用于跨线程通信
    song_processed = Signal(dict)
    def __init__(self):
        super().__init__()
        # Basic Setup
        self.setWindowTitle("OpenCloud Music")
        self.setMinimumSize(800, 600)
        self.resize(1000, 700)
        
        # 去掉系统标题栏
        self.setWindowFlags(Qt.FramelessWindowHint)
        
        # 添加拖拽相关变量
        self.drag_position = None
        
        # 设置窗口图标
        self.setWindowIcon(qta.icon('fa5s.cloud-download-alt', color='#3D82F0'))
        
        # Add Fonts - Assuming fonts are in a resource file or a known path
        # QFontDatabase.addApplicationFont(":/fonts/Inter-Regular.ttf")
        # QFontDatabase.addApplicationFont(":/fonts/Inter-Bold.ttf")

        # Playback State
        self.playlist_data = []
        self.current_index = -1
        self.is_slider_pressed = False
        self.playback_modes = ['sequential', 'repeat_one', 'shuffle']
        self.current_playback_mode_index = 0
        
        # Media Player
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(1.0) # Full volume initially

        # Connect signals
        self.player.positionChanged.connect(self.update_position)
        self.player.durationChanged.connect(self.update_duration)
        self.player.playbackStateChanged.connect(self.handle_playback_state_changed)
        self.player.mediaStatusChanged.connect(self.handle_media_status)
        self.player.errorOccurred.connect(self.handle_player_error)

        self.lyrics_timer = QTimer(self)
        self.lyrics_timer.setInterval(100)
        self.lyrics_timer.timeout.connect(self.update_lyrics_highlight)

        self._create_ui()
        self.setStyleSheet(STYLE_SHEET)
        
        # 连接信号到槽函数
        self.song_processed.connect(self.add_song_to_playlist)
        
        self.load_existing_songs()

    def _create_ui(self):
        # --- Central Widget and Main Layout ---
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 自定义标题栏
        self.title_bar = self._create_title_bar()
        main_layout.addWidget(self.title_bar)

        # A QHBoxLayout for the top part (sidebar and main content)
        top_content_layout = QHBoxLayout()
        top_content_layout.setSpacing(0)

        # --- Sidebar ---
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(10, 20, 10, 10)
        
        self.import_button = QPushButton("  导入文件")
        self.import_button.setIcon(qta.icon('fa5s.folder-plus', color='white'))
        self.import_button.clicked.connect(self.select_ncm_files)
        self.import_button.setObjectName("importButton")
        sidebar_layout.addWidget(self.import_button)

        # 搜索框
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索歌曲...")
        self.search_input.setObjectName("searchInput")
        self.search_input.textChanged.connect(self.filter_playlist)
        sidebar_layout.addWidget(self.search_input)

        self.playlist_widget = QListWidget()
        self.playlist_widget.itemClicked.connect(self.play_from_list)
        sidebar_layout.addWidget(self.playlist_widget)
        
        top_content_layout.addWidget(sidebar, 1)

        # --- Main Content Area ---
        content_area = QFrame()
        content_layout = QVBoxLayout(content_area)
        content_layout.setContentsMargins(40, 40, 40, 20)
        top_content_layout.addWidget(content_area, 3)

        # Art and Title
        art_title_layout = QHBoxLayout()
        self.album_art_label = QLabel()
        self.album_art_label.setObjectName("albumArt")
        self.album_art_label.setFixedSize(200, 200)
        self.album_art_label.setAlignment(Qt.AlignCenter)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(25)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(5, 5)
        self.album_art_label.setGraphicsEffect(shadow)

        art_title_layout.addWidget(self.album_art_label)

        title_info_layout = QVBoxLayout()
        title_info_layout.addStretch()
        self.title_label = QLabel("OpenCloud Music")
        self.title_label.setObjectName("mainTitle")
        self.artist_label = QLabel("选择歌曲开始播放")
        self.artist_label.setObjectName("mainArtist")
        title_info_layout.addWidget(self.title_label)
        title_info_layout.addWidget(self.artist_label)
        title_info_layout.addStretch()
        art_title_layout.addLayout(title_info_layout)
        art_title_layout.addStretch()
        content_layout.addLayout(art_title_layout)
        
        content_layout.addStretch(1)

        # Lyrics
        self.lyrics_widget = QListWidget()
        self.lyrics_widget.setObjectName("lyricsWidget")
        content_layout.addWidget(self.lyrics_widget)
        
        content_layout.addStretch(1)

        # Add top part to the main layout
        main_layout.addLayout(top_content_layout, 1)

        # --- Player Controls (Now at the bottom) ---
        player_controls_container = QFrame()
        player_controls_container.setObjectName("playerControls")
        player_controls_layout = QVBoxLayout(player_controls_container)
        player_controls_layout.setContentsMargins(20, 10, 20, 10)
        player_controls_layout.setSpacing(5)

        # Progress Slider
        progress_layout = QHBoxLayout()
        self.current_time_label = QLabel("00:00")
        self.progress_slider = QSlider(Qt.Horizontal)
        self.progress_slider.sliderPressed.connect(self.slider_pressed)
        self.progress_slider.sliderReleased.connect(self.slider_released)
        self.total_time_label = QLabel("00:00")
        progress_layout.addWidget(self.current_time_label)
        progress_layout.addWidget(self.progress_slider)
        progress_layout.addWidget(self.total_time_label)
        
        # Bottom row with all controls
        bottom_controls_layout = QHBoxLayout()
        
        # --- FIX: Re-structured controls for proper centering ---
        # Left container for playback mode (takes 1/3 of space)
        left_controls = QHBoxLayout()
        self.playback_mode_button = QPushButton()
        self.update_playback_mode_icon()
        self.playback_mode_button.clicked.connect(self.cycle_playback_mode)
        left_controls.addWidget(self.playback_mode_button)
        left_controls.addStretch()

        # Center container for main buttons (takes 1/3 of space)
        center_controls = QHBoxLayout()
        center_controls.addStretch()
        self.prev_button = QPushButton(qta.icon('fa5s.step-backward', color='#B3B3B3'), "")
        self.prev_button.clicked.connect(self.prev_song)
        self.play_pause_button = QPushButton(qta.icon('fa5s.play', color='black'), "")
        self.play_pause_button.setIconSize(QSize(22, 22))
        self.play_pause_button.setObjectName("playPauseButton")
        self.play_pause_button.clicked.connect(self.toggle_play_pause)
        self.next_button = QPushButton(qta.icon('fa5s.step-forward', color='#B3B3B3'), "")
        self.next_button.clicked.connect(self.next_song)
        center_controls.addWidget(self.prev_button)
        center_controls.addWidget(self.play_pause_button)
        center_controls.addWidget(self.next_button)
        center_controls.addStretch()
        
        # Right container for volume (takes 1/3 of space)
        right_controls = QHBoxLayout()
        right_controls.addStretch()
        self.volume_icon = QLabel()
        self.volume_icon.setPixmap(qta.icon('fa5s.volume-up', color='#B3B3B3').pixmap(QSize(20, 20)))
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(100)
        self.volume_slider.valueChanged.connect(self.set_volume)
        self.volume_slider.setFixedWidth(120)
        right_controls.addWidget(self.volume_icon)
        right_controls.addWidget(self.volume_slider)

        bottom_controls_layout.addLayout(left_controls, 1)
        bottom_controls_layout.addLayout(center_controls, 1)
        bottom_controls_layout.addLayout(right_controls, 1)
        # --- END FIX ---

        player_controls_layout.addLayout(progress_layout)
        player_controls_layout.addLayout(bottom_controls_layout)
        
        main_layout.addWidget(player_controls_container)

        self.playlist_widget.itemClicked.connect(self.play_from_list)
        self.lyrics_widget.itemClicked.connect(self.seek_from_lyric)
    
    def _create_title_bar(self):
        """创建自定义标题栏"""
        title_bar = QFrame()
        title_bar.setObjectName("titleBar")
        title_bar.setFixedHeight(40)
        
        layout = QHBoxLayout(title_bar)
        layout.setContentsMargins(15, 0, 10, 0)
        layout.setSpacing(10)
        
        # 应用图标和标题
        icon_label = QLabel()
        icon_label.setPixmap(qta.icon('fa5s.cloud-download-alt', color='#3D82F0').pixmap(QSize(20, 20)))
        layout.addWidget(icon_label)
        
        title_label = QLabel("OpenCloud Music")
        title_label.setObjectName("titleLabel")
        layout.addWidget(title_label)
        
        layout.addStretch()
        
        # 窗口控制按钮
        self.minimize_btn = QPushButton()
        self.minimize_btn.setIcon(qta.icon('fa5s.minus', color='#B3B3B3'))
        self.minimize_btn.setObjectName("windowControlBtn")
        self.minimize_btn.clicked.connect(self.showMinimized)
        
        self.maximize_btn = QPushButton()
        self.maximize_btn.setIcon(qta.icon('fa5s.square', color='#B3B3B3'))
        self.maximize_btn.setObjectName("windowControlBtn")
        self.maximize_btn.clicked.connect(self.toggle_maximize)
        
        self.close_btn = QPushButton()
        self.close_btn.setIcon(qta.icon('fa5s.times', color='#B3B3B3'))
        self.close_btn.setObjectName("closeBtn")
        self.close_btn.clicked.connect(self.close)
        
        layout.addWidget(self.minimize_btn)
        layout.addWidget(self.maximize_btn)
        layout.addWidget(self.close_btn)
        
        return title_bar
    
    def toggle_maximize(self):
        """切换最大化状态"""
        if self.isMaximized():
            self.showNormal()
            self.maximize_btn.setIcon(qta.icon('fa5s.square', color='#B3B3B3'))
        else:
            self.showMaximized()
            self.maximize_btn.setIcon(qta.icon('fa5s.clone', color='#B3B3B3'))
    
    def mousePressEvent(self, event):
        """处理鼠标按下事件 - 用于拖拽窗口"""
        if event.button() == Qt.LeftButton:
            # 检查是否点击在标题栏区域
            if hasattr(self, 'title_bar') and self.title_bar.geometry().contains(event.position().toPoint()):
                self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """处理鼠标移动事件 - 用于拖拽窗口"""
        if self.drag_position and event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        """处理鼠标释放事件"""
        self.drag_position = None
        super().mouseReleaseEvent(event)
    
    def filter_playlist(self, search_text):
        """根据搜索文本过滤播放列表"""
        search_text = search_text.lower().strip()
        
        for i in range(self.playlist_widget.count()):
            item = self.playlist_widget.item(i)
            
            if not search_text:
                # 如果搜索框为空，显示所有项
                item.setHidden(False)
            else:
                # 直接在显示文本中搜索
                item_text = item.text().lower()
                item.setHidden(search_text not in item_text)

    def threaded_task(self, func, *args):
        # A simple threading helper
        thread = threading.Thread(target=func, args=args)
        thread.daemon = True
        thread.start()

    def select_ncm_files(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, 
            "选择NCM文件",
            "",
            "NCM Files (*.ncm)"
        )
        if file_paths:
            self.threaded_task(self.process_files, file_paths)

    def process_files(self, ncm_paths):
        for path in ncm_paths:
            file_to_check = os.path.basename(path).replace('.ncm', '.mp3')
            if any(file_to_check in song['path'] for song in self.playlist_data):
                print(f"Skipping duplicate: {file_to_check}")
                continue

            converted_path = convert_ncm_to_mp3(path)
            if converted_path:
                update_and_embed_metadata(converted_path, "", "") # Let it search by filename
                metadata = get_song_metadata(converted_path)
                if metadata:
                    # 发射信号，在主线程中处理UI更新
                    self.song_processed.emit(metadata)
    
    def add_song_to_playlist(self, song_metadata):
        # 检查是否已存在相同的歌曲
        for existing_song in self.playlist_data:
            if existing_song['path'] == song_metadata['path']:
                return  # 如果已存在，直接返回
        
        self.playlist_data.append(song_metadata)
        
        # 直接在主线程中更新UI
        display_text = f"{song_metadata['title']} - {song_metadata['artist']}"
        list_item = QListWidgetItem(display_text)
        self.playlist_widget.addItem(list_item)
        
        print(f"Added song to playlist: {display_text}")  # 调试信息

    def load_existing_songs(self):
        output_dir = 'output'
        if not os.path.exists(output_dir):
            return
        
        for filename in sorted(os.listdir(output_dir)):
            if filename.lower().endswith('.mp3'):
                file_path = os.path.join(output_dir, filename)
                metadata = get_song_metadata(file_path)
                if metadata:
                    self.playlist_data.append(metadata)
                    display_text = f"{metadata['title']} - {metadata['artist']}"
                    list_item = QListWidgetItem(display_text)
                    self.playlist_widget.addItem(list_item)
        
    def play_from_list(self, item):
        self.current_index = self.playlist_widget.row(item)
        self.play_current_song()
        
    def play_current_song(self):
        if 0 <= self.current_index < len(self.playlist_data):
            song = self.playlist_data[self.current_index]
            self.player.setSource(QUrl.fromLocalFile(song['path']))
            self.player.play()
            
            self.title_label.setText(song['title'])
            self.artist_label.setText(song['artist'])
            
            # Cover pixmap is now loaded on demand
            if song.get('cover_pixmap'):
                 self.album_art_label.setPixmap(song['cover_pixmap'])
            else:
                cover_data = get_cover_data_from_tags(song['path'])
                if cover_data:
                    pixmap = QPixmap()
                    pixmap.loadFromData(cover_data)
                    song['cover_pixmap'] = pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.album_art_label.setPixmap(song['cover_pixmap'])
                else:
                    self.album_art_label.setPixmap(QPixmap()) # Clear pixmap
            
            self.playlist_widget.setCurrentRow(self.current_index)
            
            self.parsed_lyrics = self.parse_lrc(song.get('lyrics', ''))
            self.display_lyrics()
            self.lyrics_timer.start()

    def update_position(self, pos):
        if self.is_slider_pressed:
            return
        self.progress_slider.setValue(pos)
        self.current_time_label.setText(self.format_time(pos))

    def update_duration(self, dur):
        self.progress_slider.setRange(0, dur)
        self.total_time_label.setText(self.format_time(dur))

    def format_time(self, ms):
        seconds = ms // 1000
        minutes = seconds // 60
        seconds %= 60
        return f"{minutes:02}:{seconds:02}"

    def handle_playback_state_changed(self, state):
        """Handles changes in playback state (Playing, Paused, Stopped)."""
        if state == QMediaPlayer.PlayingState:
            self.play_pause_button.setIcon(qta.icon('fa5s.pause', color='black'))
            self.lyrics_timer.start()
        else:  # Paused or Stopped
            self.play_pause_button.setIcon(qta.icon('fa5s.play', color='black'))
            self.lyrics_timer.stop()

    def handle_media_status(self, status):
        """Handles changes in media status (e.g., end of media)."""
        if status == QMediaPlayer.EndOfMedia:
            self.handle_song_finished()

    def handle_player_error(self, error):
        print(f"Player Error: {self.player.errorString()}")

    def slider_pressed(self):
        self.is_slider_pressed = True

    def slider_released(self):
        self.player.setPosition(self.progress_slider.value())
        self.is_slider_pressed = False
        # 拖动进度条后立即更新歌词高亮
        self.update_lyrics_highlight()

    def toggle_play_pause(self):
        # If nothing is loaded yet, and we have songs, load and play the first one.
        if self.player.source().isEmpty() and self.playlist_data:
            self.current_index = 0
            self.play_current_song()
            return
            
        # If it's playing, pause it. Otherwise, play.
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def next_song(self):
        if not self.playlist_data: return
        self.current_index = (self.current_index + 1) % len(self.playlist_data)
        self.play_current_song()
        
    def prev_song(self):
        if not self.playlist_data: return
        if self.player.position() > 3000: # If more than 3s in, restart song
            self.player.setPosition(0)
        else:
            self.current_index = (self.current_index - 1 + len(self.playlist_data)) % len(self.playlist_data)
            self.play_current_song()
            
    def handle_song_finished(self):
        mode = self.playback_modes[self.current_playback_mode_index]
        
        if mode == 'repeat_one':
            self.player.setPosition(0)
            self.player.play()
        elif mode == 'shuffle':
            if len(self.playlist_data) > 1:
                next_index = self.current_index
                while next_index == self.current_index:
                    next_index = random.randint(0, len(self.playlist_data) - 1)
                self.current_index = next_index
                self.play_current_song()
            else:
                self.next_song() # fallback for single song
        else: # sequential
            self.next_song()

    def cycle_playback_mode(self):
        self.current_playback_mode_index = (self.current_playback_mode_index + 1) % len(self.playback_modes)
        self.update_playback_mode_icon()
        
    def update_playback_mode_icon(self):
        mode = self.playback_modes[self.current_playback_mode_index]
        icon_name = 'fa5s.list-ol'
        if mode == 'repeat_one':
            icon_name = 'fa5s.redo-alt'
        elif mode == 'shuffle':
            icon_name = 'fa5s.random'
        self.playback_mode_button.setIcon(qta.icon(icon_name, color='#B3B3B3'))

    def set_volume(self, value):
        volume_float = value / 100.0
        self.audio_output.setVolume(volume_float)
        
        icon_name = 'fa5s.volume-up'
        if value == 0:
            icon_name = 'fa5s.volume-mute'
        elif value < 50:
            icon_name = 'fa5s.volume-down'
        self.volume_icon.setPixmap(qta.icon(icon_name, color='#B3B3B3').pixmap(QSize(20, 20)))

    def seek_from_lyric(self, item):
        row = self.lyrics_widget.row(item)
        if 0 <= row < len(self.parsed_lyrics):
            time_ms = self.parsed_lyrics[row]['time']
            self.player.setPosition(time_ms)

    def parse_lrc(self, lrc_content):
        parsed = []
        if not lrc_content:
            return parsed

        time_regex = re.compile(r'\[(\d{2}):(\d{2})\.(\d{2,3})\]')
        
        for line in lrc_content.split('\n'):
            text = time_regex.sub('', line).strip()
            if not text:
                continue

            for match in time_regex.finditer(line):
                minutes = int(match.group(1))
                seconds = int(match.group(2))
                ms_str = match.group(3).ljust(3, '0')
                ms = int(ms_str)
                
                time_in_ms = (minutes * 60 + seconds) * 1000 + ms
                parsed.append({'time': time_in_ms, 'text': text})
        
        parsed.sort(key=lambda x: x['time'])
        return parsed

    def display_lyrics(self):
        self.lyrics_widget.clear()
        if not self.parsed_lyrics:
            item = QListWidgetItem("暂无歌词")
            item.setTextAlignment(Qt.AlignCenter)
            self.lyrics_widget.addItem(item)
            return
            
        for lyric_data in self.parsed_lyrics:
            item = QListWidgetItem(lyric_data['text'])
            item.setTextAlignment(Qt.AlignCenter)
            self.lyrics_widget.addItem(item)

    def update_lyrics_highlight(self):
        if not self.parsed_lyrics:
            return

        current_time = self.player.position()
        
        current_line = -1
        for i, lyric in enumerate(self.parsed_lyrics):
            if current_time >= lyric['time']:
                current_line = i
            else:
                break
        
        if current_line != self.lyrics_widget.currentRow():
            self.lyrics_widget.setCurrentRow(current_line)
            if current_line >= 0:
                # 直接滚动到当前行，不用动画
                self.lyrics_widget.scrollToItem(
                    self.lyrics_widget.item(current_line), 
                    QListWidget.ScrollHint.PositionAtCenter
                )
    
    def smooth_scroll_to_item(self, row):
        """平滑滚动到指定行"""
        if not hasattr(self, 'scroll_animation'):
            self.scroll_animation = QPropertyAnimation(self.lyrics_widget.verticalScrollBar(), b"value")
            self.scroll_animation.setDuration(150)  # 缩短动画时间到150ms
            self.scroll_animation.setEasingCurve(QEasingCurve.OutQuad)  # 使用更温和的缓动
        
        # 直接使用Qt的scrollToItem，但加上动画
        item = self.lyrics_widget.item(row)
        if item:
            # 获取当前滚动位置
            scrollbar = self.lyrics_widget.verticalScrollBar()
            current_value = scrollbar.value()
            
            # 计算目标位置 - 让选中的歌词显示在中间位置
            item_rect = self.lyrics_widget.visualItemRect(item)
            viewport_height = self.lyrics_widget.viewport().height()
            
            # 目标是让当前行在视窗中央
            center_offset = viewport_height // 2 - item_rect.height() // 2
            target_value = item_rect.top() - center_offset + current_value
            
            # 限制在有效范围内
            target_value = max(0, min(scrollbar.maximum(), target_value))
            
            # 只有当差距大于30像素时才使用动画，否则直接跳转
            if abs(target_value - current_value) > 30:
                if self.scroll_animation.state() == QPropertyAnimation.Running:
                    self.scroll_animation.stop()
                self.scroll_animation.setStartValue(current_value)
                self.scroll_animation.setEndValue(target_value)
                self.scroll_animation.start()
            else:
                # 差距小的话直接设置，不用动画
                scrollbar.setValue(target_value)

    def closeEvent(self, event):
        # Clean up the media player to avoid runtime errors on exit
        self.player.stop()
        self.player.setSource(QUrl())
        event.accept() 