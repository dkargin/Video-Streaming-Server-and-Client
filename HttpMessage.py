import re   # to parse http values
from urllib.parse import urlparse


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
            print("Corrupted request")
            # TODO: Should we return something meaningful?
            return False

        self._header_line = lines[0].split(' ')
        if len(self._header_line) != 3:
            print("Corrupted request")
            return False
        self._method = self._header_line[0]
        self._url_raw = self._header_line[1]
        self._protocol = self._header_line[2]
        self._url = urlparse(self._url_raw)
        self.values = HttpMessage.parse_rtsp_values(lines[1:])
        self._payload = ""
        self._seq = self.values.get("cseq")

        print("REQ=%s\nDAT=%s" % (str(self._header_line), lines[1:]))
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
