ACCENT_COLOR = "#3D82F0" # David Tao Album Blue

STYLE_SHEET = f"""
    QMainWindow {{ 
        background-color: #121212;
        border: 1px solid #333333;
    }}
    #titleBar {{
        background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                   stop: 0 #1E1E1E, stop: 1 #121212);
        border-bottom: 1px solid #333333;
    }}
    #titleLabel {{
        color: white;
        font-family: 'Inter', sans-serif;
        font-size: 14px;
        font-weight: 600;
    }}
    #windowControlBtn {{
        background-color: transparent;
        border: none;
        padding: 8px;
        border-radius: 4px;
        min-width: 30px;
        max-width: 30px;
        min-height: 30px;
        max-height: 30px;
    }}
    #windowControlBtn:hover {{
        background-color: #333333;
    }}
    #closeBtn:hover {{
        background-color: #E81123;
    }}
    #sidebar {{ 
        background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                   stop: 0 #0A0A0A, stop: 1 #040404);
        border-right: 1px solid #1A1A1A;
    }}
    #playerControls {{
         background-color: #000000;
         border-top: 1px solid #282828;
    }}
    #importButton {{
        background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                   stop: 0 {ACCENT_COLOR}, stop: 1 #2B6ECC);
        color: white;
        border: none;
        padding: 16px 20px;
        text-align: left;
        font-family: 'Inter', sans-serif;
        font-weight: 600;
        font-size: 15px;
        border-radius: 12px;
        margin: 12px;
        box-shadow: 0 4px 15px rgba(61, 130, 240, 0.3);
    }}
    #importButton:hover {{ 
        background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                   stop: 0 #589AF4, stop: 1 #3D82F0);
        transform: translateY(-1px);
        box-shadow: 0 6px 20px rgba(61, 130, 240, 0.4);
    }}
    #searchInput {{
        background-color: #1A1A1A;
        border: 1px solid #333333;
        border-radius: 8px;
        padding: 10px 12px;
        color: white;
        font-family: 'Inter', sans-serif;
        font-size: 14px;
        margin: 8px 12px;
    }}
    #searchInput:focus {{
        border: 1px solid {ACCENT_COLOR};
        background-color: #222222;
    }}
    QListWidget {{
        background-color: transparent;
        border: none;
        color: #B3B3B3;
        font-family: 'Inter', sans-serif;
        font-size: 14px;
        padding: 5px;
        outline: none;
        show-decoration-selected: 0;
    }}
    QListWidget::item {{
        padding: 12px 16px;
        border-radius: 8px;
        margin: 2px 8px;
        border: none;
        background-color: transparent;
        outline: none;
    }}
    QListWidget::item:hover {{ 
        background-color: #1A1A1A;
        border: 1px solid #333333;
    }}
    QListWidget::item:selected {{ 
        background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0,
                                   stop: 0 rgba(61, 130, 240, 0.2), 
                                   stop: 1 rgba(61, 130, 240, 0.05));
        border: 1px solid {ACCENT_COLOR};
        color: white;
    }}
    QListWidget::item:focus {{
        outline: none;
        border: none;
    }}
    
    ElidedLabel#songTitle {{ 
        font-weight: 600; 
        color: white; 
        font-size: 15px;
        margin-bottom: 2px;
    }}
    ElidedLabel#songArtist {{ 
        color: #B3B3B3; 
        font-size: 13px;
        font-weight: 400;
    }}
    
    #playlist_widget QListWidget::item:selected ElidedLabel#songTitle,
    #playlist_widget QListWidget::item:selected ElidedLabel#songArtist {{
        color: white;
    }}

    #albumArt {{
        border-radius: 12px;
        background-color: #282828;
        margin-right: 20px;
    }}
    #mainTitle {{
        color: white; font-family: 'Inter', sans-serif; font-size: 42px; font-weight: bold;
    }}
    #mainArtist {{
        color: #B3B3B3; font-family: 'Inter', sans-serif; font-size: 18px; margin-top: 5px;
    }}
    #lyricsWidget {{ 
        font-size: 18px; text-align: center; border: none;
    }}
    #lyricsWidget::item {{ color: #666; padding: 6px; }}
    #lyricsWidget::item:selected, #lyricsWidget::item.current {{ 
        color: white; font-weight: bold; background-color: transparent; border: none;
    }}
    
    QLabel {{ color: #B3B3B3; font-family: 'Inter', sans-serif; }}
    QPushButton {{ 
        background-color: transparent; border: none; color: #B3B3B3;
        padding: 8px; border-radius: 16px;
    }}
    QPushButton:hover {{ background-color: #282828; }}
    #playPauseButton {{
        background-color: white; color: black;
        min-width: 50px; max-width: 50px;
        min-height: 50px; max-height: 50px;
        border-radius: 15px;
        padding: 0px;
    }}
    #playPauseButton:hover {{ background-color: #F0F0F0; }}
    
    QSlider::groove:horizontal {{
        height: 4px; background: #535353; border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        background: white; width: 12px; height: 12px;
        margin: -4px 0; border-radius: 6px;
    }}
    QSlider::sub-page:horizontal {{
        background: {ACCENT_COLOR}; border-radius: 2px;
    }}

    /* Scrollbar Styling */
    QScrollBar:vertical {{
        border: none; background: #040404; width: 10px; margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: #282828; min-height: 20px; border-radius: 5px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}

    #lyricsWidget::item:focus, #lyricsWidget::item:selected:focus {{
        outline: none;
        border: none;
    }}
    #lyricsWidget::item {{
        outline: none;
        border: none;
    }}
    QListWidget::item:selected {{
        background: transparent;
        outline: none;
    }}
""" 