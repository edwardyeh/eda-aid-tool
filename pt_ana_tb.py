#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-only
#
# PrimeTime Report Analysis
# -- Timing Path Brief Report
# -- command: report_timing
#
# Copyright (C) 2023 Yeh, Hsin-Hsien <yhh76227@gmail.com>
#
import argparse
import gzip
import os
import re

from .utils.common import PKG_VERSION

VERSION = f"pt_ana_tb version 1.0.0 ({PKG_VERSION})"

### Function ###

def load_timeb_cfg(cfg_fp) -> dict:
    """Load Configuration for Time Mode"""  #{{{
    # Config Data Structure:
    #
    # cons_cfg = {
    #   'pc': {tag1: regex_pattern1, tag2: regex_pattern2, ...},
    # }
    cons_cfg = {}
    with open(cfg_fp, 'r') as f:
        for no, line in enumerate(f.readlines(), start=1):
            line = line.split('#')[0].strip()
            if line != "":
                try:
                    if line.startswith('pc:'):
                        tag, pat = line[3:].split()
                        pc_dict = cons_cfg.setdefault('pc', {})
                        pc_dict[tag] = re.compile(pat)
                except SyntaxError:
                    raise SyntaxError(f"config syntax error (ln:{no})")

    return cons_cfg
#}}}

def report_time_brief(rpt_fp, is_all: bool, cfg_fp: str):
    """Brief Report for 'report_timing'"""  #{{{
    if os.path.splitext(rpt_fp)[1] == '.gz':
        f = gzip.open(rpt_fp, mode='rt')
    else:
        f = open(rpt_fp)

    if cfg_fp is not None:
        cons_cfg = load_timeb_cfg(cfg_fp)
    else:
        cons_cfg = None

    ST, ED, GR, TY, SL = range(5)
    stage, path = ST, {}
    print("Group  Type  Slack  Endpoint  Startpoint")
    print("==================================================")

    line, no = f.readline(), 1
    while line != "":
        line = line.lstrip()
        if stage == ST and line[:11] == "Startpoint:":
            path['start'] = line.split()[1]
            path['no'] = no
            stage = ED 
        elif stage == ED and line[:9] == "Endpoint:":
            path['end'] = line.split()[1]
            stage = GR
        elif stage == GR and line[:11] == "Path Group:":
            path['group'] = line.split()[2]
            stage = TY
        elif stage == TY and line[:10] == "Path Type:":
            path['type'] = line.split()[2]
            stage = SL
        elif stage == SL and line[:7] == "slack (":
            toks = line.rstrip().split()
            if toks[1] != '(MET)' or is_all:
                print(path['group'], path['type'], toks[-1], path['end'], path['start'], end='')
                print(" line:{}".format(path['no']))
            stage = ST
        line, no = f.readline(), no + 1
    f.close()
#}}}

### Main ###

def create_argparse() -> argparse.ArgumentParser:
    """Create Argument Parser"""  #{{{
    parser = argparse.ArgumentParser(
                formatter_class=argparse.RawTextHelpFormatter,
                description="PrimeTime Report Analysis\n" + 
                            "-- Timing Path Brief Report\n" +
                            "-- command: report_timing")

    parser.add_argument('-version', action='version', version=VERSION)
    parser.add_argument('-a', dest='is_all', action='store_true', 
                              help="show timing meet path \n(default: only violation path)")
    parser.add_argument('-c', dest='cfg_fp', metavar='<config>', help="configuration file") 
    parser.add_argument('rpt_fp', help="report_path") 
    return parser
#}}}

def main():
    """Main Function"""  #{{{
    parser = create_argparse()
    args = parser.parse_args()
    default_cfg = ".pt_ana_tb.setup"

    if args.cfg_fp is None and os.path.exists(default_cfg):
        if os.path.isfile(default_cfg):
            args.cfg_fp = default_cfg

    report_time_brief(args.rpt_fp, args.is_all, args.cfg_fp)
#}}}

if __name__ == '__main__':
    main()
