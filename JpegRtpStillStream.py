from struct import pack_into, unpack_from, pack, pack_into
from sdp_utils import make_sdp2
from RtpFrameGenerator import RtpPacket, RtpFrameGenerator
from time import time

from JpegFile import JpegFile, serialize_scanlines
import logging

logger = logging.getLogger(__name__)

RTP_JPEG_RESTART = 0x40
RTP_PT_JPEG = 26
JPG_HDR_SIZE = 8  # Number of bytes for RTP-JPG header
DRI_SIZE = 4  # Number of bytes for DRI

"""
TODO: Check huffman table inside jpeg. We need to repack it
if it differs from the default one
"""


class RtpJpegEncoder(RtpFrameGenerator):
    """
    Encodes Jpeg file to RTP packets
    """
    def __init__(self):
        super(RtpJpegEncoder, self).__init__()
        self.jpeg_TypeSpecific = 0
        self.jpeg_Q = 255
        self.jpeg_QT_MBZ = 0
        self.jpeg_QT_Precision = 0
        self.seq = 0
        self.timestamp_start = time()

    def get_timestamp_90khz(self, stamp=None):
        step = 1.0 / 90000.0
        if stamp is None:
            stamp = time()
        delta = int((stamp - self.timestamp_start)*90000)
        return delta

    def _create_rtp_packet(self):
        """
        Constructs RTP packet. It should be filled later
        :return:
        """
        ssrc = 0
        return RtpPacket(payload_type=RTP_PT_JPEG, ssrc=ssrc)

    def calc_payload_size(self, jpeg, jpeg_offset, frame_length):
        result = 8  # For RTP Jpeg header
        if jpeg.dri:
            result += 4

        # Some space for QT
        if self.jpeg_Q > 127 and jpeg_offset == 0:
            result += 132

        # And some scanline data to the end
        result += frame_length
        return result

    # Makes another RTP frame
    def make_rtp_frame_payload(self, jpeg, jpeg_offset, frame_length):
        """
        :param jpeg:JpegFile
        :param jpeg_offset:int
        :param frame_length:int
        :return:bytes RTP mjpeg payload
        """
        offset = 0
        hoffset = (jpeg_offset >> 16) & 0xff
        loffset = jpeg_offset & 0xffff

        if jpeg.width % 8 != 0 or jpeg.height % 8 != 0:
            logger.error("Jpeg image size should be divisible by 8: %dx%d"%(jpeg.width, jpeg.height))

        output = bytearray()
        width_packed = jpeg.width >> 3
        height_packed = jpeg.height >> 3
        header = pack('!BBHBBBB',
                      self.jpeg_TypeSpecific,
                      hoffset, loffset, jpeg.type, self.jpeg_Q,
                      width_packed, height_packed)

        output += header
        offset += len(header)

        if len(output) != offset:
            raise RuntimeError("Miscalculated offset vs output: %d vs %d" % (offset, len(output)))

        if jpeg.reset_interval:
            l = 1
            h = 1
            flags = l & 0x1
            flags |= (h << 1) & 0x2
            flags |= (0x3fff << 2)
            dri = pack('!HH', jpeg.reset_interval, flags)
            output += dri
            offset += 4

        if len(output) != offset:
            raise RuntimeError("Miscalculated offset vs output: %d vs %d" % (offset, len(output)))

        if self.jpeg_Q > 127 and jpeg_offset == 0:
            # Write table
            # Write luma x64
            # Write chroma x64
            qt = bytearray(132)
            qt_length = 128
            pack_into('!BBH', qt, 0, self.jpeg_QT_MBZ, self.jpeg_QT_Precision, qt_length)
            jpeg.write_luma(qt, 4)
            jpeg.write_chroma(qt, 68)
            output += qt
            offset += 132

        if len(output) != offset:
            raise RuntimeError("Miscalculated offset vs output: %d vs %d" % (offset, len(output)))

        # TODO: Should crimp it
        max_jpeg_len = len(jpeg.image_data)
        next_jpeg_pos = min(max_jpeg_len, jpeg_offset+(frame_length-offset))
        output += jpeg.image_data[jpeg_offset:next_jpeg_pos]

        jpeg_offset = next_jpeg_pos
        return output, jpeg_offset

    # Encode to RTP payload stream
    def encode_rtp(self, timestamp, jpeg, max_datagram_size):
        """
        :param timestamp:Time
        :param jpeg:JpegFile parsed Jpeg object
        :param max_datagram_size:
        :return:
        """
        jpeg_offset = 0
        total_length = len(jpeg.image_data)
        result = []
        done = jpeg_offset >= total_length
        first = True

        while not done:
            packet = self._create_rtp_packet()
            packet.seqnum = self.seq
            packet.timestamp = self.get_timestamp_90khz(timestamp)

            frame_length = min(max_datagram_size, total_length-jpeg_offset)
            data, jpeg_offset = self.make_rtp_frame_payload(jpeg, jpeg_offset, max_datagram_size)
            done = jpeg_offset >= total_length

            if done:
                packet.marker = 1

            # TODO: hide it inside RtpPacket
            # We should implement copyless jpeg serialization as well
            header_size = packet.calc_header_size()
            packet.raw_packet = bytearray(header_size + len(data))
            packet.encode_header(packet.raw_packet, 0)
            packet.raw_packet[header_size:] = data

            self.seq += 1
            result.append(packet)

        return result

    def get_sdp(self, options):
        return make_sdp2(options)


class RtpJpegFileStream(RtpJpegEncoder):
    """
    RTP Stream that sends a single jpeg frame
    """
    def __init__(self, path, packet_size=1000):
        """
        :param path:string path to jpeg file
        :param packet_size:int desired RTP packet size
        """
        super(RtpJpegFileStream, self).__init__()
        self._jpeg = JpegFile()
        self._path = path
        # Encoded RTP frames
        self._frames = []
        self._packet_size = packet_size
        self._generator = None
        self.read_data()

    def get_sdp(self, options):
        options['width'] = self._jpeg.width
        options['height'] = self._jpeg.height
        return super(RtpJpegFileStream, self).get_sdp(options)

    def read_data(self):
        file = open(self._path, 'rb')
        raw_data = file.read()
        file.close()

        if raw_data is None:
            raise IOError("Failed to open the file %s" % self._path)
        #logger.debug("Loaded %d bytes" % len(raw_data))
        self._jpeg.load_data(raw_data)
        timestamp = time()
        self._frames = self.encode_rtp(timestamp, self._jpeg, self._packet_size)

    def restart_generator(self):
        def frame_generator():
            timestamp = time()
            frames = self.encode_rtp(timestamp, self._jpeg, self._packet_size)

            for frame in frames:
                yield frame

        if self._generator is None:
            self._generator = frame_generator()

    def next_packet(self):
        if self._generator is None:
            self.restart_generator()

        while True:
            try:
                frame = next(self._generator)
                return frame
            except StopIteration:
                self._generator = None
                self.restart_generator()
        return None

