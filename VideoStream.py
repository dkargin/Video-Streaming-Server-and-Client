from struct import pack, unpack

__author__ = 'Tibbers'


# Wraps file io
class VideoStream:
    def __init__(self, filename):

        if filename[0] == '/':
            filename = filename[1:]
        if filename[-1] == '/':
            filename = filename[:-1]

        self._filename = filename
        self._file = None
        self.frameNum = 0
        self.reopen()

    def reopen(self):
        if self._file is not None:
            self._file.close()
            self._file = None

        try:
            self._file = open(self._filename, 'rb')
            print('-' * 60 + "\nVideo file : |" + self._filename + "| read\n" + '-' * 60)
        except:
            print("read " + self._filename + " error")
            raise IOError
        self.frameNum = 0

    def get_sdp(self, server_opt):
        return make_sdp(server_opt)

    def nextFrame(self):
        """Get next frame."""

        data_in = self._file.read(5)    # Get the framelength from the first 5 bytes
        data_raw = bytearray(data_in)

        if data_raw and len(data_raw) == 5:
            data_int = (data_raw[0] - 48) * 10000 + (data_raw[1] - 48) * 1000 + (data_raw[2] - 48) * 100 + (data_raw[3] - 48) * 10 + (data_raw[4] - 48)# = #int(data.encode('hex'),16)
            final_data_int = data_int

            framelength = final_data_int
            # Read the current frame
            frame = self._file.read(framelength)
            if len(frame) != framelength:
                raise ValueError('incomplete frame data')
            #if not (data.startswith(b'\xff\xd8') and data.endswith(b'\xff\xd9')):
            #	raise ValueError('invalid jpeg')
            self.frameNum += 1
            #print('-'*10 + "\nNext Frame (#" + str(self.frameNum) + ") length:" + str(framelength) + "\n" + '-'*10)

            return frame, self.frameNum
        else:
            print("Got wrong number of bytes. Is it EOF?")
            frameNum = self.frameNum
            self.reopen()
            return None, frameNum

    def frameNbr(self):
        """Get frame number."""
        return self.frameNum
