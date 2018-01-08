from random import randint
import socket
import re
from time import time

from VideoStream import VideoStream
from RtpPacket import RtpPacket

from HttpMessage import HttpMessage

from tornado.tcpserver import TCPServer
from tornado.iostream import StreamClosedError
from tornado import gen
from tornado.ioloop import PeriodicCallback

__author__ = 'Tibbers'

"""
References:

- SDP: Session Description Protocol
https://tools.ietf.org/html/rfc4566


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
a=range:npt=0-
a=x-qt-text-nam:%s
a=x-qt-text-inf:jpeg
m=video %d RTP/AVP 26
c=IN IP4 0.0.0.0
a=cliprect:0,0,%d,%d
a=framerate:%f"""


def make_sdp(video_opt={}):
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
    height = video_opt.get('height', 1280)

    return mjpeg_sdp_format % (sname, server_name, sname, video_port, height, width, float(fps))


# Dumps list data to a semicolon-separated string
def dump_list(data):
    result = ""
    first = True

    for item in data:
        if first:
            result += str(item)
            first = False
        else:
            result += ';'
            result += str(item)
    return result


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

INIT = 0
READY = 1
PLAYING = 2
PAUSE = 3
DONE = 4


class ClientInfo:
    def __init__(self, address, id):
        # Port range to receive RTP data
        print("Generating ClientInfo for %s, id=%d" % (str(address), id))
        self.id = id
        self.address = address
        self._state = INIT
        self.rtp_ports = None
        self.unicast = False
        self.interleaved = False
        self.rtp = False

    def reset(self):
        self._state = INIT
        self.rtp_ports = None
        self.unicast = False
        self.interleaved = False
        self.rtp = False

    @property
    def state(self):
        return self._state

    def set_state(self, new_state):
        self._state = new_state

    def set_rtp_ports(self, start, end):
        self.rtp_ports = range(start, end)

    def parse_transport_options(self, transport):
        self.reset()
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
            elif item.startswith('interleaved'):
                self.interleaved = True


# Implements RTSP protocol FSM
class ServerWorker(TCPServer):
    OK_200 = 200
    BAD_REQUEST_400 = 400
    FILE_NOT_FOUND_404 = 404
    METHOD_NOT_ALLOWED_405 = 405
    UNSUPPORTED_MEDIA_TYPE_415 = 415
    UNSUPPORTED_TRANSPORT_461 = 461
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

    def __init__(self, port):
        super(ServerWorker, self).__init__()

        # Maps address->client
        self.clients = {}
        self.video_opt = {'video_port':8400}
        self._rtp_socket = None
        self._rtp_pub_ports = range(8888, 8889)
        self._local_address = '127.0.0.1'
        self._client_address = None
        self._work_thread = None
        self._last_client_id = 0
        # Frame provider
        self._stream = None
        # Generate a randomized RTSP session ID
        self._session = randint(100000, 999999)
        print("Starting session id=%d at port %d" % (self._session, port))

        # Frame generator
        self._frame_generator = PeriodicCallback(self._gen_rtp_frame, 40)

        self.listen(port)

    def _get_client(self, address):
        return self.clients.get("%s:%d" % address)

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
                self._remove_client(address)
                break

    def _remove_client(self, address):
        if address in self.clients:
            self.clients.pop(address)

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
                    response_data = self.serialise_reply_rtsp(cmd)
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
                    address_str = "%s:%d" % address
                    if address not in self.clients:
                        self._last_client_id += 1
                        client = ClientInfo(address[0], self._last_client_id)
                        self.clients[address_str] = client
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
        if client.state == INIT:
            try:
                print("Initializing stream for %s" % url.path)
                # TODO: Make a proper stream pool
                self._stream = VideoStream(url.path)
            except IOError:
                yield self.CmdRTSPResponse(self.FILE_NOT_FOUND_404, seq)
                return

        # Send RTSP reply
        # Get the RTP/UDP port from the last line
        transport = request.get('transport')

        if transport is None:
            print("No transport info specified")
            yield self.CmdRTSPResponse(self.UNSUPPORTED_TRANSPORT_461, seq)
            return

        client.parse_transport_options(transport)

        if client.interleaved:
            print("Interleaved RTSP stream is not supported")
            values = {
                'Transport': request.get('transport')
            }
            yield self.CmdRTSPResponse(self.UNSUPPORTED_TRANSPORT_461, seq, values)
            return

        # Create a new socket for RTP/UDP. We need this info to tell client where to listen
        yield self.CmdOpenRTP()

        transport_options = ['RTP/AVP']  # Hardcoded, huh?
        if client.unicast:
            transport_options.append('unicast')
        if client.rtp_ports:
            transport_options.append("client_port=%d-%d" % (client.rtp_ports.start, client.rtp_ports.stop))
        #if self._local_address:
        #    transport_options.append("source=%s" % self._local_address)
        if self._rtp_pub_ports:
            transport_options.append("server_port=%d-%d" % (self._rtp_pub_ports.start, self._rtp_pub_ports.stop))

        values = {
            'Session': self._session,
            'Transport': dump_list(transport_options)
        }
        client.set_state(READY)
        yield self.CmdRTSPResponse(self.OK_200, seq, **values)  # seq[0] the sequenceNum received from Client.py

    def _response_play(self, request, client):
        """
        Process PLAY request
        :param request:HttpMessage
        """

        # RTP-Info: url=rtsp://192.168.0.254/jpeg/track1;seq=20730;rtptime=3869319494,url=rtsp://192.168.0.254/jpeg/track2;seq=33509;rtptime=3066362516
        rtp_info = [request.url_raw]
        rtp_info.append('seq=0')
        rtp_info.append('rtptime=0')
        values = {
            'Session': self._session,
            'Range': request.get('range'),
            'RTP-Info': dump_list(rtp_info)
        }

        if client.state == READY:
            print("READY->PLAYING")
            client.set_state(PLAYING)
            yield self.CmdRTSPResponse(self.OK_200, request.seq, **values)
            return
        # Process RESUME request
        elif client.state == PAUSE:
            print("PAUSE->PLAYING")
            client.set_state(PLAYING)
            yield self.CmdRTSPResponse(self.OK_200, request.seq, **values)
            return
        else:
            raise Exception("Should handle this. Was at state=%d" % client.state)

    def _response_pause(self, request, client):
        """
        Process PAUSE request
        :param request:HttpMessage
        """
        if client.state == PLAYING:
            print('PLAYING->READY')
            #print('-' * 60 + "\nPAUSE Request Received\n" + '-' * 60)
            client.set_state(READY)
            yield self.CmdRTSPResponse(self.OK_200, request.seq)
        else:
            raise Exception("Should handle this at state %d" % client.state)

    def _response_teardown(self, request, client):
        """
        Process TEARDOWN request
        :param request:HttpMessage
        """
        client.set_state(DONE)
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
            yield self.CmdRTSPResponse(self.BAD_REQUEST_400, request.seq)
            return

        client = self._get_client(address)
        handler = self._dispatch_table.get(request.type)

        if handler is not None:
            yield from handler(self, request, client)
        else:
            print("Unhandled RTSP method %s!!!" % str(request.type))
            yield self.CmdRTSPResponse(self.METHOD_NOT_ALLOWED_405, request.seq)

    def _gen_rtp_frame(self):
        data = self._stream.nextFrame()

        if data is None:
            return

        frameNumber = self._stream.frameNbr()

        self.publish_rtp_frame(data, frameNumber)

    # Returns a list of pairs (address, port)
    def _get_rtp_destinations(self):
        result = []

        # Add own addresses
        #if self._rtp_pub_ports is not None and self._local_address is not None:
        #    for port in self._rtp_pub_ports:
        #        result.append((self._local_address, port))

        for key, client in self.clients.items():
            if client.rtp_ports is not None:
                result.append((client.address, client.rtp_ports[0]))
        return result

    # Publish frame to all clients
    def publish_rtp_frame(self, frame, frameNumber):

        packet = RtpPacket()
        packet.pt = 26
        packet.seqnum = frameNumber
        timestamp = int(time())
        packet.encode(timestamp, frame)

        data = packet.getPacket()
        data_len = len(data)
        if data_len == 0:
            print("Empty data for some reason")
            return
        destinations = self._get_rtp_destinations()
        for address in destinations:
            sent_len = self._rtp_socket.sendto(data, address)
            if sent_len < 0:
                print("System error in sendto %s" % address)
            elif sent_len < data_len:
                print("Sent %d of %d to %s" % (sent_len, data_len, address))

    def make_rtp(self, payload, frameNbr):
        """RTP-packetize the video data."""
        #version = 2
        #padding = 0
        #extension = 0
        #cc = 0
        #marker = 0
        #pt = 26 # MJPEG type
        #seqnum = frameNbr
        #ssrc = 0
        pass

    def serialise_reply_rtsp(self, reply):
        """
        :param sock: Socket to send data
        :param reply:ServerWorker.CmdRTSPResponse http reply
        :return:
        """

        # TODO: move it to HttpMessage.serialize
        code = reply.code

        msg = 'RTSP/1.0 %d %s\r\n' % (code, StatusCodes.get(code, 'Unknown code'))

        # Send RTSP reply to the client

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
