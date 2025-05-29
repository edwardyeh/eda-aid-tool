#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-only
#
# PrimeTime Report Analysis
# -- Summary of report_constraint
# -- command: report_cons -all_vio -path end
#
# Copyright (C) 2023 Yeh, Hsin-Hsien <yhh76227@gmail.com>
#
import argparse
import gzip
import math
import os
import re
import time

import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator

from .utils.common import PKG_VERSION, PT_CONS_VER
from .utils.primetime_cons import ConsReport

VERSION = f"pt_ana_cons version {PT_CONS_VER} ({PKG_VERSION})"

##############################################################################
### Main

def create_argparse() -> argparse.ArgumentParser:
    """Create Argument Parser"""  #{{{
    parser = argparse.ArgumentParser(
                formatter_class=argparse.RawTextHelpFormatter,
                description="PrimeTime Report Analysis\n" + 
                            "-- Summary of report_constraint\n" +
                            "-- command: report_cons -all_vio -path end")

    parser.add_argument('-version', action='version', version=VERSION)
    parser.add_argument('rpt_fp', help="report path (left or base)") 
    parser.add_argument('rpt_fp2', nargs='?', help="report path (right for compare)") 
    parser.add_argument('-c', dest='cfg_fp', metavar='<config>', 
                                help="configuration file") 
    parser.add_argument('-bg', dest='bgrp', metavar='<path_group>', 
                                help="select a path group to analysis distribution.") 
    parser.add_argument('-bs', dest='bsca', metavar='<scale>', type=float, default=0.1, 
                                help="define bar chart scale.") 

    return parser
#}}}

def main():
    """Main Function"""  #{{{
    parser = create_argparse()
    args = parser.parse_args()
    default_cfg = ".pt_ana_cons.setup"

    if args.cfg_fp is None and os.path.exists(default_cfg):
        if os.path.isfile(default_cfg):
            args.cfg_fp = default_cfg

    rpt_fps = ([args.rpt_fp] if args.rpt_fp2 is None 
                else [args.rpt_fp, args.rpt_fp2])

    report = ConsReport(args.cfg_fp)
    # t1 = time.perf_counter()
    report.parse_report(rpt_fps)
    # t2 = time.perf_counter()
    # print(f"=== Runtime: {t2-t1}")

    if report.is_multi:
        print()
        print(f"Left:  {os.path.abspath(rpt_fps[0])}")
        print(f"Right: {os.path.abspath(rpt_fps[1])}")
        print()
        print(f"Diff = Left - Right")
        print()
        report.print_summary2()
    else:
        print(f"\nReport:  {os.path.abspath(rpt_fps[0])}\n")
        report.print_summary()
#}}}

if __name__ == '__main__':
    main()

