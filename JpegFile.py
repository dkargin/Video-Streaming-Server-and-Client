from struct import pack_into, unpack_from

component_map = {1: 'Y', 2: 'Cb', 3: 'Cr', 4: 'I', 5: 'Q'}


class JPEGFile:
    """
    Parser for JPEG file
    """
    def __init__(self):
        self.width = 0
        self.height = 0
        self.type = 0
        self.dri = 0
        # End marker for parser
        self._done = False

        # Quantization tables, lqt, cqt
        self.quantization_table = {}

        self._found_soi = 0
        self._found_dqt = 0
        self._found_jfif = 0
        self._found_data = False

    def parse(self, p, offset=0, end=0):
        """
        Parses JPEG header
        :param p: a list of bytes
        :param type:
        :param width:
        :param height:
        :param lqt:
        :param cqt:
        :param dri:
        :return:
        """
        if end == 0:
            end = len(p)

        if p[offset+0] != 0xff or p[offset+1] != 0xd8:
            print("No SOI header at start")
            return False

        self._done = False

        while offset+4 < end and not self._done:
            temp_data = p[offset:]      # Debug data view
            (head_lo, head_hi) = unpack_from('!BB', p, offset)
            head = (head_lo<<8) | head_hi
            #print("Found block %x:%x" % (head_lo, head_hi))

            handler = self.block_parsers.get(head)
            if handler:
                offset += handler(self, p, offset)
            else:
                length = unpack_from("!H", p, offset+2)[0]
                print("Unknown block %x:%x len=%d" % (head_lo, head_hi, length))
                offset += (length+2)
        if self._found_data:
            image_data = p[offset:end]
            print("Length of image data=%d bytes" % len(image_data))
        return

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
        (precision, height, width, num_components) = unpack_from("!BHHB", data, offset+pos)
        pos += 6
        print("\t - image size %dx%d" % (width, height))

        for i in range(0, num_components):
            (comp_id, comp_sampling, quant_table) = unpack_from("!3B", data, offset+pos)
            print("\t -component %s samp=%d, qt=%d" % (component_map.get(comp_id, 'N'), comp_sampling, quant_table))
            pos += 3

        return length+2

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
        print("Parsing Quantitization block id=%x:%x len=%d table=%d" % (head_lo, head_hi, length, tableNo))
        offset += 4
        qt = data[offset:offset+length]
        self.quantization_table[tableNo] = qt
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
