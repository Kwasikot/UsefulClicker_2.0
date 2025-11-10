# -*- coding: utf-8 -*-


import sys
import cv2
import pyautogui

def take_screenshot():
  """Takes a screenshot of the entire screen and saves it to a file."""

  screenshot = pyautogui.screenshot()
  screenshot.save("screenshot.png", "png")
  mat = cv2.imread("screenshot.png")
 # mat = mat.reshape(screenshot.height(), screenshot.width(), screenshot.depth() // 8)
  return mat


