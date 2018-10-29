import re   # to parse http values
import logging
from urllib.parse import urlparse


# RTSP Status codes from rfc-2326
# We could get this codes from any http framework.
# But cool guys do not use any http frameworks.
StatusCodes = {
    100: 'Continue',
    200: 'OK',
    201: 'Created',
    250: 'Low on Storage Space',
    300: 'Multiple Choices',
    301: 'Moved Permanently',
    302: 'Moved Temporarily',
    303: 'See Other',
    304: 'Not Modified',
    305: 'Use Proxy',
    400: 'Bad Request',
    401: 'Unauthorized',
    402: 'Payment Required',
    403: 'Forbidden',
    404: 'Not Found',
    405: 'Method Not Allowed',
    406: 'Not Acceptable',
    407: 'Proxy Authentication Required',
    408: 'Request Time - out',
    410: 'Gone',
    411: 'Length Required',
    412: 'Precondition Failed',
    413: 'Request Entity Too Large',
    414: 'Request - URI Too Large',
    415: 'Unsupported Media Type',
    451: 'Parameter Not Understood',
    452: 'Conference Not Found',
    453: 'Not Enough Bandwidth',
    454: 'Session Not Found',
    455: 'Method Not Valid in This State',
    456: 'Header Field Not Valid for Resource',
    457: 'Invalid Range',
    458: 'Parameter Is Read - Only',
    459: 'Aggregate operation not allowed',
    460: 'Only aggregate operation allowed',
    461: 'Unsupported transport',
    462: 'Destination unreachable',
    500: 'Internal Server Error',
    501: 'Not Implemented',
    502: 'Bad Gateway',
    503: 'Service Unavailable',
    504: 'Gateway Time - out',
    505: 'RTSP Version not supported',
    551: 'Option not supported'
}


logger = logging.getLogger('HttpMessage')


class HttpMessage:
    """
    Contains either HTTP request or response
    """

    prog = re.compile("^([\S]+): (.+)$")

    def __init__(self):
        """
        Initializes empty http message
        """
        self._protocol = ""
        self.raw = ""
        self._header_line = []
        self._method = None
        # Requested url, in a raw string form
        self._url_raw = ""
        # Parsed url
        self._url = None
        self.values = {}
        self._payload = ""
        self._seq = None

    @property
    def seq(self):
        return self._seq

    @property
    def url(self):
        return self._url

    @property
    def url_raw(self):
        return self._url_raw

    @property
    def type(self):
        return self._method

    def get(self, key, default=None):
        return self.values.get(key, default)

    def deserialize(self, raw_message):
        """
        Deserialize HTTP fields from raw string
        :param raw_message: raw request string
        :return:
        """
        # Get the request type
        lines = raw_message.split('\r\n')

        if len(lines) < 2:
            logger.error("Corrupted request")
            # TODO: Should we return something meaningful?
            return False

        self._header_line = lines[0].split(' ')
        if len(self._header_line) != 3:
            logger.error("Corrupted request")
            return False
        self._method = self._header_line[0]
        self._url_raw = self._header_line[1]
        self._protocol = self._header_line[2]
        self._url = urlparse(self._url_raw)
        self.values = HttpMessage.parse_rtsp_values(lines[1:])
        self._payload = ""
        self._seq = self.values.get("cseq")

        logger.debug("REQ=%s\nDAT=%s" % (str(self._header_line), lines[1:]))
        return True

    @staticmethod
    def parse_rtsp_values(lines):
        values = {}
        # Lines were already split by '\r\n' ends
        for line in lines:
            res = HttpMessage.prog.split(line)
            if len(res) == 4:
                key = res[1].lower()
                values[key] = res[2]

        return values

    @staticmethod
    def serialise_rtsp(code, seq, values, data):
        """
        Serializes data to a complete RTSP (HTTP) response
        :param code:int - RTSP(HTTP) code
        :param seq:int - sequence code
        :param values:dict - header values
        :param data:bytes - payload
        :return:string complete RTSP response
        """
        msg = 'RTSP/1.0 %d %s\r\n' % (code, StatusCodes.get(code, 'Unknown code'))

        # Send RTSP reply to the client
        def add_data(buffer, field, value):
            buffer += ("%s: %s\r\n" % (str(field), str(value)))
            return buffer

        if seq is not None:
            msg = add_data(msg, 'CSeq', seq)
        if values is not None:
            for key, value in values.items():
                msg = add_data(msg, key, value)

        if data is not None and len(data) > 0:
            data = str(data)
            msg = add_data(msg, 'Content-Length', len(data))
            msg += '\r\n'
            msg += data
        else:
            msg += '\r\n'

        return msg
