from JpegFile import JpegFile, ReferenceJpeg, HuffmanCachedTable
import argparse
import logging
import sys
from PIL import Image

"""
Testing here Jpeg file loader
"""
parser = argparse.ArgumentParser(description='Test JPEG loader')
parser.add_argument('file', metavar='N', help='jpeg file to load')

args = parser.parse_args()

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
print("Opening file %s" % args.file)

file = open(args.file, 'rb')
raw_data = file.read()
file.close()

if raw_data is None:
    print("Cannot read the file %s")

print("Loaded %d bytes" % len(raw_data))

jfile = JpegFile()
jfile.load_data(raw_data)


def compare_huffman(a, b):
    """
    Compare two huffman tables
    :param a:HuffmanCachedTable
    :param b:HuffmanCachedTable
    :return:
    """
    pass
#
print("Testing reference loader")
ref_image = ReferenceJpeg(raw_data)

print("Source htables:")
for key, table in jfile.htables.items():
    print("-id%3d %s" % (key, table))

print("Result htables:")
for key, table in ref_image.htables.items():
    print("-id%3d %s" % (key, table))

print("Source components:")
for comp in jfile.components:
    print(" - dst=%d id=%d h=%d v=%d" % (comp.destination, comp.identifier, comp.h, comp.v))
print("Result components:")
for comp in ref_image.components:
    print(" - dst=%d id=%d h=%d v=%d" % (comp.destination, comp.identifier, comp.h, comp.v))

print("Source qtables")
for key, table in jfile.qtables.items():
    print(" - id= %d val=%s" % (key, list(table)))
print("Result qtables")
for key, table in ref_image.qtables.items():
    print(" - id= %d val=%s" % (key, list(table)))
# Should compare huffman tables from both
print("Testing partial decompression")
pixels = jfile.decompress()

pil_image = Image.frombytes('RGB', (jfile.width, jfile.height), bytes(pixels))
pil_image.show("Result")

ref_image.decompress()
print("Done")
