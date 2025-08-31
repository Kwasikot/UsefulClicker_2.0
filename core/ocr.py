
from typing import List, Tuple, Optional
import pytesseract
from PIL import Image
import numpy as np, cv2

def ocr_words_boxes(img_pil: Image.Image, lang: str = "eng") -> List[Tuple[str, Tuple[int,int,int,int]]]:
    data = pytesseract.image_to_data(img_pil, lang=lang, output_type=pytesseract.Output.DICT)
    res=[]
    n = len(data['text'])
    for i in range(n):
        t = data['text'][i]
        try:
            x,y,w,h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
        except Exception:
            continue
        if t and t.strip():
            res.append((t.strip(), (x,y,w,h)))
    return res

def find_text_box(img_pil: Image.Image, query: str, lang: str = "eng", case_sensitive: bool=False, partial: bool=False, area=None):
    if area:
        x1,y1,x2,y2 = area
        img_pil = img_pil.crop((x1,y1,x2,y2))
        offset=(x1,y1)
    else:
        offset=(0,0)
    words = ocr_words_boxes(img_pil, lang=lang)
    q = query if case_sensitive else query.lower()
    best=None
    for w,(x,y,wid,hei) in words:
        ww = w if case_sensitive else w.lower()
        ok = (q in ww) if partial else (q == ww)
        if ok:
            best = (x+offset[0], y+offset[1], wid, hei)
            break
    return best
