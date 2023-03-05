#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-only
#
# Compare table generator for IP flatten flow
#
# Copyright (C) 2023 Yeh, Hsin-Hsien <yhh76227@gmail.com>
#

import argparse 
import gzip
import os
import sys
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.formatting.rule import CellIsRule

### Global Setting ###   {{{

IP_FLAT_RPT_NAME = 'ip_flat_boundary_timing.brief'

CORNER_MAP = {
    'NORMAL_FFGNP_0p88v_125c_CBEST_125c_HOLD_'      : '0p88v_cbest_125c_hold',
    'NORMAL_FFGNP_0p88v_125c_CWORST_125c_HOLD_'     : '0p88v_cworst_125c_hold',
    'NORMAL_FFGNP_0p88v_125c_RCBEST_125c_HOLD_'     : '0p88v_rcbest_125c_hold',
    'NORMAL_FFGNP_0p88v_125c_RCWORST_125c_HOLD_'    : '0p88v_rcworst_125c_hold',
    'NORMAL_FFGNP_0p88v_m40c_CBEST_m40c_HOLD_'      : '0p88v_cbest_m40c_hold',
    'NORMAL_FFGNP_0p88v_m40c_CWORST_m40c_HOLD_'     : '0p88v_cworst_m40c_hold',
    'NORMAL_FFGNP_0p88v_m40c_RCBEST_m40c_HOLD_'     : '0p88v_rcbest_m40c_hold',
    'NORMAL_FFGNP_0p88v_m40c_RCWORST_m40c_HOLD_'    : '0p88v_rcworst_m40c_hold',
    'NORMAL_SSGNP_0p72v_125c_CWORST_125c_HOLD_'     : '0p72v_cworst_125c_hold',
    'NORMAL_SSGNP_0p72v_125c_CWORST_T_125c_SETUP_'  : '0p72v_cworst_t_125c_setup',
    'NORMAL_SSGNP_0p72v_125c_RCWORST_125c_HOLD_'    : '0p72v_rcworst_125c_hold',
    'NORMAL_SSGNP_0p72v_125c_RCWORST_T_125c_SETUP_' : '0p72v_rcworst_t_125c_setup',
    'NORMAL_SSGNP_0p72v_m40c_CWORST_m40c_HOLD_'     : '0p72v_cworst_m40c_hold',
    'NORMAL_SSGNP_0p72v_m40c_CWORST_T_m40c_SETUP_'  : '0p72v_cworst_t_m40c_setup',
    'NORMAL_SSGNP_0p72v_m40c_RCWORST_m40c_HOLD_'    : '0p72v_rcworst_m40c_hold',
    'NORMAL_SSGNP_0p72v_m40c_RCWORST_T_m40c_SETUP_' : '0p72v_rcworst_t_m40c_setup',
}

STATUS_FORMULA = {
    'total_chk' : '=IF(OR(C{0}<>"", D{0}<>"", $E{0}<>"", F{0}<>""), 1, 0)',
    'fatal_chk' : '=IF(AND(H{0}="inf", I{0}="inf"), "na", ' +
                   'IF(H{0}="inf", "", ' +
                   'IF(OR(H{0}<0, I{0}<0), "x", ' +
                   'IF(AND(J{0}<>"na", J{0}>-0.001, J{0}<0.1), "v", ""))))',
    'high_warn' : '=IF(AND(J{0}<>"na", J{0}<=-0.1), "x", "")',
    'low_warn'  : '=IF(AND(J{0}<>"na", J{0}>-0.1, J{0}<=-0.001), "x", ' +
                   'IF(AND(J{0}<>"na", J{0}>0.1), "c", ""))',
    'user_chk'  : ''
}

HELP_MSG = (
    "Fatal Error : post-flatten or pre-flatten slack < 0ps.",
    "High Warn : slack difference <= -100ps.",
    "Low Warn (x) : -100ps < slack difference < -0.001ps.",
    "Low Warn (c) : slack difference >= 100ps (maybe need check).",
    ""
)

#}}}

### Parameter ###   {{{

CS_THP, CS_CKG = range(2)
PT_ARL, PT_SLK, PT_CKG = range(3)
SETUP, HOLD = range(2)

RED_FONT1 = Font(color='ffcc0000')
GREEN_FONT1 = Font(color='ff006600')
YELLOW_FONT1 = Font(color='ff996600')

RED_FILL1 = PatternFill(fill_type='solid', start_color='ffffcccc')
PURPLE_FILL1 = PatternFill(fill_type='solid', start_color='ffdedce6')
GREEN_FILL1 = PatternFill(fill_type='solid', start_color='ff92d050')
GREEN_FILL2 = PatternFill(fill_type='solid', start_color='ffccffcc')
YELLOW_FILL1 = PatternFill(fill_type='solid', start_color='ffffffcc')

THIN_BLACK_SIDE = Side(border_style='thin', color='ff000000')
THIN_GREY_SIDE = Side(border_style='thin', color='ff808080')
AR_BORDER1 = Border(left=THIN_BLACK_SIDE, right=THIN_BLACK_SIDE, top=THIN_BLACK_SIDE, bottom=THIN_BLACK_SIDE)
AR_BORDER2 = Border(left=THIN_GREY_SIDE, right=THIN_GREY_SIDE, top=THIN_GREY_SIDE, bottom=THIN_GREY_SIDE)

LC_ALIGN = Alignment(horizontal='left', vertical='center', wrapText=True)
CC_ALIGN = Alignment(horizontal='center', vertical='center', wrapText=True)
RC_ALIGN = Alignment(horizontal='right', vertical='center', wrapText=True)

STS_CHK = CellIsRule(operator='==', formula=[1], font=GREEN_FONT1, fill=GREEN_FILL2)
STS_WAIT = CellIsRule(operator='==', formula=[0], font=RED_FONT1, fill=RED_FILL1)
CHK_FAIL = CellIsRule(operator='==', formula=['"x"'], font=RED_FONT1, fill=RED_FILL1)
CHK_RSV = CellIsRule(operator='==', formula=['"c"'], font=YELLOW_FONT1, fill=YELLOW_FILL1)

#}}}

### Function ###

def load_timing_report(rpt_fp, col_sz: list) -> dict:
    """Load Timing Report"""  #{{{
    table = {}
    with open(rpt_fp, 'r') as f:
        for line in f:
            line = line.strip()

            if line.startswith('#'):
                pass
            elif line != '':
                tok_list = line.split(',')
                thpoint = tok_list[0].strip()
                arrival = tok_list[1].strip()
                slack = tok_list[3].strip()
                ckgroup = tok_list[5].strip()

                if arrival == 'INFINITY' or arrival == 'NA':
                    arrival_f = "inf"
                else:
                    arrival_f = float(arrival)

                if slack == 'INFINITY' or slack == 'NA':
                    slack_f = "inf"
                else:
                    slack_f = float(slack)

                table[thpoint] = (arrival_f, slack_f, ckgroup)

                size = len(thpoint)
                if size > col_sz[CS_THP]:
                    col_sz[CS_THP] = size

                size = len(ckgroup)
                if size > col_sz[CS_CKG]:
                    col_sz[CS_CKG] = size

    return table
#}}}

def report_dump_xls (ws: openpyxl.worksheet, post_rpt: dict, pre_rpt: dict, corner: str):
    """Dump Compare Table"""  #{{{
    post_cnt, pre_cnt = len(post_rpt), len(pre_rpt)
    if post_cnt != pre_cnt:
        print("WARNING: Number of report paths is not equal.")
        print("INFO: Corner: {}".format(corner))
        print("INFO: (Post, Pre) = ({}, {})".format(post_cnt, pre_cnt))

    rid = 1
    status = ('ID', 'Total\nCheck', 'Fatal\nCheck', 'High\nWarn', 'Low\nWarn', 'User\nCheck')

    status_cnt = len(status)
    for cid in range(1, status_cnt+1):
        cell = ws.cell(rid, cid)
        cell.fill = PURPLE_FILL1
        cell.alignment = CC_ALIGN
        cell.border = AR_BORDER1 

    data_st = rid + 2 
    data_ed = post_cnt + 2 

    ws[f'A{rid}'] = f'=A{data_ed}+1'
    ws[f'B{rid}'] = f'=SUM(B{data_st}:B{data_ed})'
    ws[f'C{rid}'] = f'=COUNTIF(C{data_st}:C{data_ed}, "="&"x")'
    ws[f'D{rid}'] = f'=COUNTIF(D{data_st}:D{data_ed}, "="&"x")'
    ws[f'E{rid}'] = f'=COUNTIF(E{data_st}:E{data_ed}, "="&"x")'
    ws[f'F{rid}'] = f'=COUNTIF(F{data_st}:F{data_ed}, "="&"x")'

    rid += 1
    for cid, title in enumerate(status, 1):
        cell = ws.cell(rid, cid, title)
        cell.fill = GREEN_FILL1
        cell.border = AR_BORDER1 
        cell.alignment = CC_ALIGN

    ws.row_dimensions[rid].height = 24

    ws.conditional_formatting.add(f'B{data_st}:B{data_ed}',
            CellIsRule(operator='==', formula=[1], font=GREEN_FONT1, fill=GREEN_FILL2))
    ws.conditional_formatting.add(f'B{data_st}:B{data_ed}',
            CellIsRule(operator='==', formula=[0], font=RED_FONT1, fill=RED_FILL1))
    ws.conditional_formatting.add(f'C{data_st}:F{data_ed}',
            CellIsRule(operator='==', formula=['"x"'], font=RED_FONT1, fill=RED_FILL1))
    ws.conditional_formatting.add(f'C{data_st}:F{data_ed}',
            CellIsRule(operator='==', formula=['"c"'], font=YELLOW_FONT1, fill=YELLOW_FILL1))
    ws.conditional_formatting.add(f'H{data_st}:J{data_ed}',
            CellIsRule(operator='<', formula=[0.0], font=RED_FONT1, fill=RED_FILL1))
    ws.conditional_formatting.add(f'K{data_st}:K{data_ed}',
            CellIsRule(operator='==', formula=['"x"'], font=RED_FONT1, fill=RED_FILL1))

    ws.column_dimensions['H'].width = 10 
    ws.column_dimensions['I'].width = 10 
    ws.column_dimensions['J'].width = 10 
    ws.column_dimensions['K'].width = 10 
    ws.column_dimensions['G'].width = 24 
    ws.column_dimensions['L'].width = 30 
    ws.column_dimensions['M'].width = 30 

    items = ('Throughpoint', 'Slack\npostFlat', 'Slack\npreFlat', 'Slack\nDiff', 
             'Group\nSame', 'Dir/CKin/CKout (postFlat)', 'Dir/CKin/CKout (preFlat)')

    for cid, title in enumerate(items, start=7):
        cell = ws.cell(rid, cid, title)
        cell.fill = GREEN_FILL1
        cell.border = AR_BORDER1
        cell.alignment = LC_ALIGN

    rid += 1
    for thp, post_val in post_rpt.items():
        try:
            pre_val = pre_rpt[thp]
        except KeyError:
            print("WARNING: Cannot find the path in pre-flatten report")
            print("INFO: Corner: {}".format(corner))
            print("INFO: Throughpoint: {}".format(thp))
            pre_val = (thp, "inf", "inf", '<NA|NA|NA>')

        value_list = (rid - data_st, 
                      STATUS_FORMULA['total_chk'].format(rid), 
                      STATUS_FORMULA['fatal_chk'].format(rid), 
                      STATUS_FORMULA['high_warn'].format(rid), 
                      STATUS_FORMULA['low_warn'].format(rid), 
                      STATUS_FORMULA['user_chk'].format(rid), 
                      thp,
                      post_val[PT_SLK],
                      pre_val[PT_SLK],
                      '=IF(OR(H{0}="inf", I{0}="inf"), "na", H{0}-I{0})'.format(rid),
                      'o' if post_val[PT_CKG] == pre_val[PT_CKG] else 'x',
                      post_val[PT_CKG],
                      pre_val[PT_CKG])

        for cid, value in enumerate(value_list, start=1): 
            cell = ws.cell(rid, cid, value)
            cell.border = AR_BORDER2
            if cid <= 6 or cid == 11:
                cell.alignment = CC_ALIGN
            elif 8 <= cid <= 10:
                cell.alignment = RC_ALIGN
                cell.number_format = "0.0000"

        rid += 1

    ws.auto_filter.ref = f"A{data_st-1}:M{data_ed}"
#}}}

### Main ###

def create_argparse() -> argparse.ArgumentParser:
    """Create Argument Parser"""  #{{{
    parser = argparse.ArgumentParser(
                formatter_class=argparse.RawTextHelpFormatter,
                description="Compare table generator for IP flatten flow")

    parser.add_argument('-dmsa', dest='is_dmsa', action='store_true', help="DMSA mode")
    parser.add_argument('-f', dest='is_force', action='store_true', help="output force write")
    parser.add_argument('post_flat_dir', help="primetime report directory (post-flatten)") 
    parser.add_argument('pre_flat_dir', help="primetime report directory (pre-flatten)") 
    parser.add_argument('out_fn', help="output table name (format: xlsx)")

    return parser
#}}}

def main():
    """Main Function"""  #{{{
    parser = create_argparse()
    args = parser.parse_args()

    post_dir = Path(args.post_flat_dir)
    pre_dir = Path(args.pre_flat_dir)

    if args.is_dmsa:
        post_fp = list(post_dir.glob(f'*/{IP_FLAT_RPT_NAME}'))
        pre_fp = list(pre_dir.glob(f'*/{IP_FLAT_RPT_NAME}'))
        corner = [x.name for x in post_dir.iterdir()]
    else:
        post_fp = [post_dir / IP_FLAT_RPT_NAME]
        pre_fp = [pre_dir / IP_FLAT_RPT_NAME]
        corner = ['single']

    post_cnt = len(post_fp)
    pre_cnt = len(pre_fp)

    if post_cnt != pre_cnt:
        print("ERROR: number of reports is mismatch")
        print("INFO: Post count: {}".format(post_cnt))
        print("INFO: Pre count: {}".format(pre_cnt))
        return
    elif post_cnt == 0:
        print("ERROR: cannot find timing report")
        return 

    out_fn = args.out_fn if args.out_fn.endswith('.xlsx') else args.out_fn + '.xlsx'
    out_path = Path(out_fn)

    if out_path.exists() and not args.is_force:
        if input(f"{out_fn} existed, overwrite? (y/n) ").lower() != 'y':
            print('Terminal')
            return 

    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    for i in range(len(post_fp)):
        try:
            tab = CORNER_MAP[corner[i]]
        except KeyError:
            tab = corner[i]

        col_sz = [0, 0]
        post_rpt = load_timing_report(post_fp[i], col_sz) 
        pre_rpt = load_timing_report(pre_fp[i], col_sz)

        ws = wb.create_sheet(title=tab)
        report_dump_xls(ws, post_rpt, pre_rpt, corner[i])

    ws = wb.create_sheet(title="help")
    for i, msg in enumerate(HELP_MSG, start=1):
        ws.cell(i, 1, msg)

    wb.save(out_path)
#}}}

if __name__ == '__main__':
    main()

