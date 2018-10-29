import argparse
import logging
"""
This example streams still jpeg frames

File is determined by requested URL
"""

from RtspServer import RtspServer
from JpegRtpStillStream import RtpJpegFileStream


def main():
    parser = argparse.ArgumentParser(description='Runs RTSP server that streams still jpeg images')
    parser.add_argument('-p', '--port', type=int, default=1025, help='port for RTSP server')
    parser.add_argument('--address', type=str, default='127.0.0.1', help='Base hostname to be announced through RTSP')
    parser.add_argument('--src', default='.', help='Directory with jpeg files to be streamed. Each file is accessible from as URL')
    args = parser.parse_args()

    # Test stream factory. Creates JpegStream for any url
    def stream_factory(path):
        """
        :param path: path to be opened. Extracted from URL and starts with '/'
        :return: Created stream or None
        """
        file = args.src + path
        try:
            return RtpJpegFileStream(file)
        except:
            raise
            # File not found? Should 404 back
            return None

    # format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
    # set up logging to file - see previous section for more details
    logging.basicConfig(level=logging.DEBUG,
                        format='%(message)s',
                        datefmt='%m-%d %H:%M')
    # define a Handler which writes INFO messages or hi

    server = RtspServer(args.port, stream_factory)
    print("Will stream to rtsp://%s:%d/"%(args.address, args.port))
    server.run()

# Program Start Point
if __name__ == "__main__":
    main()


