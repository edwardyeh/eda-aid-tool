# SPDX-License-Identifier: GPL-2.0-only
#
# Copyright (C) 2022 Yeh, Hsin-Hsien <yhh76227@gmail.com>
#
"""
General function set
"""

VERSION = '0.20.1'

def str2int(str_: str, is_signed: bool=False, bits: int=32) -> int:
    """Convert string to integer (with HEX check)"""  #{{{
    if str_.startswith('0x') or str_.startswith('0X') :
        num = int(str_, 16)
        if num >> bits:
            raise ValueError("number overflow")
        if is_signed:
            sign = num >> (bits - 1)
            num |= ~((sign << bits) - 1)
    else:
        num = int(str_)
        if is_signed:
            bits -= 1
        if not is_signed and num < 0:
            raise ValueError("negative value founded in unsigned mode.")
        elif num > 0 and abs(num) >= (1 << bits):
            raise ValueError("number overflow")
        elif num < 0 and abs(num) > (1 << bits):
            raise ValueError("number overflow")
            
    return num
#}}}

