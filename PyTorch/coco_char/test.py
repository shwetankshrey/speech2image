#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon May  7 10:24:35 2018

@author: danny

Loads pretrained models in the results folder and calculates the validation and test scores for botch annotation and image retrieval
"""
#!/usr/bin/env python
from __future__ import print_function

import time
import os
import tables
import argparse
import torch
from torch.autograd import Variable

from minibatchers import iterate_text_5fold, iterate_text
from costum_loss import batch_hinge_loss, ordered_loss
from evaluate import caption2image, image2caption
from encoders import img_encoder, char_gru_encoder
from data_split import split_data
##################################### parameter settings ##############################################

parser = argparse.ArgumentParser(description='Create and run an articulatory feature classification DNN')

# args concerning file location
parser.add_argument('-data_loc', type = str, default = '/prep_data/flickr_features.h5',
                    help = 'location of the feature file, default: /prep_data/flickr_features.h5')
parser.add_argument('-split_loc', type = str, default = '/data/speech2image/PyTorch/flickr_audio/dataset.json', 
                    help = 'location of the json file containing the data split information')
parser.add_argument('-results_loc', type = str, default = '/prep_data/char_results/',
                    help = 'location of the json file containing the data split information')
# args concerning training settings
parser.add_argument('-batch_size', type = int, default = 32, help = 'batch size, default: 32')
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
               'bidirectional': True, 'dropout': 0}, 'att':{'in_size': 2048, 'hidden_size': 128}}

image_config = {'linear':{'in_size': 2048, 'out_size': 2048}, 'norm': True}


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
    batcher = iterate_text_5fold    
elif args.data_base == 'flickr':
    f_nodes = [node for node in iterate_flickr(data_file)]
    # define the batcher type to use.
    batcher = iterate_text_5fold
elif args.data_base == 'places':
    print('places has no written captions')
else:
    print('incorrect database option')
    exit()   
    
# split the database into train test and validation sets. default settings uses the json file
# with the karpathy split
train, test, val = split_data(f_nodes, args.split_loc)

def recall(data, at_n, c2i, i2c, prepend):
    # calculate the recall@n. Arguments are a set of nodes, the @n values, whether to do caption2image, image2caption or both
    # and a prepend string (e.g. to print validation or test in front of the results)
    if c2i:
        # create a minibatcher over the validation set
        iterator = batcher(data, args.batch_size, args.visual, args.cap, shuffle = False)
        recall, median_rank = caption2image(iterator, img_net, cap_net, at_n, dtype)
        # print some info about this epoch
        for x in range(len(recall)):
            print(prepend + ' caption2image recall@' + str(at_n[x]) + ' = ' + str(recall[x]*100) + '%')
        print(prepend + ' caption2image median rank= ' + str(median_rank))
    if i2c:
        # create a minibatcher over the validation set
        iterator = batcher(data, args.batch_size, args.visual, args.cap, shuffle = False)
        recall, median_rank = image2caption(iterator, img_net, cap_net, at_n, dtype)
        for x in range(len(recall)):
            print(prepend + ' image2caption recall@' + str(at_n[x]) + ' = ' + str(recall[x]*100) + '%')
        print(prepend + ' image2caption median rank= ' + str(median_rank))  


#####################################################

# network modules
img_net = img_encoder(image_config)
cap_net = char_gru_encoder(char_config)

# move graph to gpu if cuda is availlable
if cuda:
    img_net.cuda()
    text_net.cuda()

# list all the trained model parameters
models = os.listdir(args.results_loc)
caption_models = [x for x in models if 'caption' in x]
img_models = [x for x in models if 'image' in x]

# run the image and caption retrieval
img_models.sort()
caption_models.sort()
for img, cap in zip(img_models, caption_models) :
    
    img_state = torch.load(args.results_loc + img)
    caption_state = torch.load(args.results_loc + cap)
    
    img_net.load_state_dict(img_state)
    cap_net.load_state_dict(caption_state)
    # calculate the recall@n
    # create a minibatcher over the validation set
    print("Epoch " + img.split('.')[1])
    recall(val, [1, 5, 10], c2i = True, i2c = True, prepend = 'validation') 
    recall(val[:1000], [1, 5, 10], c2i = True, i2c = True, prepend = 'validation 1k') 
    recall(test, [1, 5, 10], c2i = True, i2c = True, prepend = 'test') 
    recall(test[1000], [1, 5, 10], c2i = True, i2c = True, prepend = 'test 1k') 
