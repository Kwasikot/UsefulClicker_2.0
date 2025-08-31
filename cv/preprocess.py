# -*- coding: utf-8 -*-
import cv2
import numpy as np
#import matplotlib.pyplot as plt
import random
#from screenshot import take_screenshot
import sys
import os
import shutil
import pyautogui

def take_screenshot():
  """Takes a screenshot of the entire screen and saves it to a file."""

  screenshot = pyautogui.screenshot()
  screenshot.save("screenshot.png", "png")
  mat = cv2.imread("screenshot.png")
 # mat = mat.reshape(screenshot.height(), screenshot.width(), screenshot.depth() // 8)
  return mat

# def plot_opencv_image(image):

  # # Convert the OpenCV image to a NumPy array.
  # image_array = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

  # # Plot the NumPy array using Matplotlib.
  # plt.imshow(image_array)
  # plt.show()

def canny_edge_detection(image, low_threshold, high_threshold):


  # Convert the image to grayscale.
  grayscale_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

  # Apply Gaussian blur to the grayscale image to reduce noise.
  blurred_image = cv2.GaussianBlur(grayscale_image, (5, 5), 0)

  # Apply Canny edge detection to the blurred image.
  edges = cv2.Canny(blurred_image, low_threshold, high_threshold)

  return edges


def convolution_with_long_horizontal_kernel_opencv(image, kernel):

  # Create the output image.
  output_image = image.copy();

  # Apply convolution using OpenCV.
  cv2.filter2D(src=image, ddepth=-1, kernel=kernel, dst=output_image)

  return output_image


def filter_contours_by_max_width(contours, max_width, min_width):

  filtered_contours = []
  for contour in contours:
    # Get the bounding rectangle of the contour.
    bounding_rect = cv2.boundingRect(contour)

    # Check if the width of the bounding rectangle is less than the maximum width.
    if bounding_rect[2] <= max_width and bounding_rect[2] > min_width:
      filtered_contours.append(contour)

  return filtered_contours

def process_word(image, n):
   
    image = cv2.resize(image, (image.shape[1]*4, image.shape[0]*4))
    grayscale_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    #print(grayscale_image.shape)
    # Detect edges on the image.
    edges = cv2.Canny(grayscale_image, 10, 100)
    contours, hierarchy = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    for i, contour in enumerate(contours):
        bounding_rect = cv2.boundingRect(contour)
        bounding_rect = (bounding_rect[0]-10, bounding_rect[1]-10,bounding_rect[2]+10,bounding_rect[3]+10)
      
        cropped_img = grayscale_image[bounding_rect[1]:bounding_rect[1] + bounding_rect[3],bounding_rect[0]:bounding_rect[0]+ bounding_rect[2]]
        if cropped_img.shape[0] > 0 and cropped_img.shape[1]>0 :
            # use os.path.join to avoid escape-sequence issues on Windows
            import os
            outd = os.path.join('preprocess','chars')
            os.makedirs(outd, exist_ok=True)
            cv2.imwrite(os.path.join(outd, f"{n}_{i}.png"), cropped_img)
            
def detect_words():
  # Read the image.
  image = take_screenshot()
  cv2.imwrite("screenshot.png", image)
  #image = cv2.imread("C:\\Users\\admin\\Pictures\\Screenshots\\Screenshot 2023-08-26 080242.png")
  
  # Create the kernel.
  kernel = np.array([[0,   0,    0,  ],
                     [2, 2,  2 ],
                     [0,   0,    0]])
                     
  # Detect edges on the image.
  edges = canny_edge_detection(image, 10, 100)
  #plot_opencv_image(edges)
 
  conv_image = convolution_with_long_horizontal_kernel_opencv(edges, kernel)
  
  # Find the contours in the image.
  contours, hierarchy = cv2.findContours(conv_image, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

  # Filter the contours by maximum width.
  filtered_contours = filter_contours_by_max_width(contours, 300, 10)

  rects = []
  image_canvas = image.copy()
  
  # Draw the filtered contours on the image.
  for i, contour in enumerate(filtered_contours):
      # Generate a random color for each contour.
    random_color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
    #cv2.drawContours(image, [contour], 0, random_color, 2)
    bounding_rect = cv2.boundingRect(contour)
    bounding_rect = (bounding_rect[0]-3, bounding_rect[1]-3,bounding_rect[2]+3,bounding_rect[3]+3)
    rects.append(bounding_rect)
    
    cropped_img = image[bounding_rect[1]:bounding_rect[1] + bounding_rect[3],bounding_rect[0]:bounding_rect[0]+ bounding_rect[2]]
    #if cropped_img.shape[0] > 2 and cropped_img.shape[1] > 2:
    #    cv2.imwrite(f"preprocess\\{i}.png", cropped_img)
  return rects

#detect_words()


# segmenting chars using "dissection" method
def char_segmentation():
   
    rects = detect_words()
    screenshot =  cv2.imread("screenshot.png")
    chars_dict = {}

    for n_word, bounding_rect in enumerate(rects):
        cropped_img = screenshot[bounding_rect[1]:bounding_rect[1] + bounding_rect[3],bounding_rect[0]:bounding_rect[0]+ bounding_rect[2]]
       # print(cropped_img.shape)
        # cut word
        if cropped_img.shape[0] < 2 or cropped_img.shape[1]<2 :
            continue
        chars_dict[n_word] = []
     
        # Convert the input image to grayscale
        #image = cv2.imread("preprocess\\241.png") 
        image = cropped_img
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
         
         # Define the kernel size and anchor point for the erosion filter
        kernel_size = (3, 3)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        anchor_point = (-1, -1)
        ret, thresh = cv2.threshold(gray,100,255, cv2.THRESH_OTSU) # 
        # plot_opencv_image(thresh)
        white_pixels = np.count_nonzero(thresh == 255)
        black_pixels = np.count_nonzero(thresh == 0)
       #print(f"{white_pixels} {black_pixels}")
        if black_pixels > white_pixels:
            ret, thresh = cv2.threshold(gray,100,255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU) 
            image = cv2.bitwise_not(image)
        # Creating kernel
        kernel = np.ones((2, 2), np.uint8)
        # Using cv2.erode() method 
        dissect_array = []
        for i in range(0, thresh.shape[1], 1):
            sum1 = 0
            for j in range(0, thresh.shape[0], 1):
                sum1+=(thresh[j, i]==0)
            dissect_array.append(sum1)
        #plt.plot(dissect_array)
        prev = 0
        lines_x = []
        for i in range(0, len(dissect_array), 1):
            if dissect_array[i] != 0 and prev == 0:
                lines_x.append(i-1)
                zeros_len=0
            prev = dissect_array[i]
        
        if black_pixels < white_pixels:
          ret, thresh = cv2.threshold(gray,100,255,cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU) # 
        else:
           ret, thresh = cv2.threshold(gray,100,255, cv2.THRESH_OTSU)   
    # apply connected component analysis to the thresholded image
        output = cv2.connectedComponentsWithStats(
        	gray, 4,  cv2.CV_32S)
        (numLabels, labels, stats, centroids) = output
    
       # print(numLabels)
        
         # Loop over all the connected components.
        for i in range(1, numLabels, 1):
            # Find the bounding box of the connected component.
            x = stats[i, cv2.CC_STAT_LEFT]
            lines_x.append(x)
            y = stats[i, cv2.CC_STAT_TOP]
            w = stats[i, cv2.CC_STAT_WIDTH]
            h = stats[i, cv2.CC_STAT_HEIGHT]
            area = stats[i, cv2.CC_STAT_AREA]
            # Draw the bounding box on the output image.
           # cv2.rectangle(image, (x,y),(x+w,y+h), (0, 255, 0), 1)
        lines_x.sort()
        linex_x = set(lines_x)
        # dissect characters
        x0 = 0
        lines_x.append(thresh.shape[1])
        for n_Char, x in enumerate(lines_x):
            if x0!=0:
                cropped_char = image[0:thresh.shape[1],x0:x]    
              
                if cropped_char.shape[1] >= 2:
                    bg = cropped_char[0,0]
                    cropped_char = cv2.resize(cropped_char, (20,20))
                    large_img = np.zeros((32,32,3), np.uint8)
                    large_img[:,:] = bg
                    large_img[6:26,6:26] = cropped_char
                    #print(cropped_char.shape)
                    #cv2.imwrite(f"preprocess\\chars\\{n_word}_{n_Char}.png", large_img)
                    gray2 = cv2.cvtColor(large_img, cv2.COLOR_BGR2GRAY)
                    chars_dict[n_word].append(gray2)
           #cv2.line(image, (x, 0), (x, thresh.shape[1]), (0, 255, 0), 1)
            x0 = x
      
         # Apply the erosion filter to the grayscale image
        #result = cv2.dilate(gray, kernel=kernel_size, anchor=anchor_point, iterations=1)
        #plot_opencv_image(image)
        #plot_opencv_image(thresh)
        #break
    return rects, chars_dict

#char_segmentation()