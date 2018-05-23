from JpegStream import JpegFile
import argparse

"""
Testing here Jpeg file loader
"""


parser = argparse.ArgumentParser(description='Test JPEG loader')
parser.add_argument('file', metavar='N', help='jpeg file to load')

args = parser.parse_args()

import logging
import sys
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

print("Opening file %s" % args.file)

file = open(args.file, 'rb')
raw_data = file.read()
file.close()

if raw_data is None:
    print("Cannot read the file %s")

print("Loaded %d bytes" % len(raw_data))

image = JpegFile()

image.load_data(raw_data)

print("Done")
