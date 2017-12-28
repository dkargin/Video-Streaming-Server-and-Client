import random, math
import time
from random import randint
import sys
import traceback
import socket
import threading
from urllib.parse import urlparse

import re # to parse http values

from VideoStream import VideoStream
from RtpPacket import RtpPacket


from tornado.tcpserver import TCPServer
from tornado.iostream import StreamClosedError
from tornado import gen


__author__ = 'Tibbers'

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


# Implements RTSP protocol FSM
class ServerWorker(TCPServer):
    INIT = 0
    READY = 1
    PLAYING = 2
    PAUSE = 3

    OK_200 = 0
    FILE_NOT_FOUND_404 = 1
    CON_ERR_500 = 2

    # RTSP response
    class CmdRTSPResponse:
        def __init__(self, status, seq, data = None, **kwargs):
            self.code = status
            self.seq = seq
            self.values = kwargs
            self.data = data

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
        # TODO: strip socket to a separate field
        self.clientInfo = {}
        self.video_opt = {}
        self._rtp_socket = None
        self._client_address = None
        self._work_thread = None
        self._state = ServerWorker.INIT
        # Frame provider
        self._stream = None
        # Generate a randomized RTSP session ID
        self._session = randint(100000, 999999)
        print("Starting session id=%d" % self._session)

    @gen.coroutine
    def handle_stream(self, stream, address):
        """
        Receive RTSP request from the client.
        Works in a separate thread
        """
        while True:
            try:
                request_raw = yield stream.read_until(b'\r\n\r\n')
                #request_raw = sock.recv(256)
                if request_raw is None or len(request_raw) == 0:
                    print("Should close a socket for some reason")
                    break

                responses = 0

                # Gather commands from rtsp protocol processor
                for cmd in self._process_rtsp_request(request_raw.decode("utf-8")):
                    if isinstance(cmd, self.CmdRTSPResponse):  # Generated http response
                        response_data = self.send_reply_rtsp(cmd)
                        print("Responding=%s"%response_data)
                        yield stream.write(response_data.encode())
                        responses += 1

                    elif isinstance(cmd, self.CmdOpenRTP):  # Should open UDP port for streaming
                        if self._rtp_socket is None:
                            # Create a new thread and start sending RTP packets
                            self._rtp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                            # TODO: make proper implementation
                            self.clientInfo['event'] = threading.Event()
                            self.clientInfo['worker'] = threading.Thread(target=self.send_rtp)
                            self.clientInfo['worker'].start()
                    elif isinstance(cmd, self.CmdCloseRTP):  # Should close UDP port
                        if self._rtp_socket is not None:
                            # Close the RTP socket
                            # Should do some reference counting before such rude disconnect
                            self._rtp_socket.close()
                            self._rtp_socket = None

                if responses != 1:
                    print("RTSP FSM is broken. Have generated %d responses" % responses)

            except StreamClosedError:
                break

    def parse_rtsp_values(self, lines):
        values = {}
        prog = re.compile("^([\S]+): (.+)$")
        # Lines were already split by '\r\n' ends
        for line in lines:
            res = prog.split(line)
            if len(res) == 4:
                values[res[1]] = res[2]

        return values

    def _process_rtsp_request(self, raw_data):
        """
        Coroutine that process RTSP protocol sequence
        @:rtype: tuple with HTTP status and data
        """
        # Get the request type
        request = raw_data.split('\r\n')

        if len(request) < 2:
            print("Corrupted RTSP request")
            # TODO: Should we return something meaningful?
            return

        header_line = request[0].split(' ')
        request_type = header_line[0]

        print("REQ=%s;" % str(header_line))
        print("DATA=%s;" % str(request[1]))
        # Get the RTSP sequence number
        seq = request[1].split(' ')[1]

        values = self.parse_rtsp_values(request[1:])

        # Process SETUP request
        if request_type == Protocol.OPTIONS:
            yield self.CmdRTSPResponse(self.OK_200, seq, Public="DESCRIBE, SETUP, TEARDOWN, PLAY, PAUSE")
        elif request_type == Protocol.DESCRIBE:
            # Get the media file name
            filename = header_line[1]
            sdp = make_sdp(self.video_opt)
            values = {
                'x-Accept-Dynamic-Rate': 1,
                'Content-Base': filename,
                'Content-Type': 'application/sdp'
            }
            yield self.CmdRTSPResponse(self.OK_200, seq, sdp, **values)
        elif request_type == Protocol.SETUP:
            # Get the media file name
            url = urlparse(header_line[1])
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
            transport = values.get('Transport', None)

            if transport is None:
                yield self.CmdRTSPResponse(self.FILE_NOT_FOUND_404, seq)
            # Should parse ports
            self.clientInfo['rtpPort'] = request[2].split(' ')[3]
            print('-'*60 + "\nrtpPort is :" + self.clientInfo['rtpPort'] + "\n" + '-'*60)
            values = {
                'Session': self._session,
                'Transport': values.get('Transport', 'RTP/AVP;unicast')
            }
            yield self.CmdRTSPResponse(self.OK_200, seq, **values)  #seq[0] the sequenceNum received from Client.py

        # Process PLAY request
        elif request_type == Protocol.PLAY:
            if self._state == self.READY:
                print('-'*60 + "\nPLAY Request Received\n" + '-'*60)
                self._state = self.PLAYING
                yield self.CmdRTSPResponse(self.OK_200, seq)
                # Create a new socket for RTP/UDP
                yield self.CmdOpenRTP()

        # Process RESUME request
            elif self._state == self.PAUSE:
                print('-'*60 + "\nRESUME Request Received\n" + '-'*60)
                self._state = self.PLAYING

        # Process PAUSE request
        elif request_type == Protocol.PAUSE:
            if self._state == self.PLAYING:
                print('-'*60 + "\nPAUSE Request Received\n" + '-'*60)
                self._state = self.READY
                self.clientInfo['event'].set()
                yield self.CmdRTSPResponse(self.OK_200, seq)

        # Process TEARDOWN request
        elif request_type == Protocol.TEARDOWN:
            print('-'*60 + "\nTEARDOWN Request Received\n" + '-'*60)
            #self.clientInfo['event'].set()
            yield self.CmdRTSPResponse(self.OK_200, seq)
            yield self.CmdCloseRTP()
        else:
            print("Unhandled message!!!")
            yield self.CmdRTSPResponse(self.FILE_NOT_FOUND_404, seq)

    def send_rtp(self, address):
        """Send RTP packets over UDP."""
        #port = int(self.clientInfo['rtpPort'])
        #address = (self.clientInfo['rtspSocket'][1][0], port)
        counter = 0
        threshold = 10
        while True:
            jit = math.floor(random.uniform(-13,5.99))
            jit = jit / 1000

            self.clientInfo['event'].wait(0.05 + jit)
            jit = jit + 0.020

            # Stop sending if request is PAUSE or TEARDOWN
            if self.clientInfo['event'].isSet():
                break

            data = self._stream.nextFrame()
            #print '-'*60 + "\ndata from nextFrame():\n" + data + "\n"
            if data:
                frameNumber = self._stream.frameNbr()
                try:
                    #address = 127.0.0.1 #self.rtsp_socket[0]
                    #port = '25000' #int(self.clientInfo['rtpPort'])
                    #print '-'*60 + "\nmakeRtp:\n" + self.makeRtp(data,frameNumber)
                    #print '-'*60

                    prb = math.floor(random.uniform(1,100))
                    if prb > 5.0:
                        self._rtp_socket.sendto(self.makeRtp(data, frameNumber), address)
                        counter += 1
                        time.sleep(jit)
                except:
                    print("Connection Error")
                    print('-'*60)
                    traceback.print_exc(file=sys.stdout)
                    print('-'*60)

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
        code = reply.code
        seq = reply.seq

        msg = 'RTSP/1.0 '

        def add_data(data, field, value):
            data += ("%s: %s\r\n" % (str(field), str(value)))
            return data

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

        msg = add_data(msg, 'Cseq', reply.seq)
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
