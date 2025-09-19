import re


class number_util():
    def __init__(self):
        pass

    @classmethod
    def set_int_to_4_bytes_list(cls, value):
        if isinstance(value, str):
            value = int(value, 16)
        elif isinstance(value, int):
            value = int(f"{value:02X}", 16)
        # 将10进制数值转换成 4个字节的16进制数，位数不够前面补0  例如十进制数值10转换成[00 00 00 0A]
        datalist = re.findall(r'.{1,2}',
                              format(value,
                                     '08X')) if value != '' or value != 0 else re.findall(
            r'.{1,2}',
            format(int('0', 16), '08X'))  # 每 1~2 字符一组
        return datalist
        pass
