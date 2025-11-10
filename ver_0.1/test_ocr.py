# -*- coding: utf-8 -*-
import cv2
import numpy as np
import matplotlib.pyplot as plt
import random
from screenshot import take_screenshot
import shutil
import sys
import torchvision
import torchvision.transforms as transforms
import torch.utils.data as data_utils
import os
from torchvision.io import read_image, ImageReadMode
from PIL import Image
from stringlen_estimation import StringLenEstimationModel
import torch

def plot_opencv_image(image):

  # Convert the OpenCV image to a NumPy array.
  image_array = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

  # Plot the NumPy array using Matplotlib.
  plt.imshow(image_array)
  plt.show()

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

def split_word_rect(image, bounding_rect, n):
    h, w = bounding_rect[3], bounding_rect[2]
   # n = 5
    spacing = int(w / n)
    for i in range(n):
      print(i * spacing)
      cv2.line(image, (i * spacing + bounding_rect[0], bounding_rect[1]), 
                      (i * spacing + bounding_rect[0], h + bounding_rect[1]), (255, 0, 0), 1)

def mat_to_pil(mat):

    # Get the shape of the Mat object
    (h, w) = mat.shape[:2]

    # Initialize a Pillow Image object with the same size as the Mat object
    img = Image.new('RGB', (h, w), (255, 255, 255))

    # Copy the Mat object data to the Pillow Image object
    for y in range(h):
        for x in range(w):
            img.putdata(mat[y, x])

    return img

def cv2_to_pil(mat):
    # Convert the Mat object to a numpy array
    arr = np.array(mat)

    # Create a PIL image from the numpy array
    im = Image.fromarray(arr)

    return im

def pre_image(image,model):

   mean = [0.485, 0.456, 0.406] 
   std = [0.229, 0.224, 0.225]

   # get normalized image
   image = cv2.resize(image, (160, 32))
   cv2.imwrite("tmp.png", image)
   img =  read_image("tmp.png", ImageReadMode.GRAY)
   print(img.shape)
   img = img.float()
   #img = img.T
   print(img.shape)
   #transform_norm = transforms.Compose([
   #                                     transforms.Resize((1, 160,32)),transforms.Normalize(mean, std)])
  # img_normalized = transform_norm(img).float()
   #print(img_normalized.shape)
   #img_normalized = img_normalized.unsqueeze_(0)
   # input = Variable(image_tensor)
   #img_normalized = img_normalized.to('cuda')
   # print(img_normalized.shape)


       
   with torch.no_grad():
      model.eval()  
      output = model(img)
      # print(output)
      index = output.data.cpu().numpy().argmax()
      return index
      
def cv2_to_torch(mat):
   
    numpy_img =  np.asarray( mat[:,:] )
    stacked = np.stack(numpy_img)
    tensor = torch.from_numpy(numpy_img)

  

    return tensor

def crop_rect(image, left, top, right, bottom):
    return image[top:bottom, left:right]

def detect_chars():
  # Read the image.
  image = take_screenshot()
  cv2.imwrite("screenshot.png", image)

  
  
  # Create the kernel.
  kernel = np.array([[0,   0,    0,  ],
                     [2, 2,  2 ],
                     [0,   0,    0]])
 # kernel = kernel.T
                     
  # Detect edges on the image.
  edges = canny_edge_detection(image, 10, 100)
 
  # Creating the kernel(2d convolution matrix)
  #kernel = np.ones((5, 5), np.float32)/30
 # Apply convolution using OpenCV.
  #grayscale_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
  #ret, thresh = cv2.threshold(grayscale_image,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
  conv_image = convolution_with_long_horizontal_kernel_opencv(edges, kernel)
  cv2.imwrite("conv_image.png", conv_image)
  
  
  # Find the contours in the image.
  contours, hierarchy = cv2.findContours(conv_image, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

  # Filter the contours by maximum width.
  filtered_contours = filter_contours_by_max_width(contours, 300, 10)

  rects = []
  rimage = image.copy()
  # Draw the filtered contours on the image.
  for contour in filtered_contours:
      # Generate a random color for each contour.
    random_color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
    #cv2.drawContours(image, [contour], 0, random_color, 2)
    bounding_rect = cv2.boundingRect(contour)
    bounding_rect = (bounding_rect[0]-3, bounding_rect[1]-3,bounding_rect[2]+3,bounding_rect[3]+3)
    
    if bounding_rect[2] > 20:
        rects.append(bounding_rect)
  
    cv2.rectangle(rimage, (bounding_rect[0], bounding_rect[1]),
                   (bounding_rect[0] + bounding_rect[2], bounding_rect[1] + bounding_rect[3]),
                   random_color, 2)



  # Display the original image and the gradient image.
  plot_opencv_image(image)
  
  cv2.imwrite("filtering.png", rimage)
  
  
  return rects, image






# -----------------------------------------------------------------------------

# Create a custom dataset class
class StringsLenDataset(torch.utils.data.Dataset):
    def __init__(self, image, rects):
        self.image = image
        self.rects = rects
       # self.transform = transforms.Compose([transforms.ToTensor()])
        self.images = []
        self.labels = []

    
    def __len__(self):
        return len(self.rects)

    def __getitem__(self, index):
        bounding_rect = self.rects[index] # Image.open(image_path) #
        try:
            sub_image = crop_rect(self.image, bounding_rect[0], bounding_rect[1], 
                                         bounding_rect[0] + bounding_rect[2], 
                                         bounding_rect[1] + bounding_rect[3])
            sub_image = cv2.resize(sub_image, (160, 32))
            grayscale_image = cv2.cvtColor(sub_image, cv2.COLOR_BGR2GRAY)
            filename = f"tmp\{random.randint(0, 10000)}.png"
            cv2.imwrite(filename, grayscale_image)
            #image =  cv2_to_torch(grayscale_image)  
            image =  read_image(filename, ImageReadMode.GRAY)
            image = image.float()
            #print(image.shape)
        except:
            #print("err")
            grayscale_image = np.zeros((32, 160), dtype=np.uint8)
         
            filename = f"tmp\{random.randint(0, 10000)}.png"
            cv2.imwrite(filename, grayscale_image)
            #image =  cv2_to_torch(grayscale_image)  
            image =  read_image(filename, ImageReadMode.GRAY)
            image = image.float()
            #print(f"exception {image.shape}")
        
       # if self.transform is not None:
       #     image = self.transform(image)
       # image = torch.tensor(image)
       # image = (imagetun).unsqueeze(0)
        #gray = gray.float()
       # gray = gray.to('cuda')
      #print(gray.shape)
       

        label = torch.tensor(1)
        label = label.to('cuda')

        return image, label




rects, image = detect_chars()

shutil.rmtree("tmp",)
os.mkdir("tmp")

# Create the model instance
model = StringLenEstimationModel()
model = torch.load("stringlen_estimation.model")
#model.eval()

# # Test the model
test_dataset = StringsLenDataset(image, rects)
train_loader = data_utils.DataLoader(test_dataset, batch_size=32, shuffle=True)
# test_data = dataset.test_data.transform(transform)
# test_labels = dataset.test_labels

correct = 0
total = 0

for i, (images, labels) in enumerate(train_loader):
    outputs = model(images)
    _, predicted = torch.max(outputs.data, 1)
    #total += labels.size(0)
    #correct += (predicted == labels).sum().item()
    print(predicted)

#print('Accuracy: {}%'.format(100 * correct / total))

 # cv2.waitKey(0)
