# RTSP/RTP server in python #

Forked from [Video-Streaming-Server-and-Client](https://github.com/TibbersDriveMustang/Video-Streaming-Server-and-Client).
I am trying to make it completely compatible with real RTSP clients, like VLC or ffplay

Requirements:
- python 3.5. I use a lot of `yield from` in protocol FSMs
- tornado, to spin my lovely coroutines and do socket stuff
- pil/pillow (for RTSP client, that is probably dead now)
- tkinter (for client as well)

# Running #

    Open a terminal:
        python still_jpeg_streamer.py --port 1025

    Open another terminal:
        python ClientLauncher.py 127.0.0.1 1025 5008 video.mjpeg

Start the server with the command line

```
python server_main.py --port 1025
```
	
Where server_port is the port your server listens to for incoming RTSP connections
    # 1025
    # Standard RTSP port is 554
    # But need to choose a #port > 1024


Open a new terminal

ffmpeg:
`ffplay -loglevel debug -i rtsp://localhost:1025/video.mjpeg`

live555 testRTSPClient (used in VLC):
`./testProgs/testRTSPClient rtsp://localhost:1025/video.mjpeg`

You can save jpeg images and use test jpeg loader to analyse what happened with data aftre being streamed

`../openRTSP -m rtsp://localhost:1025/wide_shit.jpg`
It should save reassembled JPEG frames back to a file

VLC:
`vlc --verbose=1 --file-logging --logfile=vlc-log.txt rtsp://localhost:1025/video.mjpeg`

References:

http://imrannazar.com/Let%27s-Build-a-JPEG-Decoder:-Huffman-Tables