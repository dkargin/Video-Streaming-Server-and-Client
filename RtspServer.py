from random import randint
import re
import logging
from RtpServer import RtpServer

from HttpMessage import HttpMessage

from tornado.tcpserver import TCPServer
from tornado.iostream import StreamClosedError
from tornado.ioloop import IOLoop
from tornado import gen

__author__ = 'Tibbers, Dmitry Kargin'


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

INIT = 0
READY = 1
PLAYING = 2
PAUSE = 3
DONE = 4


class ClientInfo:
    """
    Contains receiver parameters
    It mostly covers transport stuff
    """
    def __init__(self, address, id):
        # Unique ID of this client
        self.id = id
        # IP address, that was obtained from http/rtsp session
        self.address = address
        # Server state
        self._state = INIT
        # Requested ports for RTP transmission
        self.rtp_ports = None
        self.unicast = False
        self.interleaved = False
        self.rtp = False

    def reset(self):
        """
        Reset local data to default state
        """
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
        """
        Parse transport string from RTSP DESCRIBE request
        :param transport:string with transport requirements
        """
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
class RtspServer(TCPServer):
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
        def __init__(self, client):
            """
            :param client:ClientInfo
            """
            self.client = client

    # Command to close RTP port
    class CmdCloseRTP:
        def __init__(self, client):
            self.client = client

    def __init__(self, port, stream_factory):
        """
        Creates RTP server instance
        :param port:int primary port for RTSP server
        :param stream_factory:function(url) generator for RTP packet provider
        """
        super(RtspServer, self).__init__()

        self.logger = logging.getLogger('RtspServer')
        # Maps address->client
        self.clients = {}
        self.video_opt = {'video_port': 8400}
        self._stream_factory = stream_factory
        self._stream = None
        self._rtp_server = RtpServer()
        self._local_address = '127.0.0.1'
        self._client_address = None
        self._work_thread = None
        self._last_client_id = 0
        # Generate a randomized RTSP session ID
        self._session = randint(100000, 999999)
        self.logger.debug("Starting session id=%d at port %d" % (self._session, port))

        self.listen(port)

    def _get_client(self, address):
        return self.clients.get("%s:%d" % address)

    def _remove_client(self, address):
        """
        Removes client from RTP publish list
        :param address: address tuple  of a client
        """
        if address in self.clients:
            self.clients.pop(address)

    @staticmethod
    def run():
        IOLoop.current().start()

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
                    self.logger.warn("Should close a socket for some reason")
                    break

                yield from self._handle_raw_request(stream, request_raw, address)

            except StreamClosedError:
                self.logger.warn("Stream from %s has been closed" % str(address))
                self._remove_client(address)
                break

    def _handle_raw_request(self, stream, request_raw, address):
        """
        Handles raw http request
        :param stream: stream from tornado
        :param request_raw: raw request packet
        :param address: address of requesint side
        :return:
        """
        responses = 0

        # Gather commands from RTSP protocol processor
        generator = self._process_rtsp_request(request_raw.decode("utf-8"), address)

        out = None

        # Spin our FSM
        # We should get at least one response, and some other internal commands
        while True:
            try:
                if out is None:
                    cmd = next(generator)
                else:
                    cmd = generator.send(out)
                    out = None

                if isinstance(cmd, self.CmdRTSPResponse):  # Generated http response
                    response_data = HttpMessage.serialise_rtsp(cmd.code, cmd.seq, cmd.values, cmd.data)
                    self.logger.debug("Responding=%s" % response_data)
                    yield stream.write(response_data.encode())
                    responses += 1
                elif isinstance(cmd, self.CmdOpenRTP):  # Should open UDP port for streaming
                    self._rtp_server.add_destination(cmd.client, (cmd.client.address, cmd.client.rtp_ports.start))
                    self._rtp_server.start()
                elif isinstance(cmd, self.CmdCloseRTP):  # Should close UDP port
                    self._rtp_server.remove_destination(cmd.client, cmd.client.address)
                    self._rtp_server.stop()
                elif isinstance(cmd, self.CmdInitClient):
                    address_str = "%s:%d" % address
                    if address not in self.clients:
                        self._last_client_id += 1
                        client = ClientInfo(address[0], self._last_client_id)
                        self.clients[address_str] = client
                        out = client # Will send it back to coroutine
                    else:
                        self.logger.debug("Picking existing ClientInfo for %s" % str(address))
                        out = self._get_client()
                else:
                    raise Exception("Unhandled yield result: %s" % str(type(cmd)))

            except StopIteration:
                break

        if responses != 1:
            # TODO: Just send a default server response here
            raise Exception("RTSP FSM is broken. Have generated %d responses instead of single one!" % responses)

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

        url = request.url

        self.logger.info("Initializing stream for %s" % url.path)

        if self._stream is None:
            # TODO: Make a proper stream pool
            try:
                self._stream = self._stream_factory(url.path)
            except FileNotFoundError as e:
                yield self.CmdRTSPResponse(self.FILE_NOT_FOUND_404, request.seq)
                return

        sdp = self._stream.get_sdp(self.video_opt)

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
        url = request.url
        seq = request.seq

        if client is None:
            # Creating new client
            client = yield self.CmdInitClient()

        # Update state
        if client.state == INIT:
            try:
                self._rtp_server.set_stream(self._stream)
            except IOError:
                yield self.CmdRTSPResponse(self.FILE_NOT_FOUND_404, seq)
                return

        # Send RTSP reply
        # Get the RTP/UDP port from the last line
        transport = request.get('transport')

        if transport is None:
            self.logger.warn("No transport info specified")
            yield self.CmdRTSPResponse(self.UNSUPPORTED_TRANSPORT_461, seq)
            return

        client.parse_transport_options(transport)

        if client.interleaved:
            self.logger.warn("Interleaved RTSP stream is not supported")
            values = {
                'Transport': request.get('transport')
            }
            yield self.CmdRTSPResponse(self.UNSUPPORTED_TRANSPORT_461, seq, values)
            return

        # Create a new socket for RTP/UDP. We need this info to tell client where to listen
        yield self.CmdOpenRTP(client)

        transport_options = ['RTP/AVP']  # Hardcoded, huh?
        if client.unicast:
            transport_options.append('unicast')
        if client.rtp_ports:
            transport_options.append("client_port=%d-%d" % (client.rtp_ports.start, client.rtp_ports.stop))
        #if self._local_address:
        #    transport_options.append("source=%s" % self._local_address)
        #if self._rtp_pub_ports:
        ports = self._rtp_server.get_server_ports()
        if ports:
            start = ports.start
            end = ports.stop
            transport_options.append("server_port=%d-%d" % (start, end))

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
        """
        Example RTP-Info:
        RTP-Info: url=rtsp://192.168.0.254/jpeg/track1;seq=20730;rtptime=3869319494,url=rtsp://192.168.0.254/jpeg/track2;seq=33509;rtptime=3066362516
        """
        rtp_info = list()
        rtp_info.append(request.url_raw)
        # TODO: Get a proper seq/rtptime
        rtp_info.append('seq=0')
        rtp_info.append('rtptime=0')
        values = {
            'Session': self._session,
            'Range': request.get('range'),
            'RTP-Info': dump_list(rtp_info)
        }

        if client.state == READY:
            self.logger.debug("READY->PLAYING")
            client.set_state(PLAYING)
            yield self.CmdRTSPResponse(self.OK_200, request.seq, **values)
            return
        # Process RESUME request
        elif client.state == PAUSE:
            self.logger.warn("PAUSE->PLAYING")
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
            logger.warn('PLAYING->READY')
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
        yield self.CmdCloseRTP(client)

    def _process_rtsp_request(self, raw_data, address):
        """
        Coroutine that process RTSP protocol sequence
        @:rtype: tuple with HTTP status and data
        """
        #self.logger.warn('-'*60)
        request = HttpMessage()
        if not request.deserialize(raw_data):
            self.logger.error("Corrupted RTSP request")
            yield self.CmdRTSPResponse(self.BAD_REQUEST_400, request.seq)
            return

        client = self._get_client(address)
        handler = self._dispatch_table.get(request.type)

        if handler is not None:
            yield from handler(self, request, client)
        else:
            self.logger.error("Unhandled RTSP method %s!!!" % str(request.type))
            yield self.CmdRTSPResponse(self.METHOD_NOT_ALLOWED_405, request.seq)

    # Dispatching table for RTSP requests
    _dispatch_table = {
        Protocol.OPTIONS: _response_options,
        Protocol.DESCRIBE: _response_describe,
        Protocol.SETUP: _response_setup,
        Protocol.PLAY: _response_play,
        Protocol.PAUSE: _response_pause,
        Protocol.TEARDOWN: _response_teardown,
    }
