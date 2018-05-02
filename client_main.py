__author__ = 'Tibbers'
import sys
from tkinter import Tk
from Client import Client


def main():
    # TODO: use argparse
    try:
        serverAddr = sys.argv[1]
        serverPort = sys.argv[2]
        rtpPort = sys.argv[3]
        fileName = sys.argv[4]
    except:
        print("[Usage: client_main.py Server_name Server_port RTP_port Video_file]\n")
        return

    root = Tk()

    # Create a new client
    app = Client(root, serverAddr, serverPort, rtpPort, fileName)
    app.master.title("RTPClient")
    root.mainloop()

if __name__ == "__main__":
    main()
