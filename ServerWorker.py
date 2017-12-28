import random, math
import time
from random import randint
import sys
import traceback
import threading
import socket
from VideoStream import VideoStream
from RtpPacket import RtpPacket

import tornado
from tornado.tcpserver import TCPServer

__author__ = 'Tibbers'


#class MainHandler(tornado.web.RequestHandler):
#    def get(self):
#        self.write("Hello, world")


# Implements RTSP protocol FSM
class ServerWorker:
    SETUP = 'SETUP'
    OPTIONS = 'OPTIONS'
    PLAY = 'PLAY'
    PAUSE = 'PAUSE'
    TEARDOWN = 'TEARDOWN'

    INIT = 0
    READY = 1
    PLAYING = 2

    OK_200 = 0
    FILE_NOT_FOUND_404 = 1
    CON_ERR_500 = 2

    # RTSP response
    class CmdRTSPResponse:
        def __init__(self, status, seq, **kwargs):
            self.code = status
            self.seq = seq
            self.Public = kwargs.get('Public', None)

    # Command to open RTP port
    class CmdOpenRTP:
        def __init__(self):
            pass

    # Command to close RTP port
    class CmdCloseRTP:
        def __init__(self):
            pass

    def __init__(self, clientInfo):
        # TODO: strip socket to a separate field
        self.clientInfo = clientInfo
        self._rtsp_socket = clientInfo['rtspSocket'][0]
        self._rtp_socket = None
        self._client_address = clientInfo['rtspSocket'][1]
        self._work_thread = None
        self._state = ServerWorker.INIT
        # Generate a randomized RTSP session ID
        self._session = randint(100000, 999999)
        print("Starting session id=%d" % self._session)

    def run(self):
        """
        Run internal thread to handle rtsp requests
        """
        self._work_thread = threading.Thread(target=self._rtsp_request_handler)
        self._work_thread.start()

    def _rtsp_request_handler(self):
        """
        Receive RTSP request from the client.
        Works in a separate thread
        """
        sock = self._rtsp_socket
        while True:
            request_raw = sock.recv(256)
            if request_raw is None or len(request_raw) == 0:
                print("Should close a socket for some reason")
                break

            responses = 0

            # Gather commands from rtsp protocol processor
            for cmd in self._process_rtsp_request(request_raw.decode("utf-8")):
                if isinstance(cmd, self.CmdRTSPResponse):  # Generated http response
                    if self.send_reply_rtsp(sock, cmd):
                        responses += 1

                elif isinstance(cmd, self.CmdOpenRTP):  # Should open UDP port for streaming
                    # Create a new thread and start sending RTP packets
                    # TODO: make proper implementation
                    self.clientInfo["rtpSocket"] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    self.clientInfo['event'] = threading.Event()
                    self.clientInfo['worker'] = threading.Thread(target=self.send_rtp)
                    self.clientInfo['worker'].start()
                elif isinstance(cmd, self.CmdCloseRTP):  # Should close UDP port
                    # Close the RTP socket
                    # Should do some reference counting before such rude disconnect
                    self.clientInfo['rtpSocket'].close()

            if responses != 1:
                print("RTSP FSM is broken. Have generated %d responses" % responses)

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

        print("REQ=%s;\n" % str(header_line))
        print("DATA=%s;\n" % str(request[1]))
        # Get the RTSP sequence number
        seq = request[1].split(' ')

        # Process SETUP request
        if request_type == self.OPTIONS:
            # DESCRIBE
            yield self.CmdRTSPResponse(self.OK_200, seq[1], Public="SETUP, TEARDOWN, PLAY, PAUSE")
        elif request_type == self.SETUP:
            if self._state == self.INIT:
                # Get the media file name
                filename = header_line[1]
                # Update state
                print("SETUP Request received\n")

                try:
                    self.clientInfo['videoStream'] = VideoStream(filename)
                    self._state = self.READY

                except IOError:
                    yield self.CmdRTSPResponse(self.FILE_NOT_FOUND_404, seq[1])
                    return

                # Send RTSP reply
                print("sequenceNum is " + seq[0])
                # Get the RTP/UDP port from the last line
                self.clientInfo['rtpPort'] = request[2].split(' ')[3]
                print('-'*60 + "\nrtpPort is :" + self.clientInfo['rtpPort'] + "\n" + '-'*60)
                print("filename is " + filename)
                yield self.CmdRTSPResponse(self.OK_200, seq[0])  #seq[0] the sequenceNum received from Client.py

        # Process PLAY request
        elif request_type == self.PLAY:
            if self._state == self.READY:
                print('-'*60 + "\nPLAY Request Received\n" + '-'*60)
                self._state = self.PLAYING
                print('-' * 60 + "\nSequence Number (" + seq[0] + ")\nReplied to client\n" + '-' * 60)
                yield self.CmdRTSPResponse(self.OK_200, seq[0])
                # Create a new socket for RTP/UDP
                yield self.CmdOpenRTP()

        # Process RESUME request
            elif self._state == self.PAUSE:
                print('-'*60 + "\nRESUME Request Received\n" + '-'*60)
                self._state = self.PLAYING

        # Process PAUSE request
        elif request_type == self.PAUSE:
            if self._state == self.PLAYING:
                print('-'*60 + "\nPAUSE Request Received\n" + '-'*60)
                self._state = self.READY
                self.clientInfo['event'].set()
                yield self.CmdRTSPResponse(self.OK_200, seq[0])

        # Process TEARDOWN request
        elif request_type == self.TEARDOWN:
            print('-'*60 + "\nTEARDOWN Request Received\n" + '-'*60)
            self.clientInfo['event'].set()
            yield self.CmdRTSPResponse(self.OK_200, seq[0])
            yield self.CmdCloseRTP()

    def send_rtp(self):
        """Send RTP packets over UDP."""
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

            data = self.clientInfo['videoStream'].nextFrame()
            #print '-'*60 + "\ndata from nextFrame():\n" + data + "\n"
            if data:
                frameNumber = self.clientInfo['videoStream'].frameNbr()
                try:
                    #address = 127.0.0.1 #self.rtsp_socket[0]
                    #port = '25000' #int(self.clientInfo['rtpPort'])
                    #print '-'*60 + "\nmakeRtp:\n" + self.makeRtp(data,frameNumber)
                    #print '-'*60
                    #address = self.clientInfo['rtspSocket'][1]   #!!!! this is a tuple object ("address" , "")

                    port = int(self.clientInfo['rtpPort'])

                    prb = math.floor(random.uniform(1,100))
                    if prb > 5.0:
                        self.clientInfo['rtpSocket'].sendto(self.makeRtp(data, frameNumber),(self.clientInfo['rtspSocket'][1][0],port))
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

    def send_reply_rtsp(self, sock, reply):
        """
        :param sock: Socket to send data
        :param reply:ServerWorker.CmdRTSPResponse http reply
        :return:
        """
        code = reply.code
        seq = reply.seq

        reply_data = 'RTSP/1.0'
        # Send RTSP reply to the client
        if code == self.OK_200:
            reply_data += '200 OK\n'

        # Error messages
        elif code == self.FILE_NOT_FOUND_404:
            print("404 NOT FOUND")
            reply_data += '404 Not Found\n'
        elif code == self.CON_ERR_500:
            print("500 CONNECTION ERROR")
            reply_data += '500 Internal Server Error\n'

        reply_data += 'CSeq: ' + seq + '\nSession: ' + str(self._session)

        if reply.Public is not None:
            reply_data += "Public: %s\n" % str(reply.Public)

        sock.send(bytearray(reply_data.encode()))
        return True
