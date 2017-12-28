__author__ = 'Tibbers'
import sys, socket

from tornado.tcpserver import TCPServer
from tornado.iostream import StreamClosedError
from tornado import gen


from ServerWorker import ServerWorker

def main():
    # TODO: use argparse, because it's cool!
    try:
        SERVER_PORT = int(sys.argv[1])
    except:
        print("[Usage: server_main.py Server_port]\n")
    rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        rtspSocket.bind(('', SERVER_PORT))
    except OSError as e:
        print("Failed to bind a socket to port %d: %s" % (SERVER_PORT, str(e)))
        return

    print("RTSP Listing incoming request at port %d..." % SERVER_PORT)
    rtspSocket.listen(5)

    # Receive client info (address,port) through RTSP/TCP session
    while True:
        info = {}
        info['rtspSocket'] = rtspSocket.accept()   # this accept {SockID,tuple object},tuple object = {clinet_addr,intNum}!!!
        worker = ServerWorker(info)
        worker.run()

# Program Start Point
if __name__ == "__main__":
    main()


