"""

References:

- RTP Payload Format for JPEG-compressed Video
https://tools.ietf.org/html/rfc2435

- RTP Profile for Audio and Video Conferences with Minimal Control
https://tools.ietf.org/html/rfc3551

I try to folow it as far as I can
"""


class RtpPacket:
    HEADER_SIZE = 12
    """
    RTP Packet

    Does serialization/deserialization stuff
    """
    def __init__(self, **kwargs):
        # Contains raw header data
        self._header_raw = bytearray(self.HEADER_SIZE)
        # RTP version
        self._version = 2
        # RTP padding
        self.padding = 0
        self.extension = 0
        self.cc = 0
        # End-marker bit
        self.marker = 0
        self.timestamp = 0
        # Payload type
        self.pt = kwargs.get('payload_type', 26)   # Defaulting to MJPEG type
        # Frame number
        self.seqnum = 0
        self.ssrc = kwargs.get('ssrc', 0)
        # Frame payload. Should we keep it here?
        self.payload = None
        # Serialized RTP frame data
        self.raw_packet = None

    # Calculate size for current header
    def calc_header_size(self):
        return self.HEADER_SIZE if self.extension==0 else self.HEADER_SIZE + 4

    def encode_header(self, data_raw, offset=0):
        """
        Encode the RTP header fields
        :param data_raw:bytearray buffer to be written
        :param offset:int offset to start of the header
        """
        """
        #RTP-version filed(V), must set to 2
        #padding(P),extension(X),number of contributing sources(CC) and marker(M) fields all set to zero in this lab

        #Because we have no other contributing sources(field CC == 0),the CSRC-field does not exist
        #Thus the length of the packet header is therefore 12 bytes
        """
        # Reusing existing header
        header0 = self._version << 6
        header0 |= self.padding << 5
        header0 |= self.extension << 4
        header0 |= self.cc

        data_raw[offset+0] = header0
        data_raw[offset+1] = ((self.marker&0x1) << 7) | (self.pt & 0x7f)
        data_raw[offset+2] = (self.seqnum >> 8) & 0xFF
        data_raw[offset+3] = self.seqnum & 0xFF

        data_raw[offset+4] = (self.timestamp >> 24) & 0xFF
        data_raw[offset+5] = (self.timestamp >> 16) & 0xFF
        data_raw[offset+6] = (self.timestamp >> 8) & 0xFF
        data_raw[offset+7] = self.timestamp & 0xFF

        data_raw[offset+8] = (self.ssrc >> 24) & 0xFF
        data_raw[offset+9] = (self.ssrc >> 16) & 0xFF
        data_raw[offset+10] = (self.ssrc >> 8) & 0xFF
        data_raw[offset+11] = self.ssrc & 0xFF
        # Get the payload from the argument

    """
    # RTP Parsing example
    # The code was obtained from https://habrahabr.ru/post/117735/
    def parse(self):
        Ver_P_X_CC, M_PT, self.SequenceNumber, self.Timestamp, self.SyncSourceIdentifier = unpack('!BBHII', self.Datagram[:12])
        self.Version =      (Ver_P_X_CC & 0b11000000) >> 6
        self.Padding =      (Ver_P_X_CC & 0b00100000) >> 5
        self.Extension =    (Ver_P_X_CC & 0b00010000) >> 4
        self.CSRCCount =     Ver_P_X_CC & 0b00001111
        self.Marker =       (M_PT & 0b10000000) >> 7
        self.PayloadType =   M_PT & 0b01111111
        i = 0
        for i in range(0, self.CSRCCount, 4):
            self.CSRS.append(unpack('!I', self.Datagram[12+i:16+i]))
        if self.Extension:
            i = self.CSRCCount * 4
            (self.ExtensionHeaderID, self.ExtensionHeaderLength) = unpack('!HH', self.Datagram[12+i:16+i])
            self.ExtensionHeader = self.Datagram[16+i:16+i+self.ExtensionHeaderLength]
            i += 4 + self.ExtensionHeaderLength
        self.Payload = self.Datagram[12+i:]
    """
    def decode(self, data_raw, start=0, end=0):
        """
        Decode the RTP packet
        Copies incoming data into local fields and parses it
        """
        # Copy data into our header
        if len(data_raw) <= self.HEADER_SIZE:
            raise Exception("Data chunk is too short to fit a header. Got only %d bytes" % len(data_raw))

        self._header_raw[:] = data_raw[start:start + self.HEADER_SIZE]
        header = self._header_raw

        # Parse all the stuff
        self._version = int(header[0] >> 6)
        self.extension = (header[0] >> 5) & 0x1
        self.marker = (header[1] >> 7)
        """
        header[0] = self._version << 6
        header[0] |= self.padding << 5
        header[0] |= self.extension << 4
        header[0] |= self.cc
        header[1] = self.marker << 7
        header[1] |= self.pt
        """
        # Stripping payload part

        # header[2] shift left for 8 bits then does bit or with header[3]
        self.seqnum = int(header[2] << 8 | header[3])
        self.timestamp = int(header[4] << 24 | header[5] << 16 | header[6] << 8 | header[7])
        self.pt = header[1] & 127

        header_size = self.HEADER_SIZE
        if self.extension:
            header_size += 4

        if end == 0:
            end = len(data_raw)

        self.payload = data_raw[start + header_size:end]


class RtpFrameGenerator:
    """
    Generic generator of RTP frames
    """
    def __init__(self):
        pass

    def next_packet(self):
        """
        # Generate next RTP packet
        # Should return tuple (data, seq)
        :return:RtpPacket generated packet
        """
        raise NotImplemented()

    def get_sdp(self, options):
        """
        Generate SDP for this generator
        :return:string with SDP stream description
        """
        raise NotImplemented()
