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

import pandas as pd
import numpy as np

from .utils.general import VERSION

### Common Function ###  {{{

val_op = {
    'ge': lambda a, b: a >= b,
    'le': lambda a, b: a <= b,
    'gt': lambda a, b: a > b,
    'lt': lambda a, b: a < b
}

#}}}

### Function for 'report_constraint' ###

def report_cons_summary(rpt_fps: list, value_clamp: dict, tag: str):
    """Summary for 'report_constraint'"""  #{{{

    vio_types = (
        'max_delay/setup', 'min_delay/hold', 
        'recovery', 'removal', 'clock_gating_setup', 'clock_gating_hold', 
        'max_capacitance', 'min_capacitance', 'max_transition', 'min_transition',
        'clock_tree_pulse_width', 'sequential_tree_pulse_width', 'sequential_clock_min_period',
    )

    group_vio = ('max_delay/setup', 'min_delay/hold')
    pulse_width_vio = ('clock_tree_pulse_width', 'sequential_tree_pulse_width')
    clk_period_vio = ('sequential_clock_min_period')

    IDLE, POS, REC1, REC2, REC3 = tuple(range(5))

    is_multi = len(rpt_fps) > 1
    summary = {}
    stage = IDLE

    for fid, rpt_fp in enumerate(rpt_fps):
        if os.path.splitext(rpt_fp)[1] == '.gz':
            f = gzip.open(rpt_fp, mode='rt')
        else:
            f = open(rpt_fp)

        for line in f:
            toks = line.split()
            if stage == IDLE and len(toks) and toks[0] in vio_types:
                stage, vtype, wns, tns, nvp = POS, toks[0], 0.0, 0.0, 0
                vgroup = toks[1][2:-1] if vtype in group_vio else vtype
                item = []
            elif stage == POS and len(toks) and toks[0].startswith('---'):
                if vtype in clk_period_vio:
                    vtype_dict = summary.setdefault(vtype, {})
                    stage, vgroup, stype_id = REC2, 'none', 2
                elif vtype in pulse_width_vio:
                    vtype_dict = summary.setdefault(vtype, {})
                    stage, vgroup, stype_id = REC2, 'none', 1
                else:
                    stage = REC1
                    vgroup_list = summary.setdefault(vtype, {}).setdefault(vgroup, [])
            elif stage == REC1:
                if len(toks):
                    item.extend(toks)
                    if toks[-1] == '(VIOLATED)':
                        if tag is not None and not item[-5].startswith(tag):
                            is_active = False
                        else:
                            is_active, slack = True, float(item[-2])
                            for op, val in value_clamp.items():
                                if not val_op[op](slack, val):
                                    is_active = False
                                    break

                        if is_active:
                            tns += slack 
                            nvp += 1
                            if slack < wns:
                                wns = slack
                        item = []
                else:
                    vgroup_list.append([wns, tns, nvp])
                    stage = IDLE
            elif stage == REC2:
                if len(toks):
                    item.extend(toks)
                    if toks[-2] == '(VIOLATED)':
                        cur_group = '{}:{}'.format(item[-1], item[stype_id][1:-1])
                        if vgroup != cur_group:
                            vgroup_list = vtype_dict.setdefault((vgroup := cur_group), [])
                            try:
                                vgroup_value = vgroup_list[fid]
                            except:
                                vgroup_list.append(vgroup_value := [0.0, 0.0, 0])

                        if tag is not None and not item[-6].startswith(tag):
                            is_active = False
                        else:
                            is_active, slack = True, float(item[-3])
                            for op, val in value_clamp.items():
                                if not val_op[op](slack, val):
                                    is_active = False
                                    break
                        
                        if is_active:
                            vgroup_value[1] += slack
                            vgroup_value[2] += 1
                            if slack < vgroup_value[0]:
                                vgroup_value[0] = slack
                        item = []
                else:
                    stage = IDLE

        f.close()

    if True:
        print()
        for vtype, vtype_dict in summary.items():
            eq_cnt = 98

            print("==== {}".format(vtype))
            if is_multi:
                eq_cnt += 80
                print("  {:=^58}+{:=^39}+{:=^39}+{:=^39}+".format('', ' Left ', ' Right ', ' Diff '))
                print("  {:58}".format('Group'), end='')
                print("| {:16}{:16}{:6}".format('WNS', 'TNS', 'NVP'), end='')
                print("| {:16}{:16}{:6}".format('WNS', 'TNS', 'NVP'), end='')
                print("| {:16}{:16}{:6}".format('WNS', 'TNS', 'NVP'), end='')
                print("|")
                print('  ', '=' * eq_cnt, '+', sep='')

                for vgroup, vgroup_list in vtype_dict.items():
                    print("  {:58}".format(vgroup), end='')
                    for values in vgroup_list:
                        print("| {0[0]:< 16.4f}{0[1]:< 16.4f}{0[2]:<6}".format(values), end='')

                    if is_multi:
                        diff_values = [vgroup_list[0][0] - vgroup_list[1][0]]
                        diff_values.append(vgroup_list[0][1] - vgroup_list[1][1])
                        diff_values.append(vgroup_list[0][2] - vgroup_list[1][2])
                        print("| {0[0]:<+16.4f}{0[1]:<+16.4f}{0[2]:<+6}|".format(diff_values), end='')
                    print()
            else:
                print("  {:58}  {:16}{:16}{:6}".format('Group', 'WNS', 'TNS', 'NVP'))
                print('  ', '=' * eq_cnt, sep='')

                for vgroup, vgroup_list in vtype_dict.items():
                    print("  {:58}".format(vgroup), end='')
                    for values in vgroup_list:
                        print("  {0[0]:< 16.4f}{0[1]:< 16.4f}{0[2]:<6}".format(values), end='')
                    print()

            print()
#}}}

### Function for 'report_time' ###

def report_time_brief(rpt_fp):
    """Brief Report for 'report_timing'"""  #{{{

    if os.path.splitext(rpt_fp)[1] == '.gz':
        f = gzip.open(rpt_fp, mode='rt')
    else:
        f = open(rpt_fp)

    ST, ED, GR, TY, SL = tuple(range(5))
    stage, path = ST, {}

    print("Group  Type  Slack  Endpoint  Startpoint")
    print("==================================================")

    ln_no = 0
    for line in f:
        ln_no += 1
        if stage == ST and line[:13] == "  Startpoint:":
            path['start'] = line[14:-1]
            path['no'] = ln_no
            stage = ED 
        elif stage == ED and line[:11] == "  Endpoint:":
            path['end'] = line[12:-1]
            stage = GR
        elif stage == GR and line[:13] == "  Path Group:":
            path['group'] = line[14:-1]
            stage = TY
        elif stage == TY and line[:12] == "  Path Type:":
            path['type'] = line.split()[2]
            stage = SL
        elif stage == SL and line[:9] == "  slack (":
            stage = ST
            toks = line.split()
            if toks[1] != '(MET)':
                print(path['group'], path['type'], toks[-1], path['end'], path['start'], end='')
                print(" line:{}".format(path['no']))

    f.close()
#}}}

### Main Function ###

def create_argparse() -> argparse.ArgumentParser:
    """Create Argument Parser"""  #{{{
    parser = argparse.ArgumentParser(
                formatter_class=argparse.RawTextHelpFormatter,
                description="PrimeTime Report Analysis")

    subparsers = parser.add_subparsers(dest='proc_mode', required=True, help="select one of process modes.")
    parser.add_argument('-version', action='version', version=VERSION)
    parser.add_argument('-ge', dest='ge', metavar='<value>', type=float, default=None, help="slack is greater than or equal to <value>")
    parser.add_argument('-le', dest='le', metavar='<value>', type=float, default=None, help="slack is less than or equal to <value>")
    parser.add_argument('-gt', dest='gt', metavar='<value>', type=float, default=None, help="slack is greater than <value>")
    parser.add_argument('-lt', dest='lt', metavar='<value>', type=float, default=None, help="slack is less than <value>")

    # report_constraint brief
    parser_cons = subparsers.add_parser('cons', help="Summary of report_constraint\n" + 
                                                     "  --command: 'report_cons -all_vio -path end'\n ")
    parser_cons.add_argument('rpt_fn', help="report path (left or base)") 
    parser_cons.add_argument('rpt_fn2', nargs='?', help="report path (right for compare)") 
    parser_cons.add_argument('-s', dest='tag', metavar='<pattern>', help="filter by scenario full/partial name") 

    # report_timing brief
    parser_time = subparsers.add_parser('time', help="Brief report of report_timing\n" +
                                                     "  --command: 'report_timing'")
    parser_time.add_argument('rpt_fn', help="report_path") 

    return parser
#}}}

def main():
    """Main Function"""  #{{{

    parser = create_argparse()
    args = parser.parse_args()
    
    value_clamp = {}
    if args.ge:
        value_clamp['ge'] = args.ge
    if args.le:
        value_clamp['le'] = args.le
    if args.gt:
        value_clamp['gt'] = args.gt
    if args.lt:
        value_clamp['lt'] = args.lt

    if args.proc_mode == 'cons':
        rpt_fps = [args.rpt_fn, args.rpt_fn2] if args.rpt_fn2 else [args.rpt_fn]
        report_cons_summary(rpt_fps, value_clamp, args.tag)
    elif args.proc_mode == 'time':
        report_time_brief(args.rpt_fn)
#}}}

if __name__ == '__main__':
    main()
