# -*- coding: utf-8 -*-
import torch
from torch.nn import ReLU, LogSoftmax
from torch import flatten
import torchvision
import torchvision.transforms as transforms
import torch.utils.data as data_utils
import os
from torchvision.io import read_image, ImageReadMode
from PIL import Image
import ast
characters = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@:?*"\''

# Create a custom dataset class
class CharBboxDataset(torch.utils.data.Dataset):
    def __init__(self, root_dir, test=False):
        self.root_dir = root_dir
       # self.transform = transforms.Compose([transforms.ToTensor()])
        self.images = []
        self.bboxes = []
        
        fn = "char_bboxes_dataset\\9_bboxes.csv"
        f_in = open(fn, 'r', encoding='utf-8')
        lines = f_in.readlines()
        total = len(lines)
        for_test = int(len(lines) / 10)
        if test:
            lines = lines[total-for_test:]
        else:
            lines = lines[:total-for_test]
            
        for line in lines:
            parts = line.split("\t")
            self.images.append(parts[0])
            self.bboxes.append(ast.literal_eval(parts[1]))
        #print(self.bboxes)


    def __len__(self):
        return len(self.images)

    def __getitem__(self, index):
        image_path = self.images[index] # Image.open(image_path) #
        image =  read_image(image_path, ImageReadMode.GRAY)
       # if self.transform is not None:
       #     image = self.transform(image)
       # image = torch.tensor(image)
       # image = (imagetun).unsqueeze(0)
        image = image.float()
        image = image.to('cuda')
        height = image.shape[1]
        width =  image.shape[2]
        
       

        bbox = torch.tensor(self.bboxes[index])
        bbox = bbox.to('cuda')
        bbox = bbox.float()
        # normilize bbox coordinates to (0,1)
        bbox[0] = bbox[0] / width
        bbox[1] = bbox[1] / height
        bbox[2] = bbox[2] / width
        bbox[3] = bbox[3] / height
        
        #print(bbox)

        return image, bbox


# Load the custom dataset
dataset = CharBboxDataset(root_dir='./char_bboxes_dataset')
train_loader = data_utils.DataLoader(dataset, batch_size=32, shuffle=True)


# Define the CNN model
class CharBboxModel(torch.nn.Module):
    def __init__(self):
        super(CharBboxModel, self).__init__()

        self.conv1 = torch.nn.Conv2d(1, 64, kernel_size=(2,2), stride=1, padding=1)
        self.conv2 = torch.nn.Conv2d(64, 64, kernel_size=(2,2), stride=1, padding=1)
        self.pool1 = torch.nn.MaxPool2d(kernel_size=(2, 2))
        self.conv3 = torch.nn.Conv2d(64, 128, kernel_size=(2,2), stride=1, padding=1)
        self.conv4 = torch.nn.Conv2d(128, 128, kernel_size=(2,2), stride=1, padding=1)
        self.pool2 = torch.nn.MaxPool2d(kernel_size=(2, 2))
        self.conv5 = torch.nn.Conv2d(128, 256, kernel_size=(2,2), stride=1, padding=1)
        self.conv6 = torch.nn.Conv2d(256, 256, kernel_size=(2,2), stride=1, padding=1)
        self.pool3 = torch.nn.MaxPool2d(kernel_size=(3, 3))
        
        self.fc1 = torch.nn.Linear(41472, 128)
        self.flat = torch.nn.Flatten()
        self.relu4 = ReLU()
        self.fc2 = torch.nn.Linear(in_features=128, out_features=64)
        self.relu5 = ReLU()
        self.fc3 = torch.nn.Linear(in_features=64, out_features=32)
        self.relu6 = ReLU()
        self.fc4 = torch.nn.Linear(in_features=32, out_features=4)
        self.sigmoid = torch.nn.Sigmoid()
        #self.logSoftmax = LogSoftmax(dim=1)

    def forward(self, x):
  		# POOL layers
        x= x.cuda()
        x = self.conv1(x)
        x = self.conv2(x)
        x = self.pool1(x)
  		# pass the output from the previous layer through the second
  		# set of CONV => RELU => POOL layers
        x = self.conv3(x)
        x = self.conv4(x)
        x = self.pool2(x)
        x = self.conv5(x)
        x = self.conv6(x)
        x = self.pool3(x)
        #print(x.shape)
       # x = self.relu3(x)
  		# flatten the output from the previous layer and pass it
  		# through our only set of FC => RELU layers
        x = self.flat(x)
        #print(x.shape)
        x = self.fc1(x)
        x = self.relu4(x)
        x = self.fc2(x)
        x = self.relu5(x)
        x = self.fc3(x)
        x = self.relu6(x)
        x = self.fc4(x)
        x = self.sigmoid(x)
  		# pass the output to our softmax classifier to get our output
  		# predictions
        #output = self.logSoftmax(x)
        return x

# Create the model instance
model = CharBboxModel()
# Move the module to GPU

model = model.to('cuda')

# Define the loss function and optimizer
criterion = torch.nn.MSELoss()
optimizer = torch.optim.Adam(model.parameters(), lr=0.00001)

def train_model():
    # Train the model
    for epoch in range(4):
        for i, (images, bboxes) in enumerate(train_loader):
            # Forward pass
            outputs = model(images)
            #print(bboxes.shape)
            loss = criterion(outputs, bboxes)
            #print(outputs)
    
            # Backward pass
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
    
            if i % 100 == 0:
                print('Epoch: {} Loss: {:.4f}'.format(epoch, loss.item()))
    
    torch.save(model, "char_bbox.model")

train_model()

# # Test the model
test_dataset = CharBboxDataset(root_dir='./string_estimation_test_data', test=True)
train_loader = data_utils.DataLoader(test_dataset, batch_size=32, shuffle=False)

def test_model():
  
    # test_data = dataset.test_data.transform(transform)
    # test_labels = dataset.test_labels
    
    correct = 0
    total = 0
    
    for i, (images, bboxes) in enumerate(train_loader):
        outputs = model(images)
        print("predicted:")
        print(outputs[0])
        print("ground-truth:")
        print(bboxes[0])
    
        #print(predicted)
    
    print('Accuracy: {}%'.format(100 * correct / total))



#model = torch.load("stringlen_estimation.model")
test_model()