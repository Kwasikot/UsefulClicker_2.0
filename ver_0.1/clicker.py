# -*- coding: utf-8 -*-
import win32api, win32con
import random
import pyautogui
import time 

def click(x, y, button='left'):
  """Simulates a mouse click at the specified coordinates.

  Args:
    x: The x-coordinate of the click.
    y: The y-coordinate of the click.
    button: The mouse button to click.

  Returns:
    None.
  """
  win32api.SetCursorPos((x, y))
  if button == 'left':
      win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
      win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
  if button == 'right':
       win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
       win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
   
def click_rect(rect, button='left'):
  """Simulates a mouse click at the random point inside rectangle

  Args:
    rect: Rectangle  (xLeft, yTop, width, height)
  Returns:
    None.
  """    
  x = random.randint(rect[0], rect[0]+rect[2])
  y = random.randint(rect[1], rect[1]+rect[3])
  click(x, y, button)
  
def type_text(text):
    """Simulates a keyboard input

    Args:
      text: text to type
    Returns:
      None.
    """    
    # Convert the text to a list of key presses
    keys = []
    for char in text:
        if char == ' ':
            keys.append('space')
        elif char == '\n':
            keys.append('enter')
        else:
            keys.append(char)
    
    # Simulate each key press
    for key in keys:
        pyautogui.press(key)
        time.sleep(0.01)
        

