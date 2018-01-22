from JpegFile import JPEGFile
import argparse

parser = argparse.ArgumentParser(description='Test JPEG loader')
parser.add_argument('file', metavar='N', help='jpeg file to load')

args = parser.parse_args()

print("Opening file %s" % args.file)

file = open(args.file, 'rb')
raw_data = file.read()
file.close()

if raw_data is None:
    print("Cannot read the file %s")

print("Loaded %d bytes" % len(raw_data))

image = JPEGFile()

image.load_data(raw_data)

print("Done")