from VideoStream import Jpeg

path = "video3.mjpeg"

file = open(path, 'rb')
#stream = VideoStream(file)
data_raw = file.read()    # Get the framelength from the first 5 bytes
file.close()

jpeg = Jpeg()

chunks = []
pos = 0
while pos < len(data_raw):
    len_raw = data_raw[pos:pos+5].decode()
    pos += 5
    chunk_len = int(len_raw)
    print("Obtained block len=%d" % chunk_len)
    chunks.append((pos, chunk_len))
    pos += chunk_len

if pos != len(data_raw):
    print("Got extra %d bytes at tail" % (pos-len(data_raw)))
print("Got %d chunks from the file. Chunks=%s" % (len(chunks), str(chunks)))
good_frame_positions = []
# try:
for i in range(0, len(data_raw)):
    if jpeg.parse_header(data_raw, i) and jpeg.Type == 255:
        print("Found JPEG with offset=%d. Q=%d T=%d TS=%d Offset=%d" % (i, jpeg.Q, jpeg.Type, jpeg.TypeSpecific, jpeg.offset))
        good_frame_positions.append(i)

#print("Obtained JPEG frame size=%dx%d" % (test_jpeg.Width, test_jpeg.Height))

print("Processing is done. Frames=%s" % str(good_frame_positions))
