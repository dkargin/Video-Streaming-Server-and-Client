from struct import pack_into, unpack_from, pack, pack_into

from RtpPacket import RtpPacket

component_map = {1: 'Y', 2: 'Cb', 3: 'Cr', 4: 'I', 5: 'Q'}

"""
References:

http://vip.sugovica.hu/Sardi/kepnezo/JPEG%20File%20Layout%20and%20Format.htm
Used for making JPEG parser

https://tools.ietf.org/html/rfc2435
Used as a reference RTP-MJPEG packetiser
"""


class JPEGFile:
    """
    Parser for JPEG file
    """
    def __init__(self):
        self.width = 0
        self.height = 0
        self.type = 0
        self.dri = None
        self._image_data = None
        # End marker for parser
        self._done = False

        # Quantization tables, lqt, cqt
        self.quantization_table = {}
        self._error = 0
        self._found_quant = 0
        self._found_soi = 0
        self._found_sof = 0
        self._found_dqt = 0
        self._found_jfif = 0
        self._found_data = False

    # Reset parser to initial state
    def reset(self):
        self._error = 0
        self.width = 0
        self.height = 0
        self.quantization_table = {}

        self._done = False
        self._found_quant = 0
        self._found_soi = 0
        self._found_sof = 0
        self._found_dqt = 0
        self._found_jfif = 0
        self._found_data = False

    def load_data(self, p, offset=0, end=0):
        """
        Parses JPEG header from a block of data
        :param p: a list of bytes
        :param offset:int byte offset to start of image data
        :param end:int byte offset to an end of data block
        :return:
        """
        if end == 0:
            end = len(p)

        self.reset()

        if p[offset+0] != 0xff or p[offset+1] != 0xd8:
            print("No SOI header at start")
            return False

        self._done = False

        while offset+4 < end and not self._done:
            temp_data = p[offset:]          # Debug data view
            (head_lo, head_hi) = unpack_from('!BB', p, offset)
            head = (head_lo<<8) | head_hi

            handler = self.block_parsers.get(head)
            if handler:
                offset += handler(self, p, offset)
            else:
                length = unpack_from("!H", p, offset+2)[0]
                print("Unknown block %x:%x len=%d" % (head_lo, head_hi, length))
                offset += (length+2)

        if self._found_data:
            self.image_data = p[offset:end]
            print("Length of image data=%d bytes" % len(self.image_data))
            return True
        return False

    def ParseJFIF(self, data, offset):
        pos = 0
        (app_l, app_h, length) = unpack_from("!BBH", data, offset)
        print("Parsing JFIF block id=%x:%x len=%d" % (app_l, app_h, length))
        if app_l != 0xff and app_h != 0xe0:
            print("Wrong APP0 header %x:%x" % (app_l, app_h))
        pos += 4
        id = unpack_from("!5c", data, offset+pos)
        # Should be 'JFIF'#0 (0x4a, 0x46, 0x49, 0x46, 0x00)
        pos += 5
        (version_major, version_minor, units) = unpack_from("!BBB", data, offset+pos)
        if version_major != 1:
            print("Strange JFIF version %d.%d" % (version_major, version_minor))
        pos += 3

        (width, height, xtumb, ytumb) = unpack_from("!hhbb", data, offset+pos)
        pos += 6
        if 2 + length - pos > 0:
            thumb_data = 3*width*height

        self._found_jfif += 1
        return length+2

    def ParseSOI(self, data, offset):
        (app_l, app_h) = unpack_from("!BB", data, offset)
        print("Parsing SOI block id=%x:%x" % (app_l, app_h))
        self._found_soi += 1
        return 2

    def ParseSOF(self, data, offset):
        """
        SOF0 (Start Of Frame 0) marker:

        Field                   Size                      Description
        Marker Identifier       2 bytes    0xff, 0xc0 to identify SOF0 marker
        Length                  2 bytes    This value equals to 8 + components*3 value
        Data precision          1 byte     This is in bits/sample, usually 8 (12 and 16 not supported by most software).
        Image height            2 bytes    This must be > 0
        Image Width             2 bytes    This must be > 0
        Number of components    1 byte     Usually 1 = grey scaled, 3 = color YcbCr or YIQ, 4 = color CMYK
        Each component          3 bytes    Read each component data of 3 bytes. It contains,
                                           (component Id(1byte)(1 = Y, 2 = Cb, 3 = Cr, 4 = I, 5 = Q),
                                           sampling factors (1byte) (bit 0-3 vertical., 4-7 horizontal.),
                                           quantization table number (1 byte)).
        Remarks:     JFIF uses either 1 component (Y, greyscaled) or 3 components (YCbCr, sometimes called YUV, colour).
        """
        (app_l, app_h, length) = unpack_from("!BBH", data, offset)
        if app_l == 0xff and app_h in range(0xc0, 0xcf):
            print("Parsing SOF block id=%x:%x len=%d" % (app_l, app_h, length))
        else:
            print("Block mismatch")
            return None
        pos = 4
        (precision, self.height, self.width, num_components) = unpack_from("!BHHB", data, offset+pos)
        pos += 6
        print("\t - image size %dx%d" % (self.width, self.height))
        self._found_sof += 1

        for i in range(0, num_components):
            (comp_id, comp_sampling, quant_table) = unpack_from("!3B", data, offset+pos)
            print("\t -component %s samp=%d, qt=%d" % (component_map.get(comp_id, 'N'), comp_sampling, quant_table))
            pos += 3

        return length+2

    def ParseDRI(self, data, offset):
        """
        Marker Identifier   2 bytes     0xff, 0xdd  identifies DRI marker
        Length              2 bytes     It must be 4
        Restart interval    2 bytes     This is in units of MCU blocks, means that every n
                                        MCU blocks a RSTn marker can be found.The first marker
                                        will be RST0, then RST1 etc, after RST7 repeating from RST0.
        """
        (app_l, app_h, length, self.dri) = unpack_from("!BBH", data, offset)
        if app_l == 0xff and app_h == 0xdd:
            print("Parsed DRI block id=%x:%x len=%d" % (app_l, app_h, length))
        return length + 2

    def ParseSOFn(self, data, offset):
        (app_l, app_h, length) = unpack_from("!BBH", data, offset)
        if app_l == 0xff and app_h in range(0xc0, 0xcf):
            print("Skipping SOFn block id=%x:%x len=%d" % (app_l, app_h, length))
        return length+2

    def ParseQuantBlock(self, data, offset):
        (head_lo, head_hi, length, tableNo) = unpack_from('!BBHB', data, offset)
        if head_lo != 0xff and head_hi != 0xdb:
            print("Failed to find DQT header")
            return None
        print("Parsing Quantization block id=%x:%x len=%d table=%d" % (head_lo, head_hi, length, tableNo))
        offset += 4
        qt = data[offset:offset+length]
        self.quantization_table[tableNo] = qt
        self._found_quant += 1
        offset += length
        return 2+length

    def ParseStartOfScan(self, data, offset):
        """
        Marker Identifier             2 bytes      0xff, 0xda identify SOS marker
        Length                        2 bytes      This must be equal to 6+2*(number of components in scan).
        Number of Components in scan  1 byte       This must be >= 1 and <=4 (otherwise error), usually 1 or 3
        Each component                2 bytes      For each component, read 2 bytes. It contains,
                                                         1 byte   Component Id (1=Y, 2=Cb, 3=Cr, 4=I, 5=Q),
                                                         1 byte   Huffman table to use :
                                                               bit 0..3 : AC table (0..3)
                                                               bit 4..7 : DC table (0..3)
        Ignorable Bytes               3 bytes      We have to skip 3 bytes.
        """
        (head_lo, head_hi, length, num_components) = unpack_from('!BBHB', data, offset)
        print("Parsing Start Of Scan id=%x:%x len=%d" % (head_lo, head_hi, length))

        if num_components not in range(1, 4):
            print("\t %d - strange number of components" % num_components)
        pos = 5
        for c in range(0, num_components):
            (id, table_flags) = unpack_from('!BB', data, offset+pos)
            pos += 2

        pos += 3

        self._found_data = True
        self._done = True

        return length + 2

    def ParseEndOfImage(self, data, offset):
        print("Parsing End Of Image")
        (head_lo, head_hi, length) = unpack_from('!BBH', data, offset)
        self._done = True
        return length + 2

    HEADER_SOI = 0xffd8
    HEADER_APP0 = 0xffe0
    HEADER_SOS = 0xffda
    HEADER_QUANT = 0xffdb
    HEADER_DRI = 0xffdd
    HEADER_EOI = 0xffd9

    block_parsers = {
        HEADER_SOI: ParseSOI,
        HEADER_APP0: ParseJFIF,
        HEADER_DRI: ParseDRI,
        0xffc0: ParseSOF,
        0xffc1: ParseSOF,
        0xffc2: ParseSOF,
        0xffc3: ParseSOFn,
        0xffc4: ParseSOFn,
        0xffc5: ParseSOFn,
        0xffc6: ParseSOFn,
        0xffc7: ParseSOFn,
        0xffc9: ParseSOFn,
        0xffca: ParseSOFn,
        0xffcb: ParseSOFn,
        0xffcd: ParseSOFn,
        0xffce: ParseSOFn,
        0xffcf: ParseSOFn,
        HEADER_SOS: ParseStartOfScan,
        HEADER_QUANT: ParseQuantBlock,
        HEADER_EOI: ParseEndOfImage,
    }

RTP_JPEG_RESTART = 0x40
RTP_PT_JPEG = 26
JPG_HDR_SIZE = 8  # Number of bytes for RTP-JPG header
DRI_SIZE = 4  # Number of bytes for DRI


class RTPJpegEncoder:
    """
    Encodes Jpeg file to RTP packets
    """
    def __init__(self):
        #super(RTPJpegConverter, self).__init__()
        self.jpeg_TypeSpecific = 0
        self.jpeg_Type = 0
        self.jpeg_Q = 0
        self.jpeg_QT_MBZ = 0
        self.jpeg_QT_Precision = 0
        self.seq = 0
        self.ssrc = 0

    def write_chroma(self, jpeg, out, offset):
        out[offset:offset+64] = jpeg.quantization_table[0]

    def write_luma(self, jpeg, out, offset):
        out[offset:offset + 64] = jpeg.quantization_table[1]

    # Makes another RTP frame
    def make_rtp_frame(self, jpeg, jpeg_offset, frame_length):
        """
        :param jpeg:JpegFile
        :param jpeg_offset:int
        :param frame_length:int
        :return:bytearray rtp mjpeg payload
        """
        """
        // Initialize JPEG header. OK
        jpghdr.tspec = typespec;
        jpghdr.off = 0;
        jpghdr.type = type | ((dri != 0) ? RTP_JPEG_RESTART : 0);
        jpghdr.q = q;
        jpghdr.width = width / 8;
        jpghdr.height = height / 8;

        // Initialize DRI header.   OK
        if (dri != 0) {
            struct jpeghdr_rst {
                    u_int16 dri;
                    unsigned int f:1;
                    unsigned int l:1;
                    unsigned int count:14;
            };
            rsthdr.dri = dri;
            rsthdr.f = 1;        /* This code does not align RIs */
            rsthdr.l = 1;
            rsthdr.count = 0x3fff;
        }

        /* Initialize quantization table header
         */
        if (q >= 128) {
            qtblhdr.mbz = 0;
            qtblhdr.precision = 0; /* This code uses 8 bit tables only */
            qtblhdr.length = 128;  /* 2 64-byte tables */
        }
        """
        """
        while (bytes_left > 0)
        {
            ptr = packet_buf

            memcpy(packet_buf, &rtphdr, RTP_HDR_SZ);
            ptr += RTP_HDR_SZ;

            memcpy(ptr, &jpghdr, sizeof(jpghdr));
            ptr += sizeof(jpghdr);

            if (dri != 0)
            {
                memcpy(ptr, &rsthdr, sizeof(rsthdr));
                ptr += sizeof(rsthdr);
            }

            if (q >= 128 && jpghdr.off == 0) {
                memcpy(ptr, &qtblhdr, sizeof(qtblhdr));
                ptr += sizeof(qtblhdr);
                memcpy(ptr, lqt, 64);
                ptr += 64;
                memcpy(ptr, cqt, 64);
                ptr += 64;
            }

            data_len = PACKET_SIZE - (ptr - packet_buf);
            if (data_len >= bytes_left) {
                data_len = bytes_left;
                rtphdr.m = 1;
            }

            memcpy(ptr, jpeg_data + jpghdr.off, data_len);

            send_packet(packet_buf, (ptr - packet_buf) + data_len);

            jpghdr.off += data_len;
            bytes_left -= data_len;
            rtphdr.seq++;
        }
        return rtphdr.seq;
        """
        offset = 0
        hoffset = (jpeg_offset >> 16) & 0xff
        loffset = jpeg_offset & 0xffff

        output = bytearray()
        header = pack('!BBHBBBB',
                      self.TypeSpecific,
                      hoffset, loffset, self.Type, self.Q,
                      (jpeg.width >> 3), (self.height >> 3))
        output += header
        if jpeg.dri is not None:
            l = 1
            h = 1
            flags = l & 0x1
            flags |= (h << 1) & 0x2
            flags |= (0x3fff << 2)
            dri = pack('!HH', jpeg.dri, flags)
            output += dri
            offset += 4

        if self.jpeg_Q > 127 and jpeg_offset == 0:
            # Write table
            # Write luma x64
            # Write chroma x64
            qt = bytearray(132)
            qt_length = 128
            pack_into('!BBH', qt, 0, self.jpeg_QT_MBZ, self.jpeg_QT_Precision, qt_length)
            self.write_luma(jpeg, qt, 4)
            self.write_chroma(jpeg, qt, 68)
            output += qt
            offset += 132

        output += jpeg.image_data[jpeg_offset:jpeg_offset:frame_length]

        jpeg_offset += frame_length
        return output, jpeg_offset

    # Encode to RTP payload stream
    def encode_rtp(self, timestamp, jpeg, max_datagram_size):
        """
        :param timestamp:Time
        :param jpeg:JpegFile parsed Jpeg object
        :param max_datagram_size:
        :return:
        """
        packet = RtpPacket()
        packet.pt = RTP_PT_JPEG
        packet.seqnum = self.seq
        packet.timestamp = timestamp
        packet.ssrc = self.ssrc
        """
        // Initialize RTP header
        rtphdr.version = 2;
        rtphdr.p = 0;
        rtphdr.x = 0;
        rtphdr.cc = 0;
        rtphdr.m = 0;
        rtphdr.pt = RTP_PT_JPEG;
        rtphdr.seq = start_seq;
        rtphdr.ts = ts;
        rtphdr.ssrc = ssrc;
        """
        jpeg_offset = 0
        total_length = len(jpeg.image_data)
        result = []
        done = jpeg_offset >= total_length

        while not done:
            frame_length = min(max_datagram_size, total_length-jpeg_offset)
            data, jpeg_offset = self.make_rtp_frame(jpeg, jpeg_offset, frame_length)
            done = jpeg_offset >= total_length
            if done:
                packet.marker = 1
            packet_raw = packet.encode(data)
            self.seq += 1
            result.append(packet_raw)

        return result
