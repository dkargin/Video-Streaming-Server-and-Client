from struct import pack, unpack

__author__ = 'Tibbers'


"""
References:

- SDP: Session Description Protocol
https://tools.ietf.org/html/rfc4566

https://github.com/timohoeting/python-mjpeg-over-rtsp-client/blob/master/rfc2435jpeg.py
"""

# Hardcoded SDP for our test stream
# I try to make it as minimal as possible for test purposes
mjpeg_sdp = """v=0
o=- 1272052389382023 1 IN IP4 0.0.0.0
s=Session streamed by "nessyMediaServer"
i=jpeg
t=0 0
a=tool:Tiny python RTSP server
a=type:broadcast
a=control:*
a=range:npt=0-
a=x-qt-text-nam:Session streamed by "nessyMediaServer"
a=x-qt-text-inf:jpeg
m=video 0 RTP/AVP 26
c=IN IP4 0.0.0.0
a=cliprect:0,0,720,1280
a=framerate:25.000000
a=rtpmap:0 PCMU/8000/1"""

# Refactored SDP header. Used for python formatting
mjpeg_sdp_format = """v=0
o=- 1272052389382023 1 IN IP4 0.0.0.0
s=%s
i=jpeg
t=0 0
a=tool:%s
a=type:broadcast
a=control:*
a=recvonly
a=x-qt-text-nam:%s
a=x-qt-text-inf:jpeg
m=video %d RTP/AVP 26
c=IN IP4 0.0.0.0
a=cliprect:0,0,%d,%d
a=framerate:%f"""


def make_sdp(video_opt):
    """
    Fill in SDP string, using specified video options
    :param video_opt: Table containing video options
    :return:string sdp
    """

    sname = video_opt.get('session_name', 'Anystream')
    server_name = video_opt.get('server_name', 'Python RTSP server')
    video_port = video_opt.get('video_port', 0)
    audio_port = video_opt.get('audio_port', 0)
    fps = video_opt.get('fps', 25.0)
    width = video_opt.get('width', 1280)
    height = video_opt.get('height', 720)

    return mjpeg_sdp_format % (sname, server_name, sname, video_port, height, width, float(fps))


def list2string(l):
    s = ''
    for c in l:
        s += chr(c)
    return s


def string2list(s):
    l = []
    for c in s:
        l.append(ord(c))
    return l


def bytearray2list(s):
    l = []
    for c in s:
        l.append(c)
    return l

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


class Jpeg:
    def __init__(self):
        self.Type = 0
        self.Q = 0
        self.offset = 0
        self.Width = 0
        self.Height = 0
        self.TypeSpecific = 0
        self.RM_Header = None

        self.QT_luma = []
        self.QT_chroma = []
        self.QT_MBZ = 0
        self.QT_Precision = 0
        self.QT_Length = 0

        # Offset to payload part
        self.payload_offset = 0
        # bytearray with jpeg header
        self.JpegHeader = bytearray()
        # bytearray with jpeg payload
        self.JpegPayload = bytearray()
        # bytearray with full packet
        self.JpegImage = bytearray()

    def parse_header(self, data_raw, start=0):
        HOffset = 0
        LOffset = 0
        # Straightforward parsing
        (self.TypeSpecific,
         HOffset,  # 3 byte offset
         LOffset,
         self.Type,
         self.Q,
         width,
         height) = unpack('!BBHBBBB', data_raw[start:start+8])
        self.offset = (HOffset << 16) + LOffset
        self.Width = width << 3
        self.Height = height << 3

        # if self.offset == 0:
        #    print("Found start of jpeg")

        if self.offset > (1 << 24):
            return False

        # Expecting to find a video with size=(384x288) -> (48x36)
        if self.Width != 384 and self.Height != 288:
            return False
        # Check if we have Restart Marker header
        if 64 <= self.Type <= 127:
            # TODO: make use of that header
            self.RM_Header = data_raw[start + 8:start + 12]
            rm_i = 4  # Make offset for JPEG Header
        else:
            rm_i = 0

        # Check if we have Quantinization Tables embedded into JPEG Header
        # Only the first fragment will have it
        if self.Q > 127 and not self.JpegPayload:
            self.payload_offset = start + rm_i + 8 + 132
            QT_Header = data_raw[start + rm_i + 8:start + rm_i + 140]
            (self.QT_MBZ,
             self.QT_Precision,
             self.QT_Length) = unpack('!BBH', QT_Header[:4])

            # No luma or chroma are supported right here
            self.QT_luma = bytearray2list(QT_Header[4:68])
            self.QT_chroma = bytearray2list(QT_Header[68:132])
        else:
            self.payload_offset = start + rm_i + 8
        # Clear tables. Q might be dynamic.
        if self.Q <= 127:
            self.QT_luma = []
            self.QT_chroma = []

        return True

    def parse(self, data_raw, start=0):
        if self.parse_header(data_raw, start):
            self.JpegPayload += data_raw[self.payload_offset:]
            return True
        return False

    def makeJpeg(self):
        lqt = []
        cqt = []
        dri = 0
        # Use exsisting tables or generate ours
        if self.QT_luma:
            lqt=self.QT_luma
            cqt=self.QT_chroma
        else:
            MakeTables(self.Q,lqt,cqt)
        JPEGHdr = []
        # Make a complete JPEG header
        MakeHeaders(JPEGHdr, self.Type, int(self.Width), int(self.Height), lqt, cqt, dri)
        self.JpegHeader = list2string(JPEGHdr)
        # And a complete JPEG image
        return self.JpegHeader + self.JpegPayload
        #self.JpegPayload = ''
        #self.JpegHeader = ''
        #self.Datagram = ''
