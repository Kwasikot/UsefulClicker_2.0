
import random, time, pyautogui, pyperclip
pyautogui.FAILSAFE = True
def click_xy(x:int,y:int,button:str='left'): pyautogui.click(x=x,y=y,button=button)
def click_area(area,button:str='left'):
    x1,y1,x2,y2=area; import random as R
    x=R.randint(min(x1,x2),max(x1,x2)); y=R.randint(min(y1,y2),max(y1,y2)); pyautogui.click(x=x,y=y,button=button)
def type_text(text:str, mode:str='type'):
    if mode=='copy_paste': pyperclip.copy(text); pyautogui.hotkey('ctrl','v')
    else: pyautogui.write(text)
def parse_combo(combo:str):
    return [p.strip().lower() for p in combo.split('+')]
def hotkey(combo:str, delay_ms=None):
    pyautogui.hotkey(*parse_combo(combo)); 
    if delay_ms: time.sleep(delay_ms/1000.0)
def keysequence(seq:str, delay_ms=None):
    if delay_ms:
        for ch in seq: pyautogui.write(ch); time.sleep(delay_ms/1000.0)
    else: pyautogui.write(seq)
def screenshot_pil():
    return pyautogui.screenshot()
