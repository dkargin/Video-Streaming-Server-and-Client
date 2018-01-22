from tornado.ioloop import PeriodicCallback
from RtpFrameGenerator import RtpPacket, RtpFrameGenerator
import socket
from time import time


class RtpServer:
    """
    RTP Server
    Deals with publishing rtp datagrams to clients
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
        self._sockets = None
        self.init_sockets()

    def init_sockets(self):
        try:
            sock_primary = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock_primary.bind((self._address, self._rtp_pub_ports.start))

            sock_secondary = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock_secondary.bind((self._address, self._rtp_pub_ports.stop))

            self._sockets = (sock_primary, sock_secondary)
            return True
        except OSError as e:
            return False

    def get_server_ports(self):
        return self._rtp_pub_ports

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

        for key, dest in self._destinations.items():
            result.append(dest)
        return result

    def close_sockets(self):
        for sock in self._sockets:
            sock.close()
        self._sockets = None

    def sockets_invalid(self):
        return self._sockets is not None

    def _publish_rtp_frame(self, data_raw):
        destinations = self._get_rtp_destinations()

        data_len = len(data_raw)

        if data_len == 0:
            return

        for address in destinations:
            try:
                sent_len = self._sockets[0].sendto(data_raw, address)
                if sent_len < 0:
                    print("System error in sendto %s" % address)
                elif sent_len < data_len:
                    print("Sent %d of %d to %s" % (sent_len, data_len, address))
            except OSError as e:
                # TODO: Switch to NetInit state
                print("OS Exception: %s" % str(e))
                self.close_sockets()

    def _restart_stream(self):
        pass

    # Publish frame to all clients
    def _gen_rtp_frame(self):
        if self.sockets_invalid():
            self.init_sockets()

        if self._stream is None or not isinstance(self._stream, RtpFrameGenerator):
            raise Exception("RtpServer has invalid RTP Frame generator")

        rtp_packet = self._stream.next_packet()
        if rtp_packet is None:
            raise Exception("RtpServer got invalid rtp packet")
            self._restart_stream()

        self._publish_rtp_frame(rtp_packet.raw_packet)
