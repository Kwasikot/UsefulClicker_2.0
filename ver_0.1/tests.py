# -*- coding: utf-8 -*-
"""
Created on Fri Aug 25 13:03:25 2023

@author: admin
"""

from clicker import click_rect, type_text
import cv2
from hash_image import hash_image
from gui import get_image_hash_window, get_rect_window
from preprocess import detect_words, char_segmentation
import subprocess
import time
import pyautogui

def ClickImageHash(known_hash):
    rects = detect_words()
    screenshot = cv2.imread("data\\screenshot.png")
    for r in rects:
        cropped_img = screenshot[r[1]:r[1] + r[3],r[0]:r[0] + r[2]]
        hash_value = hash_image(cropped_img)
        if hash_value == known_hash:
            click_rect(r)
            return r


def ClickImageHashTest():
    image_hash = get_image_hash_window()
    print(f"hash_value={image_hash}")
    ClickImageHash(image_hash)

def ClickRectTest():
    selected_rect = get_rect_window()
    print(f"selected_rect={selected_rect}")
    click_rect(selected_rect)
        

def NotepadTest1():
    notepad_path = r"Notepad.exe"
    subprocess.Popen([notepad_path])
    time.sleep(0.5)
    type_text("This string is generated in UsefulClicker!")
    pyautogui.hotkey('alt', 'e')
    pyautogui.press('o')
    pyautogui.press('tab')
    pyautogui.press('tab')
    pyautogui.press('tab')
    type_text("25")
    pyautogui.press('tab')
    pyautogui.press('backspace')
    
    
ClickImageHashTest()
#NotepadTest1()
#ClickRectTest()
