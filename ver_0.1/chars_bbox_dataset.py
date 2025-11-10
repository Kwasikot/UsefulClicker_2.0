# -*- coding: utf-8 -*-
import cv2
import numpy as np
import matplotlib.pyplot as plt
import random
from screenshot import take_screenshot
from preprocess import canny_edge_detection
import torch
import torchvision.models as models
import torchvision.transforms as transforms

import sys
from PyQt5.QtGui import QImage, QPainter
from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt, QRect
from PyQt5.QtGui import QFontDatabase, QFont, QColor 
from PyQt5.QtGui import QImage, QPainter, QTransform, QPixmap
from PyQt5.QtGui import QFontMetrics



def plot_opencv_image(image):

  # Convert the OpenCV image to a NumPy array.
  image_array = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

  # Plot the NumPy array using Matplotlib.
  plt.imshow(image_array)
  plt.show()
  
def convertQImageToMat(incomingImage):
    '''  Converts a QImage into an opencv MAT format  '''

    incomingImage = incomingImage.convertToFormat(4)

    width = incomingImage.width()
    height = incomingImage.height()

    ptr = incomingImage.bits()
    ptr.setsize(incomingImage.byteCount())
    arr = np.array(ptr).reshape(height, width, 4)  #  Copies the data
    return arr

def findBBoxes(text, image, painter):
    widths = []
    heights = []
    xs = []
    text2 = ""
    width0 = 0
    for char in text:
        text2 += char
        bounding_rect = painter.boundingRect(image.rect(), Qt.AlignCenter, text2)
        widths.append(bounding_rect.width() - width0)
        width0 = bounding_rect.width()
    #print(widths)
    width0 = 0
    bboxes = []
    for w in widths:
        x = bounding_rect.x() + width0
        y = bounding_rect.top()
        width = w
        height = bounding_rect.height()
        bbox = QRect(x,y,width,height)
        bboxes.append(bbox)
        width0+=w
    return bboxes

def renderString(text, font):
       max_word_len = 10
       image = QImage(32*max_word_len, 64, QImage.Format_RGB888)
       
       painter = QPainter(image)
       f = QFont(font)
       f.setPixelSize(random.randint(20,35))
       if random.randint(0,10) < 2:
           f.setItalic(True)
       if random.randint(0,10) < 2:    
           f.setBold(True)
       
       painter.setFont(f)
       gray_value_bg = random.randint(170, 255)
       gray_value_fg = int(gray_value_bg / 2) 
       #image.fill(QColor(gray_value_bg, gray_value_bg, gray_value_bg))
       painter.setPen(QColor(gray_value_fg, gray_value_fg, gray_value_fg))
       painter.fillRect(image.rect(), QColor(gray_value_bg, gray_value_bg, gray_value_bg))
       painter.drawText(image.rect(), Qt.AlignCenter, text)
       
   
       bounding_rect = painter.boundingRect(image.rect(), Qt.AlignCenter, text)
       bboxes = findBBoxes(text, image, painter) 
       #painter.drawRect(bboxes[3])
       
       del painter
       im = convertQImageToMat(image)
       # Apply Gaussian blur to the grayscale image to reduce noise.
       blurred_image = cv2.GaussianBlur(im, (3, 3), 0)
   
       return blurred_image, bboxes

def remove_items(list_, indices):
  # Create a new list without the items at the specified indices
  new_list = []
  for i, item in enumerate(list_):
      if i not in indices:
          new_list.append(item)
  return new_list

common_fonts = ['Arial','Times New Roman','Garamond','Verdana','Calibri','Lucida Sans','Microsoft Sans Serif','Tahoma','Arial Narrow','Georgia']
app = QtWidgets.QApplication(sys.argv)
db = QFontDatabase()
indexes_to_remove = [32,60,71,137,165,168,179,254,255,257,258,259]
fonts = [font for font in db.families()]
fonts = remove_items(fonts, indexes_to_remove)
#print(fonts)
fonts_for_train = fonts[2:8]
fonts_for_test = fonts[5:10]
  
# train data
word_dictionary = {}
i = 0
filename = "alice_in_wonderland.txt"
max_word_len = 18


image,_ = renderString("pneumonoultramicro", fonts_for_train[1])  
#image = renderString("email", fonts_for_train[1])  
plot_opencv_image(image)
cv2.imwrite(f"test.png", image)
   
 
   

# ## copy words from the worldlist
# Open the file in 'r' mode (read-only)
with open('en_US-large.txt', 'r', encoding='utf-8') as f:
    # Get a list of all the lines in the file
    lines = f.readlines()

characters = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@:?*"\''

#f_out.write(f"{filename} {box}\n")
my_dict = {}
for char in characters:
    my_dict[char] = {}
    
n = 0
for word in lines:
    for font in common_fonts:
        word = word.strip("\n")
        image, bboxes = renderString(word, font)  
        filename = f"char_bboxes_dataset\images\{len(word)}_{n}.png"
        for i, char in enumerate(word):
            if char not in my_dict:
                continue
            fn_dict = my_dict[char]
            key = f"{filename}"
            if key not in fn_dict:
               fn_dict[key] = [(0,0,0,0)] 
            box = bboxes[i]
            fn_dict[key][0] = (box.x(),box.y(),box.width(),box.height())
            my_dict[char] = fn_dict
            
        print(word)
        cv2.imwrite(filename, image)
        n += 1
#print(my_dict)

for i, char in enumerate(my_dict):
    f_out = open(f"char_bboxes_dataset\{i}_bboxes.csv", 'w', encoding='utf-8')
    for fn in my_dict[char]:
        for box in my_dict[char][fn]:
           f_out.write(f"{fn}\t{box}\n") 
    f_out.close()