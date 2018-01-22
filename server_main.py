import sys
from RtspServer import RtspServer
from JpegStream import RtpJpegFileStream


# Test stream factory. Creates JpegStream for any url
def stream_factory(url):
    return RtpJpegFileStream('image.jpg')


def main():
    # TODO: use argparse, because it's cool!
    try:
        SERVER_PORT = int(sys.argv[1])
    except:
        print("[Usage: server_main.py Server_port]\n")

    server = RtspServer(SERVER_PORT, stream_factory)
    server.run()

# Program Start Point
if __name__ == "__main__":
    main()


