from tornado.ioloop import PeriodicCallback
from RtpPacket import RtpPacket
import socket
from time import time


class RtpServer:
    """
    RTP Server
    """
    def __init__(self, address="0.0.0.0"):
        self._sockets = None
        self._address = address
        self._rtp_pub_ports = range(8888, 8889)
        # Frame provider
        self._stream = None
        # Frame generator
        self._frame_generator = PeriodicCallback(self._gen_rtp_frame, 40)
        # Maps from some key to (address,port) pairs
        self._destinations = {}
        self.init_sockets()

    def get_server_ports(self):
        return self._rtp_pub_ports

    def init_sockets(self):
        # TODO: check errors and raise
        sock_primary = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock_primary.bind((self._address, self._rtp_pub_ports.start))

        sock_secondary = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock_secondary.bind((self._address, self._rtp_pub_ports.stop))

        self._sockets = (sock_primary, sock_secondary)

    def set_stream(self, stream):
        self._stream = stream

    # Start RTP streaming
    def start(self):
        self._frame_generator.start()

    # Stop RTP streaming
    def stop(self):
        self._frame_generator.stop()

    def add_destination(self, key, dest):
        self._destinations[key] = dest

    def remove_destination(self, key, dest):
        if key in self._destinations:
            self._destinations.pop(key)

    # Returns a list of pairs (address, port)
    def _get_rtp_destinations(self):
        result = []

        # Add own addresses
        # if self._rtp_pub_ports is not None and self._local_address is not None:
        #    for port in self._rtp_pub_ports:
        #        result.append((self._local_address, port))

        for key, dest in self._destinations:
            result.append(dest)
        return result

    # Publish frame to all clients
    def _gen_rtp_frame(self):

        # I do not know what is inside. Maybe we should cover somehow this data format?
        # Supposing this is MJPEG frame. Will we decode it here to check its integrity?
        frame_data, frame_number = self._stream.nextFrame()

        if frame_data is None:
            return

        # Generate RTP packet
        packet = RtpPacket()
        packet.pt = 26
        packet.seqnum = frame_number
        packet.timestamp = int(time())
        data = packet.encode(frame_data)

        data_len = len(data)
        if data_len == 0:
            print("Empty data for some reason")
            return

        destinations = self._get_rtp_destinations()

        for address in destinations:
            sent_len = self._socket[0].sendto(data, address)
            if sent_len < 0:
                print("System error in sendto %s" % address)
            elif sent_len < data_len:
                print("Sent %d of %d to %s" % (sent_len, data_len, address))
        pass
