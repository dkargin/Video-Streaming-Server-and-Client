from random import randint
import socket
import re

from VideoStream import VideoStream
from RtpPacket import RtpPacket

from HttpMessage import HttpMessage

from tornado.tcpserver import TCPServer
from tornado.iostream import StreamClosedError
from tornado import gen
from tornado.ioloop import PeriodicCallback

__author__ = 'Tibbers'

RTP_UDP_PORT = 9500

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


#a=control:*

def make_sdp(video_opt):
    return mjpeg_sdp


# Contains protocol-specific constants
class Protocol:
    SETUP = 'SETUP'
    OPTIONS = 'OPTIONS'
    DESCRIBE = 'DESCRIBE'
    PLAY = 'PLAY'
    PAUSE = 'PAUSE'
    TEARDOWN = 'TEARDOWN'


# RTSP Status codes from rfc-2326
StatusCodes = {
    100: 'Continue',
    200: 'OK',
    201: 'Created',
    250: 'Low on Storage Space',
    300: 'Multiple Choices',
    301: 'Moved Permanently',
    302: 'Moved Temporarily',
    303: 'See Other',
    304: 'Not Modified',
    305: 'Use Proxy',
    400: 'Bad Request',
    401: 'Unauthorized',
    402: 'Payment Required',
    403: 'Forbidden',
    404: 'Not Found',
    405: 'Method Not Allowed',
    406: 'Not Acceptable',
    407: 'Proxy Authentication Required',
    408: 'Request Time - out',
    410: 'Gone',
    411: 'Length Required',
    412: 'Precondition Failed',
    413: 'Request Entity Too Large',
    414: 'Request - URI Too Large',
    415: 'Unsupported Media Type',
    451: 'Parameter Not Understood',
    452: 'Conference Not Found',
    453: 'Not Enough Bandwidth',
    454: 'Session Not Found',
    455: 'Method Not Valid in This State',
    456: 'Header Field Not Valid for Resource',
    457: 'Invalid Range',
    458: 'Parameter Is Read - Only',
    459: 'Aggregate operation not allowed',
    460: 'Only aggregate operation allowed',
    461: 'Unsupported transport',
    462: 'Destination unreachable',
    500: 'Internal Server Error',
    501: 'Not Implemented',
    502: 'Bad Gateway',
    503: 'Service Unavailable',
    504: 'Gateway Time - out',
    505: 'RTSP Version not supported',
    551: 'Option not supported'
}


class ClientInfo:
    def __init__(self, address):
        # Port range to receive RTP data
        self.rtp_ports = None
        self.address = address
        self.state = None
        self.last_command = None
        self.unicast = False
        self.rtp = False

    def set_rtp_ports(self, start, end):
        self.rtp_ports = range(start, end)

    def parse_transport_options(self, transport):
        # Transport example: 'RTP/AVP;unicast;client_port=9500-9501'
        transport_items = transport.split(';')

        for item in transport_items:
            if item == 'unicast':
                self.unicast = True
            elif item.lower() == 'rtp/avp':
                self.rtp = True
            elif item.startswith('client_port='):
                # Regexp to match port range
                port_re = re.compile("([0-9]+)-([0-9]+)$")
                result = port_re.search(item)
                if result is not None:
                    port_start = result.group(1)
                    port_end = result.group(2)
                    self.set_rtp_ports(int(port_start), int(port_end))
                else:
                    print("Unrecognized client port")
                    self.rtp_ports = None


# Implements RTSP protocol FSM
class ServerWorker(TCPServer):
    INIT = 0
    READY = 1
    PLAYING = 2
    PAUSE = 3

    OK_200 = 200
    FILE_NOT_FOUND_404 = 404
    CON_ERR_500 = 500

    # RTSP response
    class CmdRTSPResponse:
        def __init__(self, status, seq, data=None, **kwargs):
            self.code = status
            self.seq = seq
            self.values = kwargs
            self.data = data

    # Command to create a new client
    class CmdInitClient:
        pass

    # Command to open RTP port
    class CmdOpenRTP:
        def __init__(self):
            pass

    # Command to close RTP port
    class CmdCloseRTP:
        def __init__(self):
            pass

    def __init__(self):
        super(ServerWorker, self).__init__()

        # Maps address->client
        self.clients = {}
        self.video_opt = {}
        self._rtp_socket = None
        self._rtp_pub_ports = range(8888, 8889)
        self._local_address = '127.0.0.1'
        self._client_address = None
        self._work_thread = None
        self._state = ServerWorker.INIT
        # Frame provider
        self._stream = None
        # Generate a randomized RTSP session ID
        self._session = randint(100000, 999999)
        print("Starting session id=%d" % self._session)

        # Frame generator
        self._frame_generator = PeriodicCallback(self._gen_rtp_frame, 40)

    def _get_client(self, address):
        return self.clients.get(address)

    @gen.coroutine
    def handle_stream(self, stream, address):
        """
        Receive RTSP request from the client.
        """
        while True:
            try:
                request_raw = yield stream.read_until(b'\r\n\r\n')
                #request_raw = sock.recv(256)
                if request_raw is None or len(request_raw) == 0:
                    print("Should close a socket for some reason")
                    break

                yield from self._handle_raw_request(stream, request_raw, address)

            except StreamClosedError:
                print("Stream from %s has been closed" % str(address))
                break

    def _handle_raw_request(self, stream, request_raw, address):
        responses = 0

        # Gather commands from RTSP protocol processor
        generator = self._process_rtsp_request(request_raw.decode("utf-8"), address)

        out = None

        while True:
            try:
                if out is None:
                    cmd = next(generator)
                else:
                    cmd = generator.send(out)
                    out = None

                if isinstance(cmd, self.CmdRTSPResponse):  # Generated http response
                    response_data = self.send_reply_rtsp(cmd)
                    print("Responding=%s" % response_data)
                    yield stream.write(response_data.encode())
                    responses += 1

                elif isinstance(cmd, self.CmdOpenRTP):  # Should open UDP port for streaming
                    if self._rtp_socket is None:
                        # Create a new thread and start sending RTP packets
                        self._rtp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                        self._frame_generator.start()
                elif isinstance(cmd, self.CmdCloseRTP):  # Should close UDP port
                    if self._rtp_socket is not None:
                        self._frame_generator.stop()
                        # Close the RTP socket
                        # Should do some reference counting before such rude disconnect
                        self._rtp_socket.close()
                        self._rtp_socket = None
                elif isinstance(cmd, self.CmdInitClient):
                    if address not in self.clients:
                        print("Creating ClientInfo for %s" % str(address))
                        client = ClientInfo(address)
                        self.clients[address] = ClientInfo(address)
                        out = client # Will send it back to coroutine
                    else:
                        print("Picking existing ClientInfo for %s" % str(address))
                        out = self._get_client()

            except StopIteration:
                break

        if responses != 1:
            # TODO: Just send a default response here
            raise ("RTSP FSM is broken. Have generated %d responses instead of single one!" % responses)

    # RTSP method handlers

    def _response_options(self, request, client):
        """
        Process OPTIONS request
        :param request:HttpMessage
        """
        yield self.CmdRTSPResponse(self.OK_200, request.seq, Public="DESCRIBE, SETUP, TEARDOWN, PLAY, PAUSE")

    def _response_describe(self, request, client):
        """
        Process DESCRIBE request
        :param request:HttpMessage
        """
        # Get the media file name
        filename = request.url_raw
        sdp = make_sdp(self.video_opt)
        values = {
            'x-Accept-Dynamic-Rate': 1,
            'Content-Base': filename,
            'Content-Type': 'application/sdp'
        }
        yield self.CmdRTSPResponse(self.OK_200, request.seq, sdp, **values)

    def _response_setup(self, request, client):
        """
        Process SETUP request
        :param request:HttpMessage
        """
        # Get the media file name
        url = request.url
        seq = request.seq

        if client is None:
            # Creating new client
            client = yield self.CmdInitClient()

        # Update state
        print("SETUP Request received for %s\n" % url.path)
        if self._state == self.INIT:
            try:
                print("Initializing stream")
                self._stream = VideoStream(url.path)
                self._state = self.READY

            except IOError:
                yield self.CmdRTSPResponse(self.FILE_NOT_FOUND_404, seq)
                return

        # Send RTSP reply
        # Get the RTP/UDP port from the last line
        transport = request.get('transport')

        if transport is None:
            yield self.CmdRTSPResponse(self.FILE_NOT_FOUND_404, seq)
            return

        client.parse_transport_options(transport)

        values = {
            'Session': self._session,
            'Transport': request.get('transport', 'RTP/AVP;unicast')
        }
        yield self.CmdRTSPResponse(self.OK_200, seq, **values)  # seq[0] the sequenceNum received from Client.py

    def _response_play(self, request, client):
        """
        Process PLAY request
        :param request:HttpMessage
        """
        if self._state == self.READY:
            print("READY->PLAYING")
            self._state = self.PLAYING
            yield self.CmdRTSPResponse(self.OK_200, request.seq)
            # Create a new socket for RTP/UDP
            yield self.CmdOpenRTP()
            return
        # Process RESUME request
        elif self._state == self.PAUSE:
            print("PAUSE->PLAYING")
            self._state = self.PLAYING
            yield self.CmdRTSPResponse(self.OK_200, request.seq)
            return
        else:
            raise "Should handle this. Was at state=%d" % self._state

    def _response_pause(self, request, client):
        """
        Process PAUSE request
        :param request:HttpMessage
        """
        if self._state == self.PLAYING:
            print('PLAYING->READY')
            #print('-' * 60 + "\nPAUSE Request Received\n" + '-' * 60)
            #self._state = self.READY
            yield self.CmdRTSPResponse(self.OK_200, request.seq)
        else:
            raise "Should handle this at state %d" % self._state

    def _response_teardown(self, request, client):
        """
        Process TEARDOWN request
        :param request:HttpMessage
        """
        yield self.CmdRTSPResponse(self.OK_200, request.seq)
        yield self.CmdCloseRTP()

    def _process_rtsp_request(self, raw_data, address):
        """
        Coroutine that process RTSP protocol sequence
        @:rtype: tuple with HTTP status and data
        """
        print('-'*60)
        request = HttpMessage()
        if not request.deserialize(raw_data):
            print("Corrupted RTSP request")
            # TODO: Should we return something meaningful?
            return

        client = self._get_client(address)
        handler = self._dispatch_table.get(request.type)

        if handler is not None:
            yield from handler(self, request, client)
        else:
            print("Unhandled RTSP method %s!!!" % str(request.type))
            yield self.CmdRTSPResponse(self.FILE_NOT_FOUND_404, request.seq)

    def _gen_rtp_frame(self):
        data = self._stream.nextFrame()

        if data is None:
            return

        frameNumber = self._stream.frameNbr()

        self.publish_rtp_frame(data, frameNumber)

    # Returns a list of pairs (address, port)
    def _get_rtp_destinations(self):
        result = []
        for key, client in self.clients.items():
            if client.rtp_ports is not None:
                result.append((client.address, client.rtp_ports[0]))
        return result

    # Publish frame to all clients
    def publish_rtp_frame(self, frame, frameNumber):
        data = self.makeRtp(frame, frameNumber)
        destinations = self._get_rtp_destinations()
        for address in destinations:
            self._rtp_socket.sendto(data, address)

    def makeRtp(self, payload, frameNbr):
        """RTP-packetize the video data."""
        version = 2
        padding = 0
        extension = 0
        cc = 0
        marker = 0
        pt = 26 # MJPEG type
        seqnum = frameNbr
        ssrc = 0

        packet = RtpPacket()
        packet.encode(version, padding, extension, cc, seqnum, marker, pt, ssrc, payload)

        return packet.getPacket()

    def send_reply_rtsp(self, reply):
        """
        :param sock: Socket to send data
        :param reply:ServerWorker.CmdRTSPResponse http reply
        :return:
        """

        # TODO: move it to HttpMessage.serialize
        code = reply.code

        msg = 'RTSP/1.0 '

        # Send RTSP reply to the client
        if code == self.OK_200:
            msg += '200 OK\r\n'
        # Error messages
        elif code == self.FILE_NOT_FOUND_404:
            print("404 NOT FOUND")
            msg += '404 Not Found\r\n'
        elif code == self.CON_ERR_500:
            print("500 CONNECTION ERROR")
            msg += '500 Internal Server Error\r\n'

        def add_data(data, field, value):
            data += ("%s: %s\r\n" % (str(field), str(value)))
            return data

        if reply.seq is not None:
            msg = add_data(msg, 'CSeq', reply.seq)
        if reply.values is not None:
            for key, value in reply.values.items():
                msg = add_data(msg, key, value)

        if reply.data is not None and len(reply.data) > 0:
            data = str(reply.data)
            msg = add_data(msg, 'Content-Length', len(data))
            msg += '\r\n'
            msg += data
        else:
            # Finish it!
            msg += '\r\n'

        return msg

    # Dispatching table for RTSP requests
    _dispatch_table = {
        Protocol.OPTIONS: _response_options,
        Protocol.DESCRIBE: _response_describe,
        Protocol.SETUP: _response_setup,
        Protocol.PLAY: _response_play,
        Protocol.PAUSE: _response_pause,
        Protocol.TEARDOWN: _response_teardown,
    }
