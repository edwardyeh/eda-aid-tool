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


### Global Variable ###

# ofs_re = re.compile(r"(\w:)(.+)")
# ofs_ta = set(('s:',))

# cmp_re = re.compile(r"(\w:\w{3})([><=]{1,2})(.+)")
# cmp_ta = set(('w:wns', 'w:tns', 'w:nvp', 'r:slk', 'd:slk'))

# clk_vio = (
#     'clock_tree_pulse_width', 
#     'sequential_tree_pulse_width', 
#     'sequential_clock_min_period'
# )

# group_vio = ('max_delay/setup', 'min_delay/hold')


##############################################################################
### Function


# def report_cons_summary(rpt_fps: list, cfg_fp: str, bgrp: str=None, 
#                         bsca: float=0.1):
#     """
#     Report the summary of the command 'report_constraint'
#     """
#     cons_cfg = load_cons_cfg(cfg_fp)
#     cons_rpt = ConsReport(gcol_w=cons_cfg['gcol_w'],
#                           wns_w=cons_cfg['wns_w'],
#                           tns_w=cons_cfg['tns_w'],
#                           nvp_w=cons_cfg['nvp_w'],
#                           path_cfg=cons_cfg['p'],
#                           grp_cfg=cons_cfg['g'],
#                           ugrp_cfg=cons_cfg['ug'],
#                           gtag_cfg=cons_cfg['gtag'],
#                           gmsg_cfg=cons_cfg['gmsg'],
#                           plot_grp=bgrp)

#     cons_rpt.parse_report(rpt_fps)
#     tnum = len(cons_rpt.cons_tables)
#     # import pdb; pdb.set_trace()

#     ## for debug
#     # for i in range(tnum):
#     #     print(f"==== Table {i}")
#     #     cons_rpt.cons_tables[i].print()
#     # print()

#     is_multi = len(rpt_fps) > 1

#     if bgrp is not None:
#         plot_data = cons_rpt.plot_data

#         if is_multi:
#             data = plot_data[0] + plot_data[1]
#             min_xbin = math.floor(min(data) / bsca) * bsca
#             max_xbin = math.ceil(max(data) / bsca) * bsca
#             fig, axs = plt.subplots((cy:=2), (cx:=1), constrained_layout=True)
#         else:
#             min_xbin = math.floor(min(plot_data[0]) / bsca) * bsca
#             max_xbin = math.ceil(max(plot_data[0]) / bsca) * bsca
#             fig, axs = plt.subplots((cy:=1), (cx:=1), constrained_layout=True)

#         xbins = np.arange(min_xbin, max_xbin+bsca, step=bsca)

#         axs = plt.subplot(cy, cx, 1)
#         axs.hist(plot_data[0], bins=xbins, color='#84bd00', histtype='bar', 
#                  ec='k', rwidth=1, alpha=.6)
#         axs.set_xlim(min_xbin, max_xbin)
#         axs.yaxis.set_major_locator(MultipleLocator(1))
#         axs.set_ylabel("endpoints")
#         axs.set_title(bgrp)

#         if is_multi:
#             axs = plt.subplot(cy, cx, 2)
#             axs.hist(plot_data[1], bins=xbins, color='#84bd00', histtype='bar', 
#                      ec='k', rwidth=1, alpha=.6)
#             axs.set_xlim(min_xbin, max_xbin)
#             axs.yaxis.set_major_locator(MultipleLocator(1))
#             axs.set_ylabel("endpoints")

#         axs.set_xlabel("slack")
#         plt.show()
#         return

#     print()
#     if is_multi:
#         print("Report(left):  {}".format(os.path.abspath(rpt_fps[0])))
#         print("Report(right): {}".format(os.path.abspath(rpt_fps[1])))
#         print()
#         print("Information:   Diff = Left - Right")
#     else:
#         print("Report:  {}".format(os.path.abspath(rpt_fps[0])))
#     print()

#     for type_, table in cons_rpt.sum_tables.items():
#         print(f"==== {type_}")
#         if tnum == 1:
#             table.print(column=['group', 
#                                 'lwns', 'ltns', 'lnvp',
#                                 'comm'])
#         else:
#             table.print(column=['group', 
#                                 'lwns', 'ltns', 'lnvp',
#                                 'rwns', 'rtns', 'rnvp',
#                                 'dwns', 'dtns', 'dnvp', 
#                                 'comm'])
#         print()

#     if len(cons_rpt.comm_set) != 0:
#         print("\n[Condition]\n")
#         for cond in cons_rpt.comm_set:
#             print(f"  {cond}")
#         print()


##############################################################################
### Main


def create_argparse() -> argparse.ArgumentParser:
    """Create Argument Parser"""
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


def main():
    """Main Function"""
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


if __name__ == '__main__':
    main()


