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
        from PySide6.QtCore import *  # pylint: disable=wildcard-import,unused-wildcard-import
        from PySide6.QtGui import *  # pylint: disable=wildcard-import,unused-wildcard-import
        from PySide6.QtWidgets import *  # pylint: disable=wildcard-import,unused-wildcard-import
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
        try:
            print(f"DEBUG: PreviewWindow.show_image - input shape: {image.shape}, dtype: {image.dtype}")
            
            # Handle different image formats properly
            h, w = image.shape[:2]
            ch = image.shape[2] if len(image.shape) == 3 else 1
            
            print(f"DEBUG: Image dimensions - h={h}, w={w}, ch={ch}")
            
            # Convert image based on channel count and format
            if ch == 4:  # BGRA format (typical for MSS screenshots)
                # Method 1: Convert BGRA to RGB manually for better control
                rgb_image = image[:, :, [2, 1, 0]]  # BGR to RGB, drop alpha channel
                
                # Ensure the array is contiguous in memory
                if not rgb_image.flags['C_CONTIGUOUS']:
                    rgb_image = np.ascontiguousarray(rgb_image)
                
                h, w, ch = rgb_image.shape
                bytes_per_line = ch * w
                qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
                
            elif ch == 3:  # BGR or RGB format
                # Assume it's BGR and convert to RGB
                if cv2 is not None:
                    # Use OpenCV if available
                    rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                else:
                    # Manual conversion
                    rgb_image = image[:, :, [2, 1, 0]]  # BGR to RGB
                
                # Ensure the array is contiguous in memory
                if not rgb_image.flags['C_CONTIGUOUS']:
                    rgb_image = np.ascontiguousarray(rgb_image)
                
                h, w, ch = rgb_image.shape
                bytes_per_line = ch * w
                qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
                
            else:
                raise ValueError(f"Unsupported image format: {ch} channels")
            
            # Convert to QPixmap
            pixmap = QPixmap.fromImage(qt_image)
            
            if pixmap.isNull():
                raise ValueError("Failed to create QPixmap from QImage")
            
            print(f"DEBUG: Created pixmap size: {pixmap.width()}x{pixmap.height()}")
            
            # Scale to fit window while maintaining aspect ratio
            max_width, max_height = 800, 600
            scaled_pixmap = pixmap.scaled(max_width, max_height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            
            print(f"DEBUG: Scaled pixmap size: {scaled_pixmap.width()}x{scaled_pixmap.height()}")
            
            # Set the pixmap to the label
            self.image_label.setPixmap(scaled_pixmap)
            
            # Resize window to fit the scaled image (with some padding)
            window_width = min(scaled_pixmap.width() + 40, max_width + 40)
            window_height = min(scaled_pixmap.height() + 80, max_height + 80)  # Extra space for button
            self.resize(window_width, window_height)
            
            print("DEBUG: Preview image displayed successfully")
            
        except Exception as e:
            print(f"ERROR: Failed to display preview image: {e}")
            import traceback
            traceback.print_exc()
            
            # Show error message in the label
            self.image_label.setText(f"Error displaying image:\n{str(e)}")
            self.image_label.setStyleSheet("border: 1px solid red; color: red; padding: 10px;")
            self.resize(400, 200)


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
        
        # Monitor information
        self.add_monitor_info(layout)
        
        # Manual input controls
        manual_layout = QHBoxLayout()
        manual_layout.addWidget(QLabel("X:"))
        self.x_spin = QSpinBox()
        # MULTI-MONITOR FIX: Allow negative coordinates for secondary monitors
        self.x_spin.setRange(-9999, 9999)
        self.x_spin.setValue(self.region_x)
        self.x_spin.valueChanged.connect(self.on_manual_change)
        manual_layout.addWidget(self.x_spin)
        
        manual_layout.addWidget(QLabel("Y:"))
        self.y_spin = QSpinBox()
        # MULTI-MONITOR FIX: Allow negative coordinates for secondary monitors
        self.y_spin.setRange(-9999, 9999)
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
        
        select_button = QPushButton("Select Region")
        select_button.clicked.connect(self.start_region_selection)
        button_layout.addWidget(select_button)
        
        self.preview_button = QPushButton("Preview")
        self.preview_button.clicked.connect(self.preview_region)
        button_layout.addWidget(self.preview_button)
        self.apply_button = QPushButton("Apply")
        self.apply_button.clicked.connect(self.apply_region)
        button_layout.addWidget(self.apply_button)
        
        # MULTI-MONITOR: Add button to show monitor info
        self.monitor_info_button = QPushButton("Show Monitors")
        self.monitor_info_button.clicked.connect(self.show_monitor_info)
        button_layout.addWidget(self.monitor_info_button)
        
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
        """Preview the selected region."""
        try:
            print(f"DEBUG: Starting preview of region: {self.region_x}, {self.region_y}, {self.region_width}x{self.region_height}")
            
            # Validate region bounds
            if self.region_width <= 0 or self.region_height <= 0:
                raise ValueError(f"Invalid region size: {self.region_width}x{self.region_height}")
            
            # Capture the selected region
            with mss.mss() as sct:
                monitor = {
                    "top": self.region_y,
                    "left": self.region_x,
                    "width": self.region_width,
                    "height": self.region_height
                }
                
                print(f"DEBUG: MSS monitor config: {monitor}")
                
                screenshot = sct.grab(monitor)
                print(f"DEBUG: Screenshot captured - size: {screenshot.size}, pixel format: {screenshot.pixel}")
                
                # Convert to numpy array
                img = np.array(screenshot)
                print(f"DEBUG: Numpy array created - shape: {img.shape}, dtype: {img.dtype}")
                
                # Optional: Apply OpenCV color conversion if available
                if cv2 is not None:
                    print("DEBUG: Applying OpenCV color conversion BGRA->RGB")
                    img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGB)
                    print(f"DEBUG: After OpenCV conversion - shape: {img.shape}")
                else:
                    print("DEBUG: OpenCV not available, will handle conversion in PreviewWindow")
                
                # Show preview window
                if self.preview_window is None:
                    print("DEBUG: Creating new PreviewWindow")
                    self.preview_window = PreviewWindow()
                else:
                    print("DEBUG: Reusing existing PreviewWindow")
                
                print("DEBUG: Calling show_image on PreviewWindow")
                self.preview_window.show_image(img)
                self.preview_window.show()
                self.preview_window.raise_()  # Bring to front
                self.preview_window.activateWindow()  # Activate window
                
                print("DEBUG: Preview region completed successfully")
                
        except Exception as e:  # pylint: disable=broad-except
            print(f"ERROR: Error previewing region: {e}")
            import traceback
            traceback.print_exc()
            
            # Show error in a message box
            try:
                from PySide6.QtWidgets import QMessageBox
                msg_box = QMessageBox(self)
                msg_box.setWindowTitle("Preview Error")
                msg_box.setText(f"Failed to preview screen region:\n\n{str(e)}")
                msg_box.setIcon(QMessageBox.Warning)
                msg_box.exec()
            except Exception as msg_e:
                print(f"ERROR: Failed to show error message box: {msg_e}")
            
    def apply_region(self):
        """Apply the selected region and emit the signal."""
        self.region_selected.emit(self.region_x, self.region_y, self.region_width, self.region_height)
        self.close()
    
    def add_monitor_info(self, layout):
        """Add monitor information display to the layout."""
        try:
            app = QApplication.instance()
            if app is None:
                return
                
            screens = app.screens()
            if not screens:
                return
                
            # Create a collapsible monitor info section
            info_label = QLabel("Monitor Information:")
            info_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
            layout.addWidget(info_label)
            
            info_text = ""
            for i, screen in enumerate(screens):
                geom = screen.geometry()
                is_primary = screen == app.primaryScreen()
                primary_text = " (PRIMARY)" if is_primary else ""
                info_text += f"Monitor {i + 1}{primary_text}: {geom.x()},{geom.y()} {geom.width()}x{geom.height()}\n"
              # Also add MSS monitor info for reference
            try:
                with mss.mss() as sct:
                    monitors = sct.monitors
                    info_text += f"\nMSS detected {len(monitors)-1} monitors"
            except Exception as e:
                info_text += f"\nMSS error: {str(e)}"
            
            monitor_info_label = QLabel(info_text.strip())
            monitor_info_label.setStyleSheet("font-family: monospace; font-size: 10px; color: #666; margin-bottom: 10px;")
            monitor_info_label.setWordWrap(True)
            layout.addWidget(monitor_info_label)
            
        except Exception:
            # Silently ignore errors in monitor info display
            pass
    
    def show_monitor_info(self):
        """Show information about all available monitors."""
        try:
            app = QApplication.instance()
            if app is None:
                print("No QApplication instance available")
                return
                
            screens = app.screens()
            if not screens:
                print("No screens detected")
                return
                
            info_text = "Multi-Monitor Setup:\n\n"
            for i, screen in enumerate(screens):
                geom = screen.geometry()
                is_primary = screen == app.primaryScreen()
                primary_text = " (PRIMARY)" if is_primary else ""
                info_text += f"Monitor {i + 1}{primary_text}:\n"
                info_text += f"  Position: {geom.x()}, {geom.y()}\n"
                info_text += f"  Size: {geom.width()} x {geom.height()}\n"
                info_text += f"  Name: {screen.name()}\n\n"
                # Also show MSS monitor info
            try:
                with mss.mss() as sct:
                    monitors = sct.monitors
                    info_text += "MSS Monitor Info:\n"
                    for i, monitor in enumerate(monitors):
                        if i == 0:
                            info_text += f"All Monitors Combined: {monitor}\n"
                        else:
                            info_text += f"Monitor {i}: {monitor}\n"
            except Exception as e:
                info_text += f"MSS info unavailable: {e}\n"
                
            # Show in a message box
            from PySide6.QtWidgets import QMessageBox
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Monitor Information")
            msg_box.setText(info_text)
            msg_box.exec()
            
        except Exception as e:
            print(f"Error showing monitor info: {e}")
            import traceback
            traceback.print_exc()


class ScreenSelectorOverlay(QWidget):
    """Fullscreen overlay for selecting screen regions with multi-monitor support."""
    region_selected = Signal(int, int, int, int)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(self.windowFlags() | 
                            Qt.WindowStaysOnTopHint | 
                            Qt.FramelessWindowHint)
        
        # Make window transparent
        self.setAttribute(Qt.WA_TranslucentBackground)
        # MULTI-MONITOR FIX: Cover all screens, not just primary
        self.setup_multi_monitor_geometry()
        
        self.rubber_band = QRubberBand(QRubberBand.Shape.Rectangle, self)
        self.origin = None

    def setup_multi_monitor_geometry(self):
        """Set up geometry to cover all monitors using MSS for accurate coordinates."""
        try:
            # Use MSS to get accurate monitor information
            with mss.mss() as sct:
                monitors = sct.monitors
                # Monitor 0 is the combined area of all monitors
                combined = monitors[0]
                
                print("DEBUG: MSS Multi-monitor setup:")
                print(f"  Combined area: {combined}")
                for i, monitor in enumerate(monitors[1:], 1):  # Skip monitor 0 (combined)
                    print(f"  Monitor {i}: {monitor}")
                
                # Set geometry to cover the combined area
                self.setGeometry(combined['left'], combined['top'], combined['width'], combined['height'])
                print(f"DEBUG: Overlay geometry set to: {combined['left']}, {combined['top']}, {combined['width']}x{combined['height']}")
                
                # Store monitor info for coordinate translation
                self.monitors = monitors
                
        except Exception as e:
            print(f"ERROR: Failed to setup MSS multi-monitor geometry: {e}")
            # Fallback to Qt method
            self.setup_qt_fallback_geometry()
    
    def setup_qt_fallback_geometry(self):
        """Fallback method using Qt screen detection."""
        app = QApplication.instance()
        if app is None:
            # Fallback to primary screen if no app instance
            screen = QApplication.primaryScreen().geometry()
            self.setGeometry(screen)
            print(f"DEBUG: Using primary screen only: {screen}")
            return
            
        # Get all screens and calculate total desktop geometry
        screens = app.screens()
        if not screens:
            # Fallback if no screens detected
            screen = QApplication.primaryScreen().geometry()
            self.setGeometry(screen)
            return
            
        # Calculate bounding rectangle of all screens
        min_x = min(screen.geometry().x() for screen in screens)
        min_y = min(screen.geometry().y() for screen in screens)
        max_x = max(screen.geometry().x() + screen.geometry().width() for screen in screens)
        max_y = max(screen.geometry().y() + screen.geometry().height() for screen in screens)
        
        total_width = max_x - min_x
        total_height = max_y - min_y
        
        print("DEBUG: Qt Multi-monitor setup detected:")
        for i, screen in enumerate(screens):
            geom = screen.geometry()
            print(f"  Screen {i}: {geom.x()}, {geom.y()}, {geom.width()}x{geom.height()}")
        
        print(f"DEBUG: Total desktop: {min_x}, {min_y}, {total_width}x{total_height}")
        
        # Set geometry to cover all screens
        self.setGeometry(min_x, min_y, total_width, total_height)
        
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.origin = event.position().toPoint()
            self.rubber_band.setGeometry(QRect(self.origin, self.origin))
            self.rubber_band.show()
            
    def mouseMoveEvent(self, event):
        if self.origin is not None:
            self.rubber_band.setGeometry(QRect(self.origin, event.position().toPoint()).normalized())
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.origin is not None:
            rect = self.rubber_band.geometry()
            
            # Convert coordinates to absolute screen coordinates using MSS coordinates
            # We stored MSS monitor info in setup_multi_monitor_geometry()
            if hasattr(self, 'monitors') and self.monitors:
                # Use MSS combined area (monitors[0]) for coordinate translation
                combined = self.monitors[0]
                absolute_x = rect.x() + combined['left']
                absolute_y = rect.y() + combined['top']
                
                print(f"DEBUG: Selected region - Widget coords: {rect.x()}, {rect.y()}, {rect.width()}x{rect.height()}")
                print(f"DEBUG: Selected region - MSS coords: {absolute_x}, {absolute_y}, {rect.width()}x{rect.height()}")
                print(f"DEBUG: MSS combined area offset: {combined['left']}, {combined['top']}")
                
            else:
                # Fallback to Qt geometry if MSS info not available
                absolute_x = rect.x() + self.geometry().x()
                absolute_y = rect.y() + self.geometry().y()
                
                print(f"DEBUG: Selected region - Widget coords: {rect.x()}, {rect.y()}, {rect.width()}x{rect.height()}")
                print(f"DEBUG: Selected region - Qt fallback coords: {absolute_x}, {absolute_y}, {rect.width()}x{rect.height()}")
            
            self.region_selected.emit(absolute_x, absolute_y, rect.width(), rect.height())
            self.close()
            
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
            
    def paintEvent(self, event):
        _ = event  # Unused parameter
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 100))  # Semi-transparent overlay    def showEvent(self, event):
        """Override showEvent to apply Windows-specific screen capture exclusion."""
        print("DEBUG: VideoOverlayWindow.showEvent called - making window visible")
        super().showEvent(event)
        
        # Force the window to be visible and on top
        self.raise_()
        self.activateWindow()
        self.setFocus()
        
        # Apply screen capture exclusion so it's invisible to capture
        self.exclude_from_screen_capture()
        
        print("DEBUG: VideoOverlayWindow should now be visible but excluded from capture")
    
    def exclude_from_screen_capture(self):
        """Apply Windows-specific attributes to exclude this window from screen capture."""
        try:
            import ctypes
            from ctypes import wintypes
            import platform
            
            if platform.system() != "Windows":
                print("DEBUG: Not on Windows, skipping screen capture exclusion")
                return
                
            # Get the window handle
            hwnd = int(self.winId())
            
            if hwnd == 0:
                print("DEBUG: No valid window handle, skipping exclusion")
                return
                
            # Windows API constants
            WDA_EXCLUDEFROMCAPTURE = 11
            
            # Get the SetWindowDisplayAffinity function
            user32 = ctypes.windll.user32
            
            # Try to exclude this window from screen capture
            # SetWindowDisplayAffinity with WDA_EXCLUDEFROMCAPTURE
            result = user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
            
            if result:
                print("DEBUG: ✅ Successfully excluded overlay window from screen capture")
            else:
                print("DEBUG: ⚠️ SetWindowDisplayAffinity failed, trying fallback...")
                # Fallback: try WS_EX_NOREDIRECTIONBITMAP extended style
                GWL_EXSTYLE = -20
                WS_EX_NOREDIRECTIONBITMAP = 0x00200000
                
                # Get current extended style
                ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                # Add the no-redirection flag
                new_ex_style = ex_style | WS_EX_NOREDIRECTIONBITMAP
                # Set the new extended style
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_ex_style)
                print("DEBUG: ✅ Applied WS_EX_NOREDIRECTIONBITMAP fallback")
                
        except Exception as e:
            print(f"DEBUG: Could not apply screen capture exclusion: {e}")
            # This is not critical, so we continue silently
    
    def ensure_proper_state(self):
        """Ensure the overlay window is in the proper state - always excluded from screen capture."""
        print("DEBUG: Ensuring overlay window proper state...")
        
        # Force update position
        self.update_position()
        
        # Don't modify window flags if already visible, as this can cause issues
        # Just ensure exclusion is applied
        self.exclude_from_screen_capture()
        
        print("DEBUG: Overlay window state reset complete")


class ScreenCapture:
    """Screen capture functionality using MSS (Multiple Screen Shots)."""
    
    def __init__(self):
        self.region = None
        self.sct = None
        self.monitor = None
        
    def set_region(self, x: int, y: int, width: int, height: int):
        """Set the screen region to capture."""
        self.region = {
            "top": y,
            "left": x,
            "width": width,
            "height": height
        }
        self.monitor = self.region
        
    def start_capture(self):
        """Initialize MSS for capturing."""
        if self.sct is None:
            self.sct = mss.mss()
            
    def capture_frame(self) -> Optional[np.ndarray]:
        """Capture a single frame from the specified region."""
        if self.sct is None or self.monitor is None:
            return None
            
        try:
            # Grab screenshot
            screenshot = self.sct.grab(self.monitor)
            # Convert to numpy array (BGRA -> RGB)
            img = np.array(screenshot)
            if cv2 is not None:
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGB)
            
            return img
        except Exception as e:  # pylint: disable=broad-except
            print(f"Error capturing frame: {e}")
            return None
            
    def stop_capture(self):
        """Clean up MSS resources."""
        if self.sct:
            self.sct.close()
            self.sct = None


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
        self.region_selector = None        # Store current region for overlay positioning
        self.current_region = None
        
    def show_region_selector(self):
        """Show the region selector dialog."""
        try:
            print("DEBUG: ScreenCaptureProcessor.show_region_selector() called")
            if self.region_selector is None:
                print("DEBUG: Creating new ScreenRegionSelector")
                self.region_selector = ScreenRegionSelector()
                self.region_selector.region_selected.connect(self.on_region_selected)
                print("DEBUG: ScreenRegionSelector created and connected")
            else:
                print("DEBUG: Using existing ScreenRegionSelector")
            
            print("DEBUG: Calling region_selector.show()")
            self.region_selector.show()
            print("DEBUG: region_selector.show() completed")
        except Exception as e:
            print(f"ERROR in show_region_selector: {e}")
            import traceback
            traceback.print_exc()
        
    def on_region_selected(self, x: int, y: int, width: int, height: int):
        """Handle region selection."""
        print(f"Screen region selected: {x}, {y}, {width}x{height}")
        
        # Store the current region for overlay positioning
        self.current_region = {'x': x, 'y': y, 'width': width, 'height': height}
        
        self.screen_capture.set_region(x, y, width, height)
        
        # CRITICAL FIX: Update screen capture settings in main window control
        print("DEBUG: Updating screen capture settings...")
        settings = self.main_window.control
        settings['ScreenCaptureXSlider'] = x
        settings['ScreenCaptureYSlider'] = y
        settings['ScreenCaptureWidthSlider'] = width
        settings['ScreenCaptureHeightSlider'] = height
        settings['ScreenCaptureEnableToggle'] = True  # Enable screen capture
        
        # Update the actual UI widgets if they exist
        self.update_screen_capture_ui_widgets(x, y, width, height)
        
        print(f"DEBUG: Settings updated - X:{x}, Y:{y}, W:{width}, H:{height}")
        
        # Enable the video overlay button when screen capture is configured
        if hasattr(self.main_window, 'buttonVideoOverlay'):
            self.main_window.buttonVideoOverlay.setEnabled(True)
            print("DEBUG: Video overlay button enabled")
          # Update existing screen capture if it's active, or create a new one
        self.update_or_create_screen_capture_media_item(x, y, width, height)
        
    def update_screen_capture_ui_widgets(self, x: int, y: int, width: int, height: int):
        """Update the screen capture UI slider widgets to reflect the selected region."""
        try:
            print("DEBUG: Updating screen capture UI widgets...")
            
            # Check if the main window has the parameter widgets
            if hasattr(self.main_window, 'parameters_widgets'):
                widgets = self.main_window.parameters_widgets
                
                # Update X position slider
                if 'ScreenCaptureXSlider' in widgets:
                    widgets['ScreenCaptureXSlider'].setValue(x)
                    print(f"DEBUG: Updated ScreenCaptureXSlider to {x}")
                
                # Update Y position slider
                if 'ScreenCaptureYSlider' in widgets:
                    widgets['ScreenCaptureYSlider'].setValue(y)
                    print(f"DEBUG: Updated ScreenCaptureYSlider to {y}")
                
                # Update Width slider
                if 'ScreenCaptureWidthSlider' in widgets:
                    widgets['ScreenCaptureWidthSlider'].setValue(width)
                    print(f"DEBUG: Updated ScreenCaptureWidthSlider to {width}")
                
                # Update Height slider
                if 'ScreenCaptureHeightSlider' in widgets:
                    widgets['ScreenCaptureHeightSlider'].setValue(height)
                    print(f"DEBUG: Updated ScreenCaptureHeightSlider to {height}")
                
                # Enable screen capture toggle
                if 'ScreenCaptureEnableToggle' in widgets:
                    widgets['ScreenCaptureEnableToggle'].setChecked(True)
                    print("DEBUG: Enabled ScreenCaptureEnableToggle")
                
                print("DEBUG: All screen capture UI widgets updated successfully")
            else:
                print("DEBUG: parameters_widgets not found in main_window")
                
        except Exception as e:
            print(f"WARNING: Failed to update screen capture UI widgets: {e}")
            import traceback
            traceback.print_exc()
        
    def create_screen_capture_media_item(self, x: int, y: int, width: int, height: int):
        """Create a media item for screen capture that integrates with the existing system."""
        import uuid
        from app.ui.widgets.actions import list_view_actions
        from app.ui.widgets.actions import common_actions as common_widget_actions
        # Generate unique media ID for this screen capture
        media_id = str(uuid.uuid1().int)
        media_path = f'Screen Capture {x},{y} {width}x{height}'
        file_type = 'screen_capture'
        
        # Settings are already updated in on_region_selected method
        # Just add the media item to the target videos list
        
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
        
    def update_or_create_screen_capture_media_item(self, x: int, y: int, width: int, height: int):
        """Update existing screen capture media item or create a new one."""
        try:
            # Check if there's an active screen capture media item in the video processor
            video_processor = getattr(self.main_window, 'video_processor', None)
            if video_processor and hasattr(video_processor, 'media_capture'):
                media_capture = video_processor.media_capture
                
                # Check if it's a ScreenCaptureWrapper instance
                if hasattr(media_capture, 'screen_capture') and hasattr(media_capture.screen_capture, 'set_region'):
                    print("DEBUG: Updating existing ScreenCaptureWrapper region...")
                    
                    # Update the region in the existing wrapper
                    media_capture.screen_capture.set_region(x, y, width, height)
                    
                    print(f"DEBUG: Existing screen capture updated to region: {x}, {y}, {width}, {height}")
                    return
            
            # If no existing screen capture or not a ScreenCaptureWrapper, create a new media item
            print("DEBUG: Creating new screen capture media item...")
            self.create_screen_capture_media_item(x, y, width, height)
            
        except Exception as e:
            print(f"ERROR: Failed to update/create screen capture media item: {e}")
            import traceback
            traceback.print_exc()
            
            # Fallback to creating a new item
            self.create_screen_capture_media_item(x, y, width, height)
    
    def capture_frame(self):
        """Capture and emit a frame from the screen capture."""
        try:
            if self.screen_capture and self.screen_capture.region:
                frame = self.screen_capture.capture_frame()
                if frame is not None:
                    self.frame_captured.emit(frame)
        except Exception as e:
            print(f"ERROR: Failed to capture frame: {e}")

class VideoOverlayWindow(QWidget):
    """Popout video window that displays processed video - like a separate video player."""
    
    def __init__(self, parent=None, region: dict = None):
        print("DEBUG: VideoOverlayWindow.__init__ called")
        super().__init__(None)  # No parent to avoid Qt issues
        self.region = region or {'x': 0, 'y': 0, 'width': 640, 'height': 480}
        print(f"DEBUG: VideoOverlayWindow region set to: {self.region}")
        
        # Use the simplest window setup that definitely works
        self.setWindowTitle("VisoMaster - Video Popout")
        
        # Use basic window flags - no fancy stuff
        self.setWindowFlags(Qt.Window)
        
        # Make it completely opaque and normal
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)        # Set size based on the captured region
        width = self.region['width']
        height = self.region['height']
        self.setFixedSize(width, height)
        print(f"DEBUG: VideoOverlayWindow size set to: {width}x{height}")
        
        # Position it at a safe, visible location (not overlapping the capture area)
        self.move(200, 200)
        
        print("DEBUG: VideoOverlayWindow basic setup complete")
        
        # Set up the UI
        self.setup_ui()
        
        # IMPORTANT: Apply screen capture exclusion immediately after creation
        # This ensures it's excluded from the very first appearance
        print("DEBUG: Applying immediate screen capture exclusion...")
        QApplication.processEvents()  # Process any pending events first
        self.exclude_from_screen_capture()
        
        print("DEBUG: VideoOverlayWindow initialization complete")
        self.update_position()
        
        # Variables for dragging (keeping for future enhancement)
        self.dragging = False
        self.drag_start_position = None
        self.move_mode = False
        
    def setup_ui(self):
        """Set up the overlay UI with simplified, highly visible design."""
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Video display label - make it highly visible and expandable
        self.video_label = QLabel("🎥 Video Overlay - Waiting for frames...")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setMinimumSize(300, 200)
        # Make the video label expand to fill available space
        try:
            from PySide6.QtWidgets import QSizePolicy
            self.video_label.setSizePolicy(
                QSizePolicy.Expanding, 
                QSizePolicy.Expanding
            )
        except ImportError:
            pass  # Fallback if import fails
            
        self.video_label.setStyleSheet("""
            QLabel {
                background-color: black;
                border: 3px solid #00ff00;
                border-radius: 5px;
                color: white;
                font-size: 16px;
                font-weight: bold;
                padding: 10px;
            }
        """)
        layout.addWidget(self.video_label)
        
        # Simplified control buttons
        controls_layout = QHBoxLayout()
        
        self.close_button = QPushButton("✖ Close")
        self.close_button.clicked.connect(self.close)
        self.close_button.setStyleSheet("""
            QPushButton {
                background-color: rgb(200, 50, 50);
                color: white;
                border: none;
                padding: 8px 15px;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: rgb(220, 70, 70);
            }
        """)
        controls_layout.addWidget(self.close_button)
        
        self.hide_button = QPushButton("⏸ Hide")
        self.hide_button.clicked.connect(self.hide)
        self.hide_button.setStyleSheet("""
            QPushButton {
                background-color: rgb(100, 100, 100);
                color: white;
                border: none;
                padding: 8px 15px;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: rgb(120, 120, 120);
            }
        """)
        controls_layout.addWidget(self.hide_button)        
        layout.addLayout(controls_layout)
        
        self.setLayout(layout)
        
    def update_position(self):
        """Update window position to match the capture region."""
        if self.region:
            print(f"DEBUG: Positioning overlay at {self.region['x']}, {self.region['y']}, {self.region['width']}x{self.region['height']}")
            
            # Ensure minimum size
            width = max(self.region['width'], 320)
            height = max(self.region['height'], 240)
            
            # Position the window
            self.setGeometry(
                self.region['x'],
                self.region['y'],
                width,
                height
            )
    
    def set_region(self, x: int, y: int, width: int, height: int):
        """Update the overlay region and resize window accordingly."""
        self.region = {'x': x, 'y': y, 'width': width, 'height': height}
        
        # Resize the window to match the new region size
        self.setFixedSize(width, height)
        print(f"DEBUG: Resized overlay window to {width}x{height}")
        
        self.update_position()
        print(f"DEBUG: Updated overlay region to {x}, {y}, {width}x{height}")
    
    def show_frame(self, frame: np.ndarray):
        """Display a processed video frame in the overlay."""
        try:
            if frame is None:
                return
                
            print(f"DEBUG: Overlay received frame: {frame.shape}")
            
            # Convert frame to QPixmap
            h, w = frame.shape[:2]
            ch = frame.shape[2] if len(frame.shape) == 3 else 1
            
            if ch == 3:  # BGR format
                if cv2 is not None:
                    # Convert BGR to RGB
                    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                else:
                    # Manual BGR to RGB conversion
                    rgb_frame = frame[:, :, [2, 1, 0]]
                    
                # Ensure contiguous array
                if not rgb_frame.flags['C_CONTIGUOUS']:
                    rgb_frame = np.ascontiguousarray(rgb_frame)
                
                # Create QImage
                qt_image = QImage(rgb_frame.data, w, h, ch * w, QImage.Format_RGB888)
                
                if qt_image.isNull():
                    print("WARNING: Failed to create QImage from frame")
                    return
                
                # Convert to QPixmap
                pixmap = QPixmap.fromImage(qt_image)
                
                if pixmap.isNull():
                    print("WARNING: Failed to create QPixmap from QImage")
                    return
                
                # Scale to fit the video label while maintaining aspect ratio
                label_size = self.video_label.size()
                scaled_pixmap = pixmap.scaled(
                    label_size,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                
                # Set the pixmap to the label
                self.video_label.setPixmap(scaled_pixmap)
                self.video_label.setText("")  # Clear any text
                # When video is showing, remove background styling to show the video clearly
                self.video_label.setStyleSheet("""
                    QLabel {
                        border: 2px solid #00ff00;
                        border-radius: 5px;
                        background-color: transparent;
                    }
                """)
                
                print(f"DEBUG: Overlay frame displayed: {w}x{h} -> {scaled_pixmap.width()}x{scaled_pixmap.height()}")
                
            else:
                print(f"WARNING: Unsupported frame format: {ch} channels")
        except Exception as e:
            print(f"ERROR: Failed to display overlay frame: {e}")
            import traceback
            traceback.print_exc()
    def showEvent(self, event):
        """Override showEvent to apply Windows-specific screen capture exclusion."""
        print("DEBUG: VideoOverlayWindow.showEvent called - window is becoming visible")
        super().showEvent(event)
        
        # Always update position when showing
        self.update_position()
        
        # Force the window to be visible and on top
        self.raise_()
        self.activateWindow()
        self.setFocus()
        
        # Apply exclusion immediately
        print("DEBUG: Applying screen capture exclusion on show...")
        self.exclude_from_screen_capture()
        
        # Apply exclusion again after short delays to ensure it takes effect
        from PySide6.QtCore import QTimer
        QTimer.singleShot(100, self.exclude_from_screen_capture)  # 100ms delay
        QTimer.singleShot(500, self.exclude_from_screen_capture)  # 500ms delay
        
        print("DEBUG: VideoOverlayWindow.showEvent completed")
    
    def exclude_from_screen_capture(self):
        """Apply Windows-specific attributes to exclude this window from screen capture."""
        try:
            import ctypes
            from ctypes import wintypes
            import platform
            
            if platform.system() != "Windows":
                print("DEBUG: Not on Windows, skipping screen capture exclusion")
                return
                
            # Get the window handle
            hwnd = int(self.winId())
            
            if hwnd == 0:
                print("DEBUG: No valid window handle, skipping exclusion")
                return
                
            # Windows API constants
            WDA_EXCLUDEFROMCAPTURE = 11
            
            # Get the SetWindowDisplayAffinity function
            user32 = ctypes.windll.user32
            
            # Try to exclude this window from screen capture
            # SetWindowDisplayAffinity with WDA_EXCLUDEFROMCAPTURE
            result = user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
            
            if result:
                print("DEBUG: ✅ Successfully excluded overlay window from screen capture")
            else:
                print("DEBUG: ⚠️ SetWindowDisplayAffinity failed, trying fallback...")
                # Fallback: try WS_EX_NOREDIRECTIONBITMAP extended style
                GWL_EXSTYLE = -20
                WS_EX_NOREDIRECTIONBITMAP = 0x00200000
                
                # Get current extended style
                ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                # Add the no-redirection flag
                new_ex_style = ex_style | WS_EX_NOREDIRECTIONBITMAP
                # Set the new extended style
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_ex_style)
                print("DEBUG: ✅ Applied WS_EX_NOREDIRECTIONBITMAP fallback")
                
        except Exception as e:
            print(f"DEBUG: Could not apply screen capture exclusion: {e}")
            # This is not critical, so we continue silently


class ScreenCaptureWrapper:
    """Wrapper class to make screen capture compatible with cv2.VideoCapture interface."""
    
    def __init__(self, x: int, y: int, width: int, height: int):
        self.screen_capture = ScreenCapture()
        self.screen_capture.set_region(x, y, width, height)
        self.is_opened = False
        
    def open(self) -> bool:
        """Open the screen capture."""
        try:
            self.screen_capture.start_capture()
            self.is_opened = True
            return True
        except Exception as e:
            print(f"Error opening screen capture: {e}")
            return False
            
    def isOpened(self) -> bool:
        """Check if screen capture is opened."""
        return self.is_opened
        
    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Read a frame from screen capture."""
        if not self.is_opened:
            return False, None
            
        frame = self.screen_capture.capture_frame()
        if frame is not None and cv2 is not None:
            # Convert RGB to BGR for OpenCV compatibility
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            return True, frame_bgr
        else:
            return False, None
            
    def get(self, prop_id: int):
        """Get video capture properties."""
        if cv2 is None:
            return 0
            
        if prop_id == cv2.CAP_PROP_FRAME_WIDTH:
            return self.screen_capture.region['width'] if self.screen_capture.region else 0
        elif prop_id == cv2.CAP_PROP_FRAME_HEIGHT:
            return self.screen_capture.region['height'] if self.screen_capture.region else 0
        elif prop_id == cv2.CAP_PROP_FPS:
            return 30.0  # Default FPS
        elif prop_id == cv2.CAP_PROP_FRAME_COUNT:
            return float('inf')  # Screen capture has unlimited frames
        elif prop_id == cv2.CAP_PROP_POS_FRAMES:
            return 0  # Current frame position (not applicable for screen capture)
        else:
            return 0
    
    def set(self, prop_id: int, value):
        """Set video capture properties."""
        if cv2 is None:
            return False
            
        # For screen capture, most properties are not settable
        # We'll ignore frame position changes as screen capture is always "live"
        if prop_id == cv2.CAP_PROP_POS_FRAMES:
            # Frame seeking is not applicable to screen capture
            return True
        elif prop_id == cv2.CAP_PROP_FRAME_WIDTH:
            # Would need to resize capture region, for now just ignore
            return False
        elif prop_id == cv2.CAP_PROP_FRAME_HEIGHT:
            # Would need to resize capture region, for now just ignore
            return False
        else:
            return False
    
    def set_region(self, x: int, y: int, width: int, height: int):
        """Update the capture region - this is the key method for updating coordinates."""
        print(f"DEBUG: ScreenCaptureWrapper.set_region called: {x}, {y}, {width}x{height}")
        if self.screen_capture:
            self.screen_capture.set_region(x, y, width, height)
            print(f"DEBUG: ScreenCaptureWrapper region updated successfully")
        
    def release(self):
        """Release the screen capture."""
        if self.is_opened:
            self.screen_capture.stop_capture()
            self.is_opened = False
