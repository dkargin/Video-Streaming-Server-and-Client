from time import time
__author__ = 'Tibbers'
import sys
# from VideoStream import VideoStream
import VideoStream


class RtpPacket:
    HEADER_SIZE = 12
    """
    RTP Packet
    Does serialization/deserialization stuff
    """

    def __init__(self):
        self.header_raw = bytearray(self.HEADER_SIZE)
        self.version = 2
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

    def encode(self, version, padding, extension, cc, seqnum, marker, pt, ssrc, payload):
        """Encode the RTP packet with header fields and payload."""

        timestamp = int(time())
        #--------------
        # TO COMPLETE
        #--------------
        # Fill the header bytearray with RTP header fields

        #RTP-version filed(V), must set to 2
        #padding(P),extension(X),number of contributing sources(CC) and marker(M) fields all set to zero in this lab

        #Because we have no other contributing sources(field CC == 0),the CSRC-field does not exist
        #Thus the length of the packet header is therefore 12 bytes
        #Above all done in RtspServer.py

        # Reusing existing header
        header = self.header_raw
        header = bytearray(self.HEADER_SIZE)
        # header[0] = version + padding + extension + cc + seqnum + marker + pt + ssrc
        header[0] = version << 6
        header[0] = self.header[0] | padding << 5
        header[0] = self.header[0] | extension << 4
        header[0] = self.header[0] | cc
        header[1] = marker << 7
        header[1] = self.header[1] | pt

        header[2] = (seqnum >> 8) & 0xFF
        header[3] = (seqnum ) & 0xFF

        header[4] = (timestamp >> 24) & 0xFF
        header[5] = (timestamp >> 16) & 0xFF
        header[6] = (timestamp >> 8) & 0xFF
        header[7] = timestamp & 0xFF

        header[8] = (ssrc >> 24 ) & 0xFF
        header[9] = (ssrc >> 16 ) & 0xFF
        header[10] = (ssrc >> 8) & 0xFF
        header[11] = (ssrc) & 0xFF

        # Get the payload from the argument
        self.payload = payload
        return header, payload

    def decode(self, byteStream):
        """Decode the RTP packet."""
        # Copy data into our header
        self.header_raw[:] = byteStream[:self.HEADER_SIZE]
        header = self.header_raw
        payload = byteStream[self.HEADER_SIZE:]
        self.version = int(header[0] >> 6)
        # header[2] shift left for 8 bits then does bit or with header[3]
        self.seqnum = int(header[2] << 8 | header[3])
        self.timestamp = int(header[4] << 24 | header[5] << 16 | header[6] << 8 | header[7])
        self.pt = header[1] & 127

    def getPayload(self):
        """Return payload."""
        return self.payload

    def getPacket(self):
        """Return RTP packet."""
        return self.header_raw + self.payload