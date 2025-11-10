# -*- coding: utf-8 -*-
import torch
from torch.nn import ReLU, LogSoftmax
from torch import flatten
import torchvision
import torchvision.transforms as transforms
import torch.utils.data as data_utils
import random
import os
from torchvision.io import read_image, ImageReadMode

# Create a custom dataset class
class TextAreaDataset(torch.utils.data.Dataset):
    def __init__(self, root_dir, test=False):
        self.root_dir = root_dir

        self.images = []
        self.labels = []
        root_dir = "text_area_cls_data\\text"
        for filename in os.listdir(root_dir):
            image_path = os.path.join(root_dir, filename)
            self.images.append(image_path)
            self.labels.append(0)

        root_dir = "text_area_cls_data\\non-text"
        for filename in os.listdir(root_dir):
            image_path = os.path.join(root_dir, filename)
            self.images.append(image_path)
            self.labels.append(1)
        
        
        root_dir = "preprocess"
        test_images = []
        test_labels = []
        if test:
            for filename in os.listdir(root_dir):
                if filename == "chars":
                    continue
                image_path = os.path.join(root_dir, filename)
                test_images.append(image_path)
                test_labels.append(int(filename.split(".")[0]))
                print(filename.split(".")[0])
            self.images = test_images
            self.labels = test_labels

    def __len__(self):
        return len(self.images)

    def __getitem__(self, index):
        image_path = self.images[index] # Image.open(image_path) #
        image = read_image(image_path, ImageReadMode.GRAY)
        transform = transforms.Resize((64,64),antialias=True)
        image = transform(image)
       # imagetun = torch.tensor(image)
       # image = (imagetun).unsqueeze(0)
        image = image.float()
        #if self.transform is not None:
         

        label = torch.tensor(self.labels[index])

        return image_path, image, label

# Load the custom dataset
dataset = TextAreaDataset(root_dir='text_area_cls_data')
train_loader = data_utils.DataLoader(dataset, batch_size=32, shuffle=True)

num_classes = 2
#train_data = dataset.transform(transform)

# Define the CNN model
class TextAreaClassifier(torch.nn.Module):
    def __init__(self):
        super(TextAreaClassifier, self).__init__()

        self.conv1 = torch.nn.Conv2d(1, 32, kernel_size=(3,3), stride=1, padding=1)
        self.pool1 = torch.nn.MaxPool2d(kernel_size=(2, 2), )
        self.relu1 = ReLU()
        self.conv2 = torch.nn.Conv2d(32, 32, kernel_size=(3,3), stride=1, padding=1)
        self.pool2 = torch.nn.MaxPool2d(kernel_size=(2, 2))
        self.relu2 = ReLU()
        self.fc1 = torch.nn.Linear(8192, 500)
        self.flat = torch.nn.Flatten()
        self.relu3 = ReLU()
        self.fc2 = torch.nn.Linear(in_features=500, out_features=num_classes)
        self.logSoftmax = LogSoftmax(dim=1)

    def forward(self, x):
  		# POOL layers
        x = self.conv1(x)
        x = self.relu1(x)
        x = self.pool1(x)
  		# pass the output from the previous layer through the second
  		# set of CONV => RELU => POOL layers
        x = self.conv2(x)
        x = self.relu2(x)
        x = self.pool2(x)
  		# flatten the output from the previous layer and pass it
  		# through our only set of FC => RELU layers
        x = self.flat(x)
        x = self.fc1(x)
        x = self.relu3(x)
        x = self.fc2(x)
  		# pass the output to our softmax classifier to get our output
  		# predictions
        output = self.logSoftmax(x)
        return x

# Create the model instance
model = TextAreaClassifier()
# Move the module to GPU

def train():
    # Define the loss function and optimizer
    criterion = torch.nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    
    # Train the model
    for epoch in range(10):
        for i, (_, images, labels) in enumerate(train_loader):
            # Forward pass
            outputs = model(images)
            loss = criterion(outputs, labels)
    
            # Backward pass
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
    
            if i % 100 == 0:
                print('Epoch: {} Loss: {:.4f}'.format(epoch, loss.item()))
    torch.save(model, "text_classifier.model")

#train()

model = torch.load("text_classifier.model")
# # Test the model
test_dataset = TextAreaDataset(root_dir='text_area_cls_data\\test', test=True)
train_loader = data_utils.DataLoader(test_dataset, batch_size=32, shuffle=True)
# test_data = dataset.test_data.transform(transform)
# test_labels = dataset.test_labels

correct = 0
total = 0

for i, (image_paths, images, labels) in enumerate(train_loader):
    outputs = model(images)
    _, predicted = torch.max(outputs.data, 1)
    print(f"{labels[0]}-{predicted[0]}")
    for j, path in enumerate(image_paths):
        if predicted[j] == 1: # non text
           os.remove(path)
           print(f"remove {path}")
        

