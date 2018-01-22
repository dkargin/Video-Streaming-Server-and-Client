"""
References:

- SDP: Session Description Protocol
https://tools.ietf.org/html/rfc4566

https://github.com/timohoeting/python-mjpeg-over-rtsp-client/blob/master/rfc2435jpeg.py
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


def make_sdp(video_opt):
    """
    Fill in SDP string, using specified video options
    :param video_opt: Table containing video options
    :return:string sdp
    """

    # Refactored SDP header. Used for python formatting
    mjpeg_sdp_format = """v=0
o=- 1272052389382023 1 IN IP4 0.0.0.0
s=%s
i=jpeg
t=0 0
a=tool:%s
a=type:broadcast
a=control:*
a=recvonly
a=x-qt-text-nam:%s
a=x-qt-text-inf:jpeg
m=video %d RTP/AVP 26
c=IN IP4 0.0.0.0
a=cliprect:0,0,%d,%d
a=framerate:%f"""

    sname = video_opt.get('session_name', 'Anystream')
    server_name = video_opt.get('server_name', 'Python RTSP server')
    video_port = video_opt.get('video_port', 0)
    audio_port = video_opt.get('audio_port', 0)
    fps = video_opt.get('fps', 25.0)
    width = video_opt.get('width', 1280)
    height = video_opt.get('height', 720)

    return mjpeg_sdp_format % (sname, server_name, sname, video_port, height, width, float(fps))


def make_sdp2(video_opt):
    mjpeg_sdp_format2 = """v=0
o=- 1272052389382023 1 IN IP4 0.0.0.0
s={session_name}
i=jpeg
t=0 0
a=tool:{server_name}
a=type:broadcast
a=control:*
a=recvonly
a=x-qt-text-nam:{session_name}
a=x-qt-text-inf:jpeg
m=video {video_port} RTP/AVP {payload}
a=control:rtsp://{url}:{rtsp_port}/{video_path}
c=IN IP4 0.0.0.0
a=cliprect:0,0,{height},{width}
a=framerate:{fps}"""

    options = {
        'session_name': 'Anystream',
        'server_name': 'Python RTSP server',
        'video_port': 0,
        'audio_port': 0,
        'payload': 26,
        'fps': 0,
        'width': 1280,
        'height': 720,
        'control_url': '*',
        'url': '127.0.0.7',
        'rtsp_port': '1025',
        'video_path': 'video.mjpg',
    }
    options.update(video_opt)
    return mjpeg_sdp_format2.format(**options)
