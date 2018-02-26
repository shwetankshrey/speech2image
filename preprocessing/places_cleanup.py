#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Feb 22 15:28:36 2018
Cleanup the places images database by removing all the images for which no captions 
exist.
@author: danny
"""

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Feb 19 12:03:28 2018

@author: danny
"""

import numpy as np
import os

import glob

meta_data_loc = '/data/places_corpus/placesaudio_distro_part_1/metadata/'

img_path = os.path.join('/data/places_corpus/places_images')

file = open(os.path.join(meta_data_loc, 'utt2image'))

imgs =file.readlines()

imgs= [os.path.join(img_path, x.split()[1][1:]) for x in imgs]

x = glob.glob(img_path + '/*/*/*/*.jpg')
y = glob.glob(img_path + '/*/*/*.jpg')
places_data = x + y 

# check if all files in the metadata are actually in the places database
union = set(places_data) & set(imgs)
print(len(union) == len(imgs))

disjunct = set(places_data) - set(imgs)

# remove places images for which there is no caption to save disk space
for x in list(disjunct):
    os.remove(x)
