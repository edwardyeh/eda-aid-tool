#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-only
#
# PrimeTime Violation Summary by Timing Groups 
#
# Copyright (C) 2022 Yeh, Hsin-Hsien <yhh76227@gmail.com>
#
import argparse

### Global Parameter ###  

#{{{
VERSION = '0.1.0'
DEFAULT_PATH_COL_SIZE = 32
DEFAULT_AREA_COL_SIZE = 9
#}}}

### Sub Function ###

### Main Function ###

def create_argparse() -> argparse.ArgumentParser:
    """Create Argument Parser"""  #{{{
    parser = argparse.ArgumentParser(
                formatter_class=argparse.RawTextHelpFormatter,
                description="PrimeTime Violation Summary by Timing Groups.")

    parser.add_argument('-version', action='version', version=VERSION)
    parser.add_argument('rpt_fn', nargs='+', help="area report path") 

    return parser
#}}}

def main():
    """Main Function"""  #{{{

    parser = create_argparse()
    args = parser.parse_args()
#}}}

if __name__ == '__main__':
    main()
