from typing import TYPE_CHECKING, Tuple, Optional
import numpy as np

# OpenCV import with error handling
try:
    import cv2
except ImportError as e:
    print(f"OpenCV import error: {e}")
    cv2 = None

# PySide6 imports with error handling
try:
    from PySide6.QtCore import QObject, Signal, QTimer, QRect, Qt
    from PySide6.QtGui import QPixmap, QPainter, QColor, QImage
    from PySide6.QtWidgets import QApplication, QWidget, QRubberBand, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSpinBox
except ImportError as e:
    print(f"PySide6 import error: {e}")
    # Fallback imports
    try:
        from PySide6.QtCore import *
        from PySide6.QtGui import *
        from PySide6.QtWidgets import *
    except ImportError:
        print("Failed to import PySide6 components")

import mss

if TYPE_CHECKING:
    from app.ui.main_ui import MainWindow


class PreviewWindow(QWidget):
    """Simple preview window for displaying captured screen regions."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Screen Capture Preview")
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        
        layout = QVBoxLayout()
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("border: 1px solid gray;")
        layout.addWidget(self.image_label)
        
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)
        layout.addWidget(close_button)
        
        self.setLayout(layout)
        
    def show_image(self, image: np.ndarray):
        """Display the captured image in the preview window."""
        # Convert numpy array to QPixmap
        h, w, ch = image.shape
        bytes_per_line = ch * w
        qt_image = QImage(image.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_image)
        
        # Scale to fit window while maintaining aspect ratio
        scaled_pixmap = pixmap.scaled(800, 600, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image_label.setPixmap(scaled_pixmap)
        self.resize(scaled_pixmap.size())


class ScreenRegionSelector(QWidget):
    """Widget for selecting a screen region using a rubber band selector."""
    
    region_selected = Signal(int, int, int, int)  # x, y, width, height
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Screen Region for Capture")
        self.setFixedSize(400, 200)
        
        # Region coordinates
        self.region_x = 0
        self.region_y = 0
        self.region_width = 640
        self.region_height = 480
        
        # Initialize preview window and selector overlay
        self.preview_window = None
        self.selector_overlay = None
        
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Instructions
        instructions = QLabel("Click 'Select Region' to choose a screen area to capture")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        
        # Current region display
        self.region_label = QLabel(f"Current Region: {self.region_x}, {self.region_y}, {self.region_width}x{self.region_height}")
        layout.addWidget(self.region_label)
        
        # Manual input controls
        manual_layout = QHBoxLayout()
        manual_layout.addWidget(QLabel("X:"))
        self.x_spin = QSpinBox()
        self.x_spin.setRange(0, 9999)
        self.x_spin.setValue(self.region_x)
        self.x_spin.valueChanged.connect(self.on_manual_change)
        manual_layout.addWidget(self.x_spin)
        
        manual_layout.addWidget(QLabel("Y:"))
        self.y_spin = QSpinBox()
        self.y_spin.setRange(0, 9999)
        self.y_spin.setValue(self.region_y)
        self.y_spin.valueChanged.connect(self.on_manual_change)
        manual_layout.addWidget(self.y_spin)
        
        manual_layout.addWidget(QLabel("Width:"))
        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 9999)
        self.width_spin.setValue(self.region_width)
        self.width_spin.valueChanged.connect(self.on_manual_change)
        manual_layout.addWidget(self.width_spin)
        
        manual_layout.addWidget(QLabel("Height:"))
        self.height_spin = QSpinBox()
        self.height_spin.setRange(1, 9999)
        self.height_spin.setValue(self.region_height)
        self.height_spin.valueChanged.connect(self.on_manual_change)
        manual_layout.addWidget(self.height_spin)
        
        layout.addLayout(manual_layout)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.select_button = QPushButton("Select Region")
        self.select_button.clicked.connect(self.start_region_selection)
        button_layout.addWidget(self.select_button)
        
        self.preview_button = QPushButton("Preview")
        self.preview_button.clicked.connect(self.preview_region)
        button_layout.addWidget(self.preview_button)
        
        self.apply_button = QPushButton("Apply")
        self.apply_button.clicked.connect(self.apply_region)
        button_layout.addWidget(self.apply_button)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
        
    def on_manual_change(self):
        self.region_x = self.x_spin.value()
        self.region_y = self.y_spin.value()
        self.region_width = self.width_spin.value()
        self.region_height = self.height_spin.value()
        self.update_region_label()
        
    def update_region_label(self):
        self.region_label.setText(f"Current Region: {self.region_x}, {self.region_y}, {self.region_width}x{self.region_height}")

    def start_region_selection(self):
        """Start the rubber band selection process."""
        self.hide()  # Hide this dialog
        if self.selector_overlay is None:
            self.selector_overlay = ScreenSelectorOverlay()
            self.selector_overlay.region_selected.connect(self.on_region_selected)
        self.selector_overlay.show()
        
    def on_region_selected(self, x, y, width, height):
        """Called when a region is selected via rubber band."""
        self.region_x = x
        self.region_y = y
        self.region_width = width
        self.region_height = height
        
        # Update spinboxes
        self.x_spin.setValue(x)
        self.y_spin.setValue(y)
        self.width_spin.setValue(width)
        self.height_spin.setValue(height)
        
        self.update_region_label()
        self.show()  # Show this dialog again
        
    def preview_region(self):
        """Preview the selected region by taking a screenshot."""
        try:
            with mss.mss() as sct:
                monitor = {
                    "top": self.region_y,
                    "left": self.region_x,
                    "width": self.region_width,
                    "height": self.region_height
                }
                screenshot = sct.grab(monitor)
                img = np.array(screenshot)
                if cv2 is not None:
                    img = getattr(cv2, 'cvtColor')(img, getattr(cv2, 'COLOR_BGRA2RGB'))
                else:
                    # Fallback: manual color conversion
                    img = img[:, :, [2, 1, 0]]  # BGRA to RGB
                
                # Show preview using Qt-based window instead of cv2.imshow
                if self.preview_window is None:
                    self.preview_window = PreviewWindow(self)
                
                self.preview_window.show_image(img)
                self.preview_window.show()
                self.preview_window.raise_()
                self.preview_window.activateWindow()
                
        except Exception as e:
            print(f"Preview error: {e}")
            
    def apply_region(self):
        """Apply the selected region and emit signal."""
        self.region_selected.emit(self.region_x, self.region_y, self.region_width, self.region_height)
        self.close()


class ScreenSelectorOverlay(QWidget):
    """Fullscreen overlay for selecting screen regions."""
    region_selected = Signal(int, int, int, int)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(self.windowFlags() | 
                            Qt.WindowStaysOnTopHint | 
                            Qt.FramelessWindowHint)
        
        # Make window transparent
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Full screen
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)
        self.rubber_band = QRubberBand(QRubberBand.Shape.Rectangle, self)
        self.origin = None
        
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.origin = event.position().toPoint()
            self.rubber_band.setGeometry(QRect(self.origin, self.origin))
            self.rubber_band.show()
            
    def mouseMoveEvent(self, event):
        if self.origin is not None:
            self.rubber_band.setGeometry(QRect(self.origin, event.position().toPoint()).normalized())
            
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.origin is not None:            rect = self.rubber_band.geometry()
            self.region_selected.emit(rect.x(), rect.y(), rect.width(), rect.height())
            self.close()
            
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
            
    def paintEvent(self, event):
        _ = event  # Unused parameter
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 100))  # Semi-transparent overlay


class ScreenCapture:
    """Screen capture functionality using MSS (Multiple Screen Shots)."""
    
    def __init__(self):
        self.region = None
        self.sct = None
        self.monitor = None
        
    def set_region(self, x: int, y: int, width: int, height: int):
        """Set the capture region."""
        self.region = (x, y, width, height)
        self.monitor = {
            "top": y,
            "left": x,
            "width": width,
            "height": height
        }
        
    def start_capture(self):
        """Initialize the screen capture."""
        if self.sct is None:
            self.sct = mss.mss()
            
    def stop_capture(self):
        """Stop screen capture and cleanup."""
        if self.sct is not None:
            self.sct.close()
            self.sct = None
            
    def capture_frame(self) -> Optional[np.ndarray]:
        """Capture a single frame from the screen region."""
        if self.sct is None or self.monitor is None:
            return None
            
        try:
            screenshot = self.sct.grab(self.monitor)
            img = np.array(screenshot)
            # Convert BGRA to RGB
            if cv2 is not None:
                img = getattr(cv2, 'cvtColor')(img, getattr(cv2, 'COLOR_BGRA2RGB'))
            else:
                # Fallback: manual color conversion
                img = img[:, :, [2, 1, 0]]  # BGRA to RGB
            return img
        except Exception as e:
            print(f"Screen capture error: {e}")
            return None


class ScreenCaptureProcessor(QObject):
    """Processor that integrates screen capture with VisoMaster's video processing pipeline."""
    
    frame_captured = Signal(np.ndarray)
    
    def __init__(self, main_window: 'MainWindow'):
        super().__init__()
        self.main_window = main_window
        self.screen_capture = ScreenCapture()
        self.capture_timer = QTimer()
        self.capture_timer.timeout.connect(self.capture_frame)
        self.is_capturing = False
        self.region_selector = None
        
    def show_region_selector(self):
        """Show the region selector dialog."""
        if self.region_selector is None:
            self.region_selector = ScreenRegionSelector()
            self.region_selector.region_selected.connect(self.on_region_selected)
        self.region_selector.show()
    def on_region_selected(self, x: int, y: int, width: int, height: int):
        """Handle region selection."""
        print(f"Screen region selected: {x}, {y}, {width}x{height}")
        self.screen_capture.set_region(x, y, width, height)
        
        # Create a virtual "screen capture" media item
        self.create_screen_capture_media_item(x, y, width, height)
        
    def create_screen_capture_media_item(self, x: int, y: int, width: int, height: int):
        """Create a media item for screen capture that integrates with the existing system."""
        import uuid
        from PySide6 import QtGui
        from app.ui.widgets.actions import list_view_actions
        from app.ui.widgets.actions import common_actions as common_widget_actions
        
        # Generate unique media ID for this screen capture
        media_id = str(uuid.uuid1().int)
        media_path = f'Screen Capture {x},{y} {width}x{height}'
        file_type = 'screen_capture'
        
        # Update screen capture settings in control
        settings = self.main_window.control
        settings['ScreenCaptureXSlider'] = x
        settings['ScreenCaptureYSlider'] = y
        settings['ScreenCaptureWidthSlider'] = width
        settings['ScreenCaptureHeightSlider'] = height
        
        # Capture a frame for the thumbnail
        try:
            screen_capture = ScreenCapture()
            screen_capture.set_region(x, y, width, height)
            screen_capture.start_capture()
            frame = screen_capture.capture_frame()
            screen_capture.stop_capture()
            
            if frame is not None:
                # Convert frame to pixmap for thumbnail
                pixmap = common_widget_actions.get_pixmap_from_frame(self.main_window, frame)
                
                # Add to target videos list
                list_view_actions.add_screen_capture_thumbnail_to_target_videos_list(
                    self.main_window, media_path, pixmap, file_type, media_id
                )
                
                print(f"Added screen capture region to target media list: {media_path}")
            else:
                print("Failed to capture screen region for thumbnail")
        except Exception as e:
            print(f"Error creating screen capture media item: {e}")
        
        print(f"Screen capture source configured: {width}x{height} at {x},{y}")
        
    def start_capture(self):
        """Start screen capture."""
        if not self.is_capturing and self.screen_capture.region is not None:
            self.screen_capture.start_capture()
            self.capture_timer.start(33)  # ~30 FPS
            self.is_capturing = True
            
            # OPTIMIZATION: Automatically enable performance mode for screen capture
            if hasattr(self.main_window, 'video_processor'):
                self.main_window.video_processor.enable_screen_capture_performance_mode()

            print("Screen capture started with performance mode enabled")

    def stop_capture(self):
        """Stop screen capture."""
        if self.is_capturing:
            self.capture_timer.stop()
            self.screen_capture.stop_capture()
            self.is_capturing = False

            # OPTIMIZATION: Disable performance mode when stopping screen capture
            if hasattr(self.main_window, 'video_processor'):
                self.main_window.video_processor.disable_screen_capture_performance_mode()

            print("Screen capture stopped, performance mode disabled")

    def capture_frame(self):
        """Capture and emit a frame."""
        frame = self.screen_capture.capture_frame()
        if frame is not None:
            self.frame_captured.emit(frame)

class ScreenCaptureWrapper:
    """Wrapper class to make screen capture compatible with cv2.VideoCapture interface."""

    def __init__(self, screen_capture: ScreenCapture):
        self.screen_capture = screen_capture
        self._is_opened = True

    def isOpened(self) -> bool:
        return self._is_opened

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Read a frame from screen capture."""
        frame = self.screen_capture.capture_frame()
        if frame is not None:
            # Convert RGB to BGR for compatibility with OpenCV
            if cv2 is not None:
                frame = getattr(cv2, 'cvtColor')(frame, getattr(cv2, 'COLOR_RGB2BGR'))
            else:
                # Fallback: manual color conversion
                frame = frame[:, :, [2, 1, 0]]  # RGB to BGR
            return True, frame
        return False, None

    def get(self, prop_id: int):
        """Get property values."""
        if prop_id == getattr(cv2, 'CAP_PROP_FPS', 0):
            return 30.0
        elif prop_id == getattr(cv2, 'CAP_PROP_FRAME_WIDTH', 0):
            return self.screen_capture.region[2] if self.screen_capture.region else 640
        elif prop_id == getattr(cv2, 'CAP_PROP_FRAME_HEIGHT', 0):
            return self.screen_capture.region[3] if self.screen_capture.region else 480
        elif prop_id == getattr(cv2, 'CAP_PROP_FRAME_COUNT', 0):
            return 999999  # Infinite frames for live capture
        return 0

    def set(self, prop_id: int, value):
        """Set property values (no-op for screen capture)."""
        pass

    def release(self):
        """Release resources."""
        self.screen_capture.stop_capture()
        self._is_opened = False