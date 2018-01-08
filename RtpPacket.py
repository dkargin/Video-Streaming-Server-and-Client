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

    def __init__(self):
        self._header_raw = bytearray(self.HEADER_SIZE)
        self._version = 2
        self.padding = 0
        self.extension = 0
        self.cc = 0
        self.marker = 0
        # Payload type
        self.pt = 26  # MJPEG type
        # Frame number
        self.seqnum = 0
        self.ssrc = 0
        self.payload = None

    def encode(self, timestamp, payload):
        """
        Encode the RTP packet with header fields and payload.
        :param timestamp: Timestamp for specified payload
        :param payload: bytearray Actual frame data.
        """

        """
        #RTP-version filed(V), must set to 2
        #padding(P),extension(X),number of contributing sources(CC) and marker(M) fields all set to zero in this lab

        #Because we have no other contributing sources(field CC == 0),the CSRC-field does not exist
        #Thus the length of the packet header is therefore 12 bytes
        """

        # Reusing existing header
        header = self._header_raw
        header = bytearray(self.HEADER_SIZE)
        # header[0] = version + padding + extension + cc + seqnum + marker + pt + ssrc
        header[0] = self._version << 6
        header[0] |= self.padding << 5
        header[0] |= self.extension << 4
        header[0] |= self.cc
        header[1] = self.marker << 7
        header[1] = header[1] | self.pt

        header[2] = (self.seqnum >> 8) & 0xFF
        header[3] = self.seqnum & 0xFF

        header[4] = (timestamp >> 24) & 0xFF
        header[5] = (timestamp >> 16) & 0xFF
        header[6] = (timestamp >> 8) & 0xFF
        header[7] = timestamp & 0xFF

        header[8] = (self.ssrc >> 24) & 0xFF
        header[9] = (self.ssrc >> 16) & 0xFF
        header[10] = (self.ssrc >> 8) & 0xFF
        header[11] = self.ssrc & 0xFF

        # Get the payload from the argument
        self.payload = payload
        return header, payload

    def decode(self, data_raw):
        """Decode the RTP packet."""
        # Copy data into our header
        if len(data_raw) <= self.HEADER_SIZE:
            print("Data chunk is too short to fit a header. Got only %d bytes" % len(data_raw))
            return False
        self._header_raw[:] = data_raw[:self.HEADER_SIZE]
        header = self._header_raw
        payload = data_raw[self.HEADER_SIZE:]
        self._version = int(header[0] >> 6)
        # header[2] shift left for 8 bits then does bit or with header[3]
        self.seqnum = int(header[2] << 8 | header[3])
        self.timestamp = int(header[4] << 24 | header[5] << 16 | header[6] << 8 | header[7])
        self.pt = header[1] & 127
        return True

    def getPayload(self):
        """Return payload."""
        return self.payload

    def getPacket(self):
        """Return RTP packet."""
        return self._header_raw + self.payload