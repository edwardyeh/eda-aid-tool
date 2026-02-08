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
import time
from pathlib import Path
from .utils.primetime_cons import ConsReport
from . import __version__

VERSION = f'{Path(__file__).stem} version {__version__}'


##############################################################################
### Main


def create_argparse() -> argparse.ArgumentParser:
    """Create an argument parser."""
    parser = argparse.ArgumentParser(
                formatter_class=argparse.RawTextHelpFormatter,
                description="PrimeTime Report Analysis\n" + 
                            "-- Summary of report_constraint\n" +
                            "-- command: report_cons -all_vio -path end")

    parser.add_argument('-version', action='version', version=VERSION)
    parser.add_argument('rpt_fp', help="report path (left or base)") 
    parser.add_argument('rpt_fp2', nargs='?', 
                        help="report path (right for compare)") 
    parser.add_argument('-c', dest='cfg_fp', metavar='<config>', 
                        help="configuration file") 
    parser.add_argument('-bg', dest='bgrp', metavar='<path_group>', 
                        help="select a path group to analysis distribution.") 
    parser.add_argument('-bs', dest='bsca', metavar='<scale>', type=float, 
                        default=0.1, help="define bar chart scale.") 

    return parser


def main():
    """Main function."""
    parser = create_argparse()
    args = parser.parse_args()

    # Check if the configuration is existed
    if args.cfg_fp is None:
        path_cfg = Path(".pt_ana_cons.setup")
        if path_cfg.exists() and path_cfg.is_file():
            args.cfg_fp = path_cfg
        else:
            path_cfg = Path.home() / path_cfg
            if path_cfg.exists() and path_cfg.is_file():
                args.cfg_fp = path_cfg

    if args.rpt_fp2 is None:
        rpt_fps, is_multi = [args.rpt_fp], False
    else:
        rpt_fps, is_multi = [args.rpt_fp, args.rpt_fp2], True

    report = ConsReport(args.cfg_fp, is_multi)
    # t1 = time.perf_counter()
    report.parse_report(rpt_fps)
    # t2 = time.perf_counter()
    # print(f"=== Runtime: {t2-t1}")

    if report.is_multi:
        print()
        print(f"Left:  {Path(rpt_fps[0]).resolve()}")
        print(f"Right: {Path(rpt_fps[1]).resolve()}")
        print()
        print(f"Diff = Left - Right")
        print()
        report.print_summary_multi()
    else:
        print(f"\nReport:  {Path(rpt_fps[0]).resolve()}\n")
        report.print_summary()


if __name__ == '__main__':
    main()

