import sys
from tornado.ioloop import IOLoop
from RtspServer import ServerWorker


def main():
    # TODO: use argparse, because it's cool!
    try:
        SERVER_PORT = int(sys.argv[1])
    except:
        print("[Usage: server_main.py Server_port]\n")

    server = ServerWorker(SERVER_PORT)

    IOLoop.current().start()

# Program Start Point
if __name__ == "__main__":
    main()


