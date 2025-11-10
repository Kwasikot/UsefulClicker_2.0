# -*- coding: utf-8 -*-
import cv2
import struct

def double_to_hex(f):
    return hex(struct.unpack('<Q', struct.pack('<d', f))[0])

def hash_image(image):

    image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    image = cv2.resize(image, (8, 8))

    hash_value = 0
    for i in range(8):
        for j in range(8):
            hash_value += (image[i][j]/2) * 2**(8 * i + j)
    hex_string = double_to_hex(hash_value)

    return hex_string

