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
import re

import pandas as pd
import numpy as np

from .utils.general import VERSION

### Global Parameter ###  

#{{{
DEFAULT_PATHGROUP_COL_SIZE = 32
DEFAULT_AREA_COL_SIZE = 9

vio_header = ('instance', 'required', 'actual', 'slack')
vio_header_len = len(vio_header)

clk_vio_chk_list = (
        'clock_tree_pulse_width', 
        'sequential_tree_pulse_width', 
        'sequential_clock_min_period'
)

vio_type_list = (
        'max_delay/setup', 
        'min_delay/hold', 
        'max_capacitance', 
        'min_capacitance', 
        'max_transition', 
        'min_transition', 
        'recovery', 
        'clock_gating_setup' 
) + clk_vio_chk_list

#}}}

### Class Defintion ###

### Sub Function ###

def load_vio_rpt(rpt_fps) -> list:
    """Load PrimeTime Violation Report"""  #{{{

    ## Return Structure:
    ##   vio_tables = [
    ##     vio_report1 = {
    ##       'vio_type1' : {'group11': <DataFrame>,
    ##                      'group12': <DataFrame>, ...},
    ##       'vio_type2' : {'group21': <DataFrame>,
    ##                      'group22': <DataFrame>, ...},
    ##       ...
    ##     },
    ##     vio_report2 = {
    ##       'vio_type1' : {'group11': <DataFrame>,
    ##                      'group12': <DataFrame>, ...},
    ##       'vio_type2' : {'group21': <DataFrame>,
    ##                      'group22': <DataFrame>, ...},
    ##       ...
    ##     }
    ##   ]

    regexp_grp = re.compile(r"\('(\w+)' group\)")

    vio_tables = []

    if type(rpt_fps) is not list:
        rpt_fps = [rpt_fps]

    for rpt_fp in rpt_fps:
        with open(rpt_fp) as f:
            col_cnt = 0
            loc_en = parse_en = False
            vio_chk_en = clk_chk_en = False
            is_drop = is_cont = False
            vio_tables.append(vio_rpt_dt := {})

            line = f.readline()
            while line:
                if len(words := line.strip().split()):
                    if words[0] in vio_type_list:
                        vio_typ_dt = vio_rpt_dt.setdefault((vio_typ_name := words[0]), {})
                        try:
                            words = words[1:]
                            value = words[0]
                            while not value.endswith(')'):
                                words = words[1:]
                                value += f" {words[0]}"
                            group_name = regexp_grp.match(value)[1]
                        except:
                            group_name = 'default'
                        vio_grp_df = vio_typ_dt.setdefault(group_name, pd.DataFrame(columns=vio_header))
                        loc_en = True
                    elif loc_en:
                        if words[0].startswith('---'):
                            loc_en = False
                            parse_en = True
                    elif parse_en:
                        while len(words):
                            col_name = vio_header[col_cnt]
                            if col_name == 'instance':
                                if vio_typ_name in clk_vio_chk_list: 
                                    words = words[1:]
                                    value = words[0]
                                    while not value.endswith(')'):
                                        words = words[1:]
                                        value += f" {words[0]}"
                                    data_row = {col_name: value[1:-1].split()[-1]}
                                    words = words[1:]
                                else:
                                    data_row = {col_name: words[0]}
                                    words = words[1:]
                            elif vio_chk_en:
                                vio_chk_en = False
                                if words[0].startswith('(VIOLATED'):
                                    while not words[0].endswith(')'):
                                        words = words[1:]
                                    words = words[1:]
                                else:
                                    is_drop = True
                                    if clk_chk_en:
                                        clk_chk_en = False
                                    else:
                                        is_cont = True
                            elif clk_chk_en:
                                clk_chk_en = False
                                data_row[vio_header[0]] = f"{words[0]} ({data_row[vio_header[0]]})"
                            else:
                                data_row[col_name] = (value := float(words[0]))
                                words = words[1:]
                                if col_name == 'slack':
                                    vio_chk_en = True
                                    if vio_typ_name in clk_vio_chk_list: 
                                        clk_chk_en = True

                            if not vio_chk_en and not clk_chk_en:
                                col_cnt += 1

                            if col_cnt == vio_header_len:
                                col_cnt = 0
                                if is_drop:
                                    is_drop = False
                                    if is_cont:
                                        is_cont = False
                                        continue
                                    else:
                                        break
                                else:
                                    vio_grp_df.loc[vio_grp_df.shape[0]] = data_row
                                    break
                line = f.readline()
    return vio_tables
#}}}

def report_gvs(vio_tables: list):
    """Report Violation Group Summary"""  #{{{
    header_just = ['l', 'r', 'r']
    header_lens = [DEFAULT_PATHGROUP_COL_SIZE, DEFAULT_AREA_COL_SIZE, DEFAULT_AREA_COL_SIZE]
    header_list = ['Path Group', 'WNS', 'NVP']
    divider_size = sum(header_lens) + 2
    gvs_tables = {}

    is_multi = len(vio_tables) > 1

    for vio_typ_name, vio_typ_dict in vio_tables[0].items():
        gvs_df = gvs_tables.setdefault(vio_typ_name, pd.DataFrame(columns=['name', 'wns', 'nvp']))
        for vio_grp_name, vio_grp_df in vio_typ_dict.items():
            name = vio_grp_name + (' <-' if is_multi else '')
            wns = vio_grp_df['slack'].min()
            nvp = vio_grp_df.shape[0]
            gvs_df.loc[vio_grp_name] = [name, wns, nvp]

    if is_multi:
        for vio_typ_name, vio_typ_dict in vio_tables[1].items():
            gvs_df = gvs_tables.setdefault(vio_typ_name, pd.DataFrame(columns=['name', 'wns', 'nvp']))
            for vio_grp_name, vio_grp_df in vio_typ_dict.items():
                wns = vio_grp_df['slack'].min()
                nvp = vio_grp_df.shape[0]
                if vio_grp_name in gvs_df.index:
                    gvs_df.loc[vio_grp_name, 'name'] = vio_grp_name
                    gvs_df.loc[vio_grp_name, 'wns':'nvp'] = [wns, nvp] - gvs_df.loc[vio_grp_name, 'wns':'nvp']
                else:
                    name = vio_grp_name + ' ->'
                    gvs_df.loc[vio_grp_name] = [name, wns, nvp]

    for vio_typ_name, gvs_df in gvs_tables.items():
        print(f"\n--- {vio_typ_name}")
        print('=' * divider_size)
        show_header(header_just, header_lens, header_list)
        print('=' * divider_size)
        for i in range(gvs_df.shape[0]):
            show_header(header_just, header_lens, list(gvs_df.iloc[i].apply(str)))

    print()
#}}}

def print_table(vio_tables: list):
    """Print Table"""  #{{{
    for rid, vio_rpt_dt in enumerate(vio_tables):
        print(f"report id: {rid}")
        for vio_typ_name, vio_typ_dt in vio_rpt_dt.items():
            print(f"vio_type: {vio_typ_name}")
            for vio_grp_name, vio_grp_df in vio_typ_dt.items():
                print(f"group name: {vio_grp_name}")
                print(vio_grp_df, end='\n\n')
#}}}

def show_header(just_type: list, header_lens: list, header_list: list):
    """Show header"""  #{{{
    for i, head in enumerate(header_list):
        if just_type[i] == 'l':
            print("{}".format(head.split('/')[0].ljust(header_lens[i])), end='')
        else:
            print("{}".format(head.split('/')[0].rjust(header_lens[i])), end='')
    print()

    try:
        for i, head in enumerate(header_list):
            if just_type[i] == 'l':
                print("{}".format(head.split('/')[1].ljust(header_lens[i])), end='')
            else:
                print("{}".format(head.split('/')[1].rjust(header_lens[i])), end='')
        print()
    except:
        pass
#}}}

### Main Function ###

def create_argparse() -> argparse.ArgumentParser:
    """Create Argument Parser"""  #{{{
    parser = argparse.ArgumentParser(
                formatter_class=argparse.RawTextHelpFormatter,
                description="PrimeTime Report Analysis")

    subparsers = parser.add_subparsers(dest='proc_mode', required=True, help="select one of process modes.")
    parser.add_argument('-version', action='version', version=VERSION)
    parser.add_argument('-flt_type', dest='filter_type', metavar='<and|or>', default='and', 
                                    choices=['and', 'or'], help="filter type")
    parser.add_argument('-gt', dest='gt', metavar='<value>', type=float, help="filter operator (x > value)")
    parser.add_argument('-lt', dest='lt', metavar='<value>', type=float, help="filter operator (x < value)")
    parser.add_argument('-ge', dest='ge', metavar='<value>', type=float, help="filter operator (x >= value)")
    parser.add_argument('-le', dest='le', metavar='<value>', type=float, help="filter operator (x <= value)")
    parser.add_argument('-eq', dest='eq', metavar='<value>', type=float, help="filter operator (x == value)")

    # violation group summary
    parser_norm = subparsers.add_parser('gvs', help='group violation summary from constraint violation report')
    parser_norm.add_argument('rpt_fn', help="area report path 1 (base)") 
    parser_norm.add_argument('rpt_fn2', nargs='?', help="area report path 2 (diff with base)") 

    return parser
#}}}

def main():
    """Main Function"""  #{{{

    parser = create_argparse()
    args = parser.parse_args()

    if args.proc_mode == 'gvs':
        rpt_fps = [args.rpt_fn, args.rpt_fn2] if args.rpt_fn2 else [args.rpt_fn]
        vio_tables = load_vio_rpt(rpt_fps)
        report_gvs(vio_tables)
#}}}

if __name__ == '__main__':
    main()
