# -*- coding: utf-8 -*-
import sys

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtGui import QImage 
from PyQt5.QtWidgets import QLabel
import numpy as np
import cv2
from cv2 import imread
from preprocess import detect_words
from hash_image import hash_image
from PyQt5.QtCore import Qt

ghash_value = ""

def convertQImageToMat(incomingImage):
    '''  Converts a QImage into an opencv MAT format  '''

    incomingImage = incomingImage.convertToFormat(4)

    width = incomingImage.width()
    height = incomingImage.height()

    ptr = incomingImage.bits()
    ptr.setsize(incomingImage.byteCount())
    arr = np.array(ptr).reshape(height, width, 4)  #  Copies the data
    return arr

class MainWindow(QtWidgets.QMainWindow):

    
    def __init__(self, img_path, words=None, rects=None):
        super().__init__()
        if rects == None:
            self.rects = detect_words()
        else:
            self.rects = rects
        self.qrects = []
        self.selected_rect = QtCore.QRect()
        self.hash = ""
        self.words = words
       
        for r in self.rects:
            self.qrects.append(self.tuple_to_qrect(r))
        #print(self.rects)
       # self.qrects = self.remove_contained_rectangles(self.qrects)
      
        #return
        self.qimg = QImage(img_path)
        #self.highlighted_indexes = self.find_image_hashes(known_image_hashes)
        #print(self.highlighted_indexes)
        self.setMouseTracking(True)
        self.last_pos = QtCore.QPoint()
        
        self.label = QLabel("word", self)
        self.label.setStyleSheet("background-color: red; color: white; font-size: 30px;")
        self.label.resize(300,40)
        self.label.move(10, 10)
        self.show()
        
    
        
        self.setStyleSheet('QMainWindow {background:transparent}')
        self.setWindowFlags(
            QtCore.Qt.WindowStaysOnTopHint |
            QtCore.Qt.FramelessWindowHint #|
         #   QtCore.Qt.WindowTransparentForInput
        )
        
      #  self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
       # self.setWindowOpacity(0.9)
        self.showFullScreen()

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(10)
    
    def find_image_hashes(self, know_image_hashes):
        index = 0
        indexes = []
        for r in self.qrects:
            cropped_image = self.crop_image(self.qimg, r)
            hash_value = hash_image(convertQImageToMat(cropped_image))
            if hash_value in know_image_hashes:
                indexes.append(index)
            index = index + 1
        return indexes
   # def update(self):
   #     self.repaint()
    def remove_contained_rectangles(self, rects):
        new_rects = []   
        for rect in rects:
            is_contained = False
            for other_rect in rects:         
                if other_rect != rect and other_rect.contains(rect):
                    is_contained = True
                    break    
            if not is_contained:
                new_rects.append(rect)
    
        return new_rects
    
    def crop_image(self, image, rect):
        x, y, width, height = rect.x(), rect.y(), rect.width(), rect.height()
        cropped_image = QtGui.QImage(width, height, QtGui.QImage.Format_RGBA8888)
        cropped_image = image.copy(x, y, width, height)
        return cropped_image

    def tuple_to_qrect(self, tuple):
        x, y, width, height = tuple
        return QtCore.QRect(x, y, width, height)

    def mouseMoveEvent(self, event):
        self.last_pos = event.pos()
        
    def mousePressEvent(self, event):
        cropped_image = self.crop_image(self.qimg, self.selected_rect)
        #cropped_image.save("cropped.png")
        hash_value = hash_image(convertQImageToMat(cropped_image))
        self.hash = hash_value
        app = QtWidgets.QApplication.instance()
        app.closeAllWindows()
        
    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        rect = self.rect()
        painter.drawImage(rect, self.qimg)
        index = 0
        for i, qr in enumerate(self.qrects):
          
            if qr.contains(self.last_pos):
                painter.setPen(QtGui.QPen(QtGui.QColor('red')))
                painter.fillRect(qr, QtGui.QColor(255,0,0,100))
                self.selected_rect = qr
                if self.words!= None:
                    if i in self.words:
                      self.label.setText(f"{i}:{self.words[i]}")
                      # self.label.setText(f"{i}")
                      
                else:
                    self.label.setText(f"{i}")
            else:
                painter.setPen(QtGui.QPen(QtGui.QColor('green')))
                painter.fillRect(qr, QtGui.QColor(0,255,0,100))
            painter.drawRect(qr)
            index = index + 1
            

def get_image_hash_window():
    app = QtWidgets.QApplication(sys.argv)
    img_path = 'screenshot.png'
    window = MainWindow(img_path)
    window.show()
    app.exec()
    return window.hash

def get_rect_window():
    app = QtWidgets.QApplication(sys.argv)
    img_path = 'screenshot.png'
    window = MainWindow(img_path)
    window.show()
    app.exec()
    r = window.selected_rect
    return (r.x(),r.y(),r.width(),r.height())

def get_words_window(words, rects):
    app = QtWidgets.QApplication(sys.argv)
    img_path = 'screenshot.png'
    window = MainWindow(img_path, words, rects)
    window.show()
    app.exec()
    
hash_value = get_image_hash_window()
print(f"hash_value = {hash_value}")