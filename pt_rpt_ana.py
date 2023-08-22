#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-only
#
# PrimeTime Report Analysis
#
# Copyright (C) 2022 Yeh, Hsin-Hsien <yhh76227@gmail.com>
#
import argparse
import gzip
import os
import re

import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt

from .utils.common import PKG_VERSION, PT_ANA_VER

VERSION = f"pt_rpt_ana version {PT_ANA_VER} ({PKG_VERSION})"

### Function ###

def report_noise_brief(rpt_fp):
    """Brief Report for 'report_timing'"""  #{{{
    if os.path.splitext(rpt_fp)[1] == '.gz':
        f = gzip.open(rpt_fp, mode='rt')
    else:
        f = open(rpt_fp)

    IDLE, POS, REC = range(3)
    stage = IDLE

    print("NoiseRegion         WNS         TNS         NVP")
    print("===============================================")

    for line in f:
        if stage == IDLE and line.startswith(" noise_region:"):
            region, wns, tns, nvp = line.split(':')[1].strip(), 0, 0, 0
            stage = POS
        elif stage == POS and line.startswith(" ---"):
            stage = REC
        elif stage == REC:
            tok_list = line.strip().split()
            if len(tok_list) == 0:
                stage = IDLE
                print("{:<11}  {: >10.4f}  {: >10.4f}  {: >10.4f}".format(
                        region, wns, tns, nvp))
            else:
                slack = float(tok_list[4])
                tns += slack
                nvp += 1
                if slack < wns:
                    wns = slack
    f.close()
#}}}

### Main ###

def create_argparse() -> argparse.ArgumentParser:
    """Create Argument Parser"""  #{{{
    parser = argparse.ArgumentParser(
                formatter_class=argparse.RawTextHelpFormatter,
                description="PrimeTime Report Analysis")

    subparsers = parser.add_subparsers(dest='proc_mode', required=True, 
                                       help="select one of process modes.\n ")
    parser.add_argument('-version', action='version', version=VERSION)

    ## report_noise brief
    parser_time = subparsers.add_parser('nois', help="Brief report of report_noise\n" +
                                                     "  --command: 'report_noise'")
    parser_time.add_argument('rpt_fp', help="report_path") 

    return parser
#}}}

def main():
    """Main Function"""  #{{{
    parser = create_argparse()
    args = parser.parse_args()

    if args.proc_mode == 'nois':
        report_noise_brief(args.rpt_fp)
#}}}

if __name__ == '__main__':
    main()
