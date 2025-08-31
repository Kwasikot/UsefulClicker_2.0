"""Extnode for perception: detect text-containing rectangles and OCR them.

This module is intended to be used from XML as an <extnode>:

<extnode module="perceive_node" class="PerceiveNode" method="perceive" output_var="rects_dict" output_format="dict"/>

The perceive() method returns a dict with key 'rects' containing a list
of {x,y,w,h,text,conf} items.
"""
from typing import List, Dict, Any
try:
    from cv.preprocess import detect_words
    import cv2
except Exception:
    detect_words = None
    cv2 = None

class PerceiveNode:
    def __init__(self, llm=None):
        self.llm = llm

    def perceive(self, **kwargs) -> Dict[str, Any]:
        rects: List[tuple] = []
        if detect_words is None:
            return {'rects': []}
        try:
            rects = detect_words()
        except Exception:
            rects = []

        items = []
        # try to read screenshot.png
        img = None
        try:
            if cv2 is not None:
                img = cv2.imread('screenshot.png')
        except Exception:
            img = None

        # Try to import easyocr for OCR
        try:
            import easyocr
            reader = easyocr.Reader(['ru','en'], gpu=False)
        except Exception:
            reader = None

        for r in rects:
            x,y,w,h = r
            text = ''
            conf = 0.0
            if reader is not None and img is not None:
                try:
                    crop = img[y:y+h, x:x+w]
                    res = reader.readtext(crop)
                    if res:
                        texts = [t[1] for t in res if t and len(t)>1]
                        confs = [float(t[2]) for t in res if t and len(t)>2]
                        text = ' '.join(texts)
                        conf = sum(confs)/len(confs) if confs else 0.0
                except Exception:
                    text = ''
            items.append({'x': x, 'y': y, 'w': w, 'h': h, 'text': text, 'conf': conf})

        return {'rects': items}
