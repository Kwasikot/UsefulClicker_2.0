
import sys, os, math
from typing import List, Tuple, Optional
from PyQt5 import QtWidgets, QtCore, QtGui
from PIL import Image
import numpy as np
import cv2
import pyautogui

# Add project root to sys.path so "core" is importable when run directly
ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.append(ROOT)

from core.image_hash import phash_hex_simple

Rect = Tuple[int,int,int,int]

def pil_to_cv(img: Image.Image):
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

def detect_rects_for_text(cv_bgr) -> List[Rect]:
    """Detect candidate rectangles using edges + contours; filter by reasonable size/aspect/area."""
    gray = cv2.cvtColor(cv_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3,3), 0)
    edges = cv2.Canny(gray, 50, 150)
    edges = cv2.dilate(edges, None, iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    H, W = gray.shape
    rects: List[Rect] = []
    for c in contours:
        x,y,w,h = cv2.boundingRect(c)
        if w < 20 or h < 12:        # too small
            continue
        if w > W or h > H:          # too large
            continue
        area = w*h
        if area < 150:              # noise
            continue
        aspect = w / max(1.0, float(h))
        if aspect < 0.5 or aspect > 20.0:
            continue
        rects.append((x,y,w,h))
    # Optionally merge overlapping rects (simple NMS by IoU)
    rects = nms_rects(rects, iou_thresh=0.3)
    return rects

def iou(a: Rect, b: Rect) -> float:
    ax,ay,aw,ah = a; bx,by,bw,bh = b
    ax2, ay2 = ax+aw, ay+ah
    bx2, by2 = bx+bw, by+bh
    x1, y1 = max(ax, bx), max(ay, by)
    x2, y2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, x2-x1), max(0, y2-y1)
    inter = iw*ih
    if inter == 0: return 0.0
    ua = aw*ah + bw*bh - inter
    return inter / max(1.0, float(ua))

def nms_rects(rects: List[Rect], iou_thresh: float=0.4) -> List[Rect]:
    rects = sorted(rects, key=lambda r: r[2]*r[3], reverse=True)
    kept: List[Rect] = []
    for r in rects:
        if all(iou(r, k) < iou_thresh for k in kept):
            kept.append(r)
    return kept

class ScreenshotSelect(QtWidgets.QMainWindow):
    rectSelected = QtCore.pyqtSignal(QtCore.QRect)

    def __init__(self, mode: str = "hash"):
        super().__init__()
        self.mode = mode  # "hash" or "rect"
        self.setWindowTitle("usefulcliker_gui — select area (drag) or click candidate; Enter to accept, Esc to cancel")
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.FramelessWindowHint)
        self.setWindowState(self.windowState() | QtCore.Qt.WindowFullScreen)

        # Capture screen
        self.screen_pil: Image.Image = pyautogui.screenshot()
        self.cv = pil_to_cv(self.screen_pil)

        # Pre-detect candidate rectangles
        self.candidates: List[Rect] = detect_rects_for_text(self.cv)

        # Prepare base image
        self.qimg = self.pil2qimage(self.screen_pil)
        self.label = QtWidgets.QLabel()
        self.label.setPixmap(QtGui.QPixmap.fromImage(self.qimg))
        self.setCentralWidget(self.label)

        # Overlay for drawing
        self.overlay = QtWidgets.QLabel(self.label)
        self.overlay.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.overlay.resize(self.label.size())

        # UI helpers
        self.btn = QtWidgets.QPushButton("Save", self)
        self.btn.clicked.connect(self.finish_select)
        self.btn.setStyleSheet("position: absolute; top: 20px; left: 20px; padding: 8px 12px;")
        self.btn.raise_()

        self.origin: Optional[QtCore.QPoint] = None
        self.currentRect: Optional[QtCore.QRect] = None
        self.hoverIndex: Optional[int] = None
        self.selectedIndex: Optional[int] = None

        self.repaint_overlay()

    def pil2qimage(self, im: Image.Image):
        return QtGui.QImage(im.tobytes(), im.width, im.height, im.width*3, QtGui.QImage.Format_RGB888)

    def mousePressEvent(self, e: QtGui.QMouseEvent):
        # If clicking on a candidate, select it
        p = e.pos()
        idx = self.find_candidate_at_point(p.x(), p.y())
        if idx is not None:
            self.selectedIndex = idx
            self.currentRect = None  # clear manual selection
            self.repaint_overlay()
            return
        # Otherwise, start manual drag
        self.origin = e.pos()
        self.currentRect = QtCore.QRect(self.origin, self.origin)

    def mouseMoveEvent(self, e: QtGui.QMouseEvent):
        # Update hover
        p = e.pos()
        self.hoverIndex = self.find_candidate_at_point(p.x(), p.y())
        # Update drag rect
        if self.origin is not None:
            self.currentRect = QtCore.QRect(self.origin, e.pos()).normalized()
        self.repaint_overlay()

    def mouseReleaseEvent(self, e: QtGui.QMouseEvent):
        if self.origin is None:
            return
        self.currentRect = QtCore.QRect(self.origin, e.pos()).normalized()
        self.origin = None
        self.repaint_overlay()

    def keyPressEvent(self, e: QtGui.QKeyEvent):
        if e.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            self.finish_select()
        elif e.key() == QtCore.Qt.Key_Escape:
            self.close()

    def find_candidate_at_point(self, x: int, y: int) -> Optional[int]:
        for i,(rx,ry,rw,rh) in enumerate(self.candidates):
            if rx <= x <= rx+rw and ry <= y <= ry+rh:
                return i
        return None

    def repaint_overlay(self):
        pix = QtGui.QPixmap(self.qimg.size())
        pix.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(pix)

        # Draw all candidates as translucent rectangles
        for i,(x,y,w,h) in enumerate(self.candidates):
            color = QtGui.QColor(0, 150, 255, 60)  # cyan-ish translucent
            pen = QtGui.QPen(QtGui.QColor(0, 150, 255, 140), 2)
            if i == self.hoverIndex:
                color = QtGui.QColor(255, 0, 0, 60)   # hover -> red translucent
                pen = QtGui.QPen(QtGui.QColor(255, 0, 0, 200), 3)
            if i == self.selectedIndex:
                color = QtGui.QColor(0, 255, 0, 60)   # selected -> green
                pen = QtGui.QPen(QtGui.QColor(0, 255, 0, 200), 3)

            painter.setBrush(QtGui.QBrush(color))
            painter.setPen(pen)
            painter.drawRect(QtCore.QRect(x, y, w, h))

        # Draw manual selection if any
        if self.currentRect:
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 0, 0, 220), 2, QtCore.Qt.DashLine))
            painter.drawRect(self.currentRect)

        painter.end()
        self.overlay.setPixmap(pix)

    def finish_select(self):
        rect: Optional[Rect] = None
        if self.selectedIndex is not None:
            rect = self.candidates[self.selectedIndex]
        elif self.currentRect is not None:
            r = self.currentRect
            rect = (r.left(), r.top(), r.width(), r.height())

        if rect is None:
            # nothing chosen
            return

        x,y,w,h = rect
        crop = self.screen_pil.crop((x, y, x+w, y+h))

        if self.mode == "rect":
            print(f"{x},{y},{w},{h}")
        else:  # hash (default)
            hhex = phash_hex_simple(crop)
            # save
            os.makedirs("gui/hashes", exist_ok=True)
            with open("gui/hashes/last_hash.txt", "w", encoding="utf-8") as f:
                f.write(hhex)
            print(hhex)

        sys.stdout.flush()
        self.close()

def main():
    import argparse
    ap = argparse.ArgumentParser(description="usefulcliker_gui — rectangle/hash selection")
    ap.add_argument("--mode", choices=["hash","rect"], default="hash", help="Return pHash (hash) or rectangle (rect)")
    args = ap.parse_args()
    app = QtWidgets.QApplication(sys.argv)
    w = ScreenshotSelect(mode=args.mode)
    w.show()
    app.exec_()

if __name__ == "__main__":
    main()
