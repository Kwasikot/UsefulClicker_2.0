
from PIL import Image
import numpy as np, cv2, imagehash

def pil_to_cv(img: Image.Image):
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

def cv_to_pil(mat):
    return Image.fromarray(cv2.cvtColor(mat, cv2.COLOR_BGR2RGB))

def phash_hex_simple(img: Image.Image) -> str:
    # standard hex string
    return str(imagehash.phash(img))

def hamming_distance_hex(h1: str, h2: str) -> int:
    import imagehash
    return imagehash.hex_to_hash(h1) - imagehash.hex_to_hash(h2)

def rect_candidates_from_edges(cv_bgr):
    gray = cv2.cvtColor(cv_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3,3), 0)
    edges = cv2.Canny(gray, 50, 150)
    edges = cv2.dilate(edges, None, iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    rects=[]
    H,W=gray.shape
    for c in contours:
        x,y,w,h = cv2.boundingRect(c)
        if w<20 or h<20: continue
        if w>W or h>H: continue
        rects.append((x,y,w,h))
    return rects
