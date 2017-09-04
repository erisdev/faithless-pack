import json
import numpy
import os
import png

from array import array
from pathlib import Path
from random import choice, randrange

def isindexed(info):
    return info['bitdepth'] == 8 and info['planes'] == 1 and 'palette' in info

def chunked(iterable, chunk_size):
    return zip(*([iter(iterable)] * chunk_size))

def palette_from_pixels(data, info):
    planes = info['planes']
    return set(color for row in data for color in chunked(row, info['planes']))

def load_palette(filename):
    with open(filename, 'rb') as file:
        reader = png.Reader(file)
        w, h, data, info = reader.read()
        if isindexed(info):
            return info['palette']
        else:
            return list(palette_from_pixels(data, info))

def load_tile(filename):
    with open(filename, 'rb') as file:
        reader = png.Reader(file)
        w, h, data, info = reader.read()
        if isindexed(info):
            return numpy.vstack(map(numpy.uint8, data))
        else:
            data = list(data)
            palette = {color:idx for idx, color in enumerate(palette_from_pixels(data, info))}
            return numpy.vstack(numpy.uint8([palette[color] for color in chunked(row, info['planes'])]) for row in data)


def blit(dst, dx, dy, src, sx, sy, w, h):
    dst[dy:dy+h, dx:dx+w] = src[sy:sy+h, sx:sx+w]

def isopaque(color):
    return color[3] != 0

def glitch(filename, tile_list):
    nframes = randrange(1, 5)
    bedrock = numpy.ndarray((16 * nframes, 16), numpy.uint8)
    frames = []
    for idx in range(nframes):
        frames.append({
            'index': idx,
            'time':randrange(16, 64)
        })
        y0 = idx * 16
        for dx, dy in ((0,0), (0,8), (8,0), (8,8)):
            tile = load_tile(choice(tile_list))
            sx = randrange(0, tile.shape[1], 8)
            sy = randrange(0, tile.shape[0], 8)
            blit(bedrock, dx, y0 + dy, tile, sx, sy, 8, 8)

    maxcolor = bedrock.max()
    palette = []
    while len(palette) <= maxcolor:
        palette.extend(filter(isopaque, load_palette(choice(tile_list))))
    if len(palette) > 255:
        del palette[256:]

    with open(filename, 'wb') as file:
        h, w = bedrock.shape
        writer = png.Writer(w, h, palette=palette)
        writer.write(file, bedrock)
    with open(Path(filename).with_suffix('.png.mcmeta'), 'w') as file:
        json.dump({
            'animation': {
                'frames': frames
            }
        }, file)
