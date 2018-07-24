#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon May  7 10:24:35 2018

@author: danny

Loads pretrained network parameters and combines their predictions into an ensemble.
Works well with a cyclic learning rate because this lr causes the network to settle in 
several disctinc local minima, while these networks then can have similar test scores
they make different mistakes leading to a meaningfull ensemble. 

for this script to work put the best scoring models in the results folder. With a cyclic learning
rate cycle of 4 epochs this is every fourth epoch (except the first few)
"""
#!/usr/bin/env python
from __future__ import print_function

import os
import tables
import argparse
import torch
import sys
import numpy as np
import sklearn.linear_model
import scipy.spatial
from torch.autograd import Variable

sys.path.append('/data/speech2image/PyTorch/functions')

from minibatchers import iterate_raw_text_5fold, iterate_raw_text
from evaluate import evaluate
from encoders import img_encoder, char_gru_encoder
from data_split import split_data
##################################### parameter settings ##############################################

parser = argparse.ArgumentParser(description='Create and run an articulatory feature classification DNN')

# args concerning file location
parser.add_argument('-data_loc', type = str, default = '/prep_data/flickr_features.h5',
                    help = 'location of the feature file, default: /prep_data/flickr_features.h5')
parser.add_argument('-split_loc', type = str, default = '/data/speech2image/preprocessing/dataset.json', 
                    help = 'location of the json file containing the data split information')
parser.add_argument('-results_loc', type = str, default = '/data/speech2image/PyTorch/flickr_char/ensemble/',
                    help = 'location of the json file containing the data split information')
# args concerning training settings
parser.add_argument('-batch_size', type = int, default = 100, help = 'batch size, default: 32')
parser.add_argument('-cuda', type = bool, default = True, help = 'use cuda, default: True')
# args concerning the database and which features to load
parser.add_argument('-data_base', type = str, default = 'flickr', help = 'database to train on, default: flickr')
parser.add_argument('-visual', type = str, default = 'resnet', help = 'name of the node containing the visual features, default: resnet')
parser.add_argument('-cap', type = str, default = 'raw_text', help = 'name of the node containing the audio features, default: raw_text')
parser.add_argument('-gradient_clipping', type = bool, default = True, help ='use gradient clipping, default: True')

args = parser.parse_args()

# create config dictionaries with all the parameters for your encoders

char_config = {'embed':{'num_chars': 100, 'embedding_dim': 20, 'sparse': False, 'padding_idx': 0},
               'gru':{'input_size': 20, 'hidden_size': 1024, 'num_layers': 1, 'batch_first': True,
               'bidirectional': True, 'dropout': 0}, 'att':{'in_size': 2048, 'hidden_size': 128, 'heads': 1}}
# automatically adapt the image encoder output size to the size of the caption encoder
out_size = char_config['gru']['hidden_size'] * 2**char_config['gru']['bidirectional'] * char_config['att']['heads']
image_config = {'linear':{'in_size': 2048, 'out_size': out_size}, 'norm': True}


# open the data file
data_file = tables.open_file(args.data_loc, mode='r+') 

# check if cuda is availlable and user wants to run on gpu
cuda = args.cuda and torch.cuda.is_available()
if cuda:
    print('using gpu')
    # if cuda cast all variables as cuda tensor
    dtype = torch.cuda.FloatTensor
else:
    print('using cpu')
    dtype = torch.FloatTensor

# get a list of all the nodes in the file. h5 format takes at most 10000 leaves per node, so big
# datasets are split into subgroups at the root node 
def iterate_large_dataset(h5_file):
    for x in h5_file.root:
        for y in x:
            yield y
# flickr doesnt need to be split at the root node
def iterate_flickr(h5_file):
    for x in h5_file.root:
        yield x

if args.data_base == 'coco':
    f_nodes = [node for node in iterate_large_dataset(data_file)]
    # define the batcher type to use.
    batcher = iterate_raw_text_5fold    
elif args.data_base == 'flickr':
    f_nodes = [node for node in iterate_flickr(data_file)]
    # define the batcher type to use.
    batcher = iterate_raw_text_5fold
elif args.data_base == 'places':
    print('places has no written captions')
else:
    print('incorrect database option')
    exit()   
    
# split the database into train test and validation sets. default settings uses the json file
# with the karpathy split
train, val = split_data_coco(f_nodes)
test = train[-5000:]
# nr of caption in the test set
test_size = len(test) * 5
#####################################################

# network modules
img_net = img_encoder(image_config)
cap_net = char_gru_encoder(char_config)

# move graph to gpu if cuda is availlable
if cuda:
    img_net.cuda()
    cap_net.cuda()

# list all the trained model parameters
models = os.listdir(args.results_loc)
caption_models = [x for x in models if 'caption' in x]
img_models = [x for x in models if 'image' in x]

# run the image and caption retrieval and create an ensemble
img_models.sort()
caption_models.sort()
caps = torch.autograd.Variable(dtype(np.zeros((test_size, out_size)))).data
imgs = torch.autograd.Variable(dtype(np.zeros((test_size, out_size)))).data

evaluator = evaluate(dtype, img_net, cap_net)
evaluator.set_n([1,5,10])

a = []
b = []
encode = False

if encode == True:
 
    for img, cap in zip(img_models, caption_models) :
        epoch = img.split('.')[1]
        img_state = torch.load(args.results_loc + img)
        caption_state = torch.load(args.results_loc + cap)
    
        img_net.load_state_dict(img_state)
        cap_net.load_state_dict(caption_state)
        iterator = batcher(test, args.batch_size, args.visual, args.cap, max_chars= 200, shuffle = False)
        
        evaluator.embed_data(iterator)
        caption =  evaluator.return_caption_embeddings()
        image = evaluator.return_image_embeddings()
        print("Epoch " + epoch)
        #print the per epoch results
        
        evaluator.print_caption2image('test')
        evaluator.print_image2caption('test')
        
        evaluator.set_caption_embeddings(caption[:1000])
        evaluator.set_image_embeddings(image[:1000])

        evaluator.print_caption2image('1k test')
        evaluator.print_image2caption('1k test')
        
        caps += caption
        imgs += image
        a.append(caption)
        b.append(image)
    # save the models (handy in case you want to run the ensembling with multiple settings)
    models = []
    for m in range(len(a)):
        # for all pretrained models, concatenate the image and caption embeddings along a new dimension.
        models.append(torch.cat((a[m], b[m]), 0).unsqueeze(2))
    models = torch.cat(models, 2)
    models = models.cpu()
    torch.save(models, 'model')
    # z becomes the ensemble embedding space. We want to minimise the distance between the pretrained models and the embeddings in the ensemble space using procrustal or linear regression
    z = models.mean(2)

if encode == False:
    models = torch.load('model')
    z = models.mean(2)
    #z = torch.rand(10000,2048)

# variables to keep track of the decrease in procrustes disparity
prev_disp =2
disp = 1
while prev_disp - disp >= 0.00001:
    prev_disp = disp
    predict = []
    disparity = []
    # for all the pretrained models apply the procrustes transformations to the ensemble model space
    for x in range(models.size()[2]):
        mtx_1, mtx_2, disp_x = scipy.spatial.procrustes(z.numpy(), models[:,:,x].cpu().numpy())
        # keep track of the predictions and disparity
        predict.append(torch.Tensor(mtx_2).unsqueeze(2))
        disparity.append(disp_x)
    disp = sum(disparity)/len(disparity)
    print(disp)
    # use the predictions to incrementally update the ensemble embedding space
    z = torch.cat(predict, 2).mean(2)

# separate the caption and image embeddings again
caps = z[:5000]
imgs = z[5000:10000]

evaluator.set_image_embeddings(imgs)
evaluator.set_caption_embeddings(caps)

# print the results of the ensemble
evaluator.print_caption2image('test ensemble')
evaluator.print_image2caption('test ensemble')

evaluator.set_caption_embeddings(caps[:1000])
evaluator.set_image_embeddings(imgs[:1000])

evaluator.print_caption2image('1k test ensemble')
evaluator.print_image2caption('1k test ensemble')