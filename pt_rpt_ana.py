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

from .utils.general import VERSION

### Global Function ###

## for cons {{{
ofs_re = re.compile(r"(\w:)(.+)")
ofs_ta = set(('s:',))

cmp_re = re.compile(r"(\w:\w{3})([><=]{1,2})(.+)")
cmp_ta = set(('w:wns', 'w:tns', 'w:nvp', 'r:slk', 'd:slk'))
cmp_op = {
    '>' : lambda a, b: a > b,
    '<' : lambda a, b: a < b,
    '==': lambda a, b: a == b,
    '>=': lambda a, b: a >= b,
    '<=': lambda a, b: a <= b
}

vio_types = (
    'max_delay/setup', 'min_delay/hold', 
    'recovery', 'removal', 'clock_gating_setup', 'clock_gating_hold', 
    'max_capacitance', 'min_capacitance', 'max_transition', 'min_transition',
    'clock_tree_pulse_width', 'sequential_tree_pulse_width', 'sequential_clock_min_period'
)

clk_vio = (
    'clock_tree_pulse_width', 
    'sequential_tree_pulse_width', 
    'sequential_clock_min_period'
)

group_vio = ('max_delay/setup', 'min_delay/hold')
#}}}

## for time2 {{{
prange_re1 = re.compile(r"(\d+)\+(\d+)")
prange_re2 = re.compile(r"(\d+)-(\d+)")
path_re = re.compile(r"\s*\S+")
dps_tag = {'T': 'T', 'S': 'S'}

TIME_COL_NUM = 10
PT, PHY, FO, CAP, DTRAN, TRAN, DERATE, DELTA, INCR, PATH = range(TIME_COL_NUM)
col_dict = {'net': FO, 'cap': CAP, 'dtran': DTRAN, 'tran': TRAN, 'derate': DERATE, 'delta': DELTA}
ANNO_SYM = set(['H', '^', '*', '&', '$', '+', '@'])

# clock pin
CKP = set(['CP', 'CPN'])    # TSMC
CKP.add('CK')               # SYNP virage

# Histogram
HIST_DEFAULT_COLOR = "#caccd1"
HIST_PALETTE = [
    "#84bd00", "#efdf00", "#fe5000", "#e4002b", 
    "#da1884", "#a51890", "#0077c8", "#008eaa", 
    "#74d2e7", "#48a9c5", "#0085ad", "#8db9ca", 
    "#4298b5", "#005670", "#00205b",
]
#}}}

### Function for 'report_constraint' ###

def load_cons_cfg(cfg_fp) -> tuple:
    """Load Configuration for Cons Mode"""  #{{{
    #
    # Config Data Structure:
    #
    # cons_cfg = {
    #   'g': {'vtype1:grp1': [[(ln, tar, op, val), ...], [...], [...]], 
    #         'vtype1:grp2': [[(ln, tar, op, val), ...], [...], [...]], 
    #         'vtype1:'    : {'rgrp1': [[(ln, tar, op, val), ...], [...], [...]],
    #                         'rgrp2': [[(ln, tar, op, val), ...], [...], [...]]}, 
    #         'vtype2:grp1': [[(ln, tar, op, val), ...], [...], [...]], ...},
    #
    #   'p': {'vtype1:grp1:ins1': [[(ln, tar, op, val), ...], [...]],
    #         'vtype1:grp1:ins2': [[(ln, tar, op, val), ...], [...]],
    #         'vtype1::ins3'    : [[(ln, tar, op, val), ...], [...]],
    #         'vtype1:grp1:'    : {'rins1': [[(ln, tar, op, val), ...], [...]],
    #                              'rins2': [[(ln, tar, op, val), ...], [...]]}, ...}
    #         'vtype1::'        : {'rins1': [[(ln, tar, op, val), ...], [...]],
    #                              'rins2': [[(ln, tar, op, val), ...], [...]]}, ...}
    # }
    #
    # {'group': [left op], [right op], [diff op]}
    # {'path':  [left op], [right op]}
    #
    global group_vio
    grp_col_w, cons_cfg = 50, {'g': {}, 'p': {}}

    with open(cfg_fp, 'r') as f:
        for ln_no, line in enumerate(f.readlines(), start=1):
            line = line.split('#')[0].strip()
            if line != '':
                try:
                    if line.startswith('grp_col_width:'):
                        grp_col_w = int(line[14:])

                    elif line.startswith('g:'):
                        item, *cmd_list = line[2:].split()
                        vtype, group, rid = item.split(':') 
                        tag = f'{vtype}:{group}' if vtype in group_vio else f'{vtype}:{vtype}'
                        grp_list = cons_cfg['g'].setdefault(tag, [[], [], []])
                        parse_grp_cmd(ln_no, grp_list[int(rid)], cmd_list)

                    elif line.startswith('gr:'):
                        item, *cmd_list = line[3:].split()
                        vtype, group, rid = item.split(':') 
                        if vtype not in group_vio:
                            group = vtype
                        vtype_dict = cons_cfg['g'].setdefault(f'{vtype}:', {})
                        grp_list = vtype_dict.setdefault(group, [[], [], []])
                        parse_grp_cmd(ln_no, grp_list[int(rid)], cmd_list)

                    elif line.startswith('i:'):
                        item, *cmd_list = line[2:].split()
                        vtype, group, rid, ins = item.split(':')
                        tag = f'{vtype}:{group}:{ins}' if vtype in group_vio else f'{vtype}:{vtype}:{ins}'
                        ins_list = cons_cfg['p'].setdefault(tag, [[], []])
                        if rid == '2':
                            parse_ins_cmd(ins_list[0], cmd_list)
                            parse_ins_cmd(ins_list[1], cmd_list)
                        else:
                            parse_ins_cmd(ins_list[int(rid)], cmd_list)

                    elif line.startswith('ir:'):
                        item, *cmd_list = line[3:].split()
                        vtype, group, rid, ins = item.split(':')
                        tag = f'{vtype}:{group}:' if vtype in group_vio else f'{vtype}:{vtype}:'
                        grp_dict = cons_cfg['p'].setdefault(tag, {})
                        ins_list = grp_dict.setdefault(ins, [[], []])
                        if rid == '2':
                            parse_ins_cmd(ins_list[0], cmd_list)
                            parse_ins_cmd(ins_list[1], cmd_list)
                        else:
                            parse_ins_cmd(ins_list[int(rid)], cmd_list)

                except SyntaxError:
                    raise SyntaxError(f"config syntax error (ln:{ln_no})")

    return grp_col_w, cons_cfg
#}}}

def parse_grp_cmd(ln_no: int, grp_list: list, cmd_list: list):
    """Parse group command"""  #{{{
    idx = 0
    while idx < len(cmd_list):
        cmd = cmd_list[idx]
        idx = idx + 1

        if cmd == '':
            continue
        elif cmd.startswith('w'):
            m = cmp_re.fullmatch(cmd)
            if m is None or m[1] not in cmp_ta:
                raise SyntaxError('PGC-001')
            else:
                grp_list.append((ln_no, m[1], m[2], float(m[3])))
#}}}

def grp_cons_check(rid: int, values: list, cons_list: list, comm: str, cond_set: set) -> str:
    """Group Config Check"""  #{{{
    for cons in cons_list:
        if cons[1] == 'w:wns':
            opd_a = values[0]
        elif cons[1] == 'w:tns':
            opd_a = values[1]
        elif cons[1] == 'w:nvp':
            opd_a = values[2]

        if cmp_op[cons[2]](opd_a, cons[3]):
            cid = cons[1][0] + str(cons[0])
            comm += f"{cid},"
            if rid is None:
                cond_set.add("{0:8}{1[1]}{1[2]}{1[3]}".format(f"{cid}:", cons))
            else:
                cond_set.add("{0:8}{1}:{2[1]}{2[2]}{2[3]}".format(f"{cid}:", rid, cons))

    return comm
#}}}

def parse_ins_cmd(ins_list: list, cmd_list: list):
    """Parse instance command"""  #{{{
    idx = 0
    while idx < len(cmd_list):
        cmd = cmd_list[idx]
        idx = idx + 1

        if cmd == '':
            continue

        elif cmd == 'r' or cmd == 'd':
            ins_list.append(cmd)

        elif cmd.startswith('s'):
            m = ofs_re.fullmatch(cmd)
            if m is None or m[1] not in ofs_ta:
                raise SyntaxError('PIC-001')
            else:
                ins_list.append((m[1], float(m[2])))

        elif cmd.startswith('r') or cmd.startswith('d'):
            m = cmp_re.fullmatch(cmd)
            if m is None or m[1] not in cmp_ta:
                raise SyntaxError('PIC-002')
            else:
                ins_list.append((m[1], m[2], float(m[3])))
#}}}

def ins_cons_check(slack: float, cons_list: list) -> (bool, float):
    """Instance Config Check"""  #{{{
    off, is_active, is_rsv, is_del = 0.0, False, False, False
    rsv_slk, del_slk = (False, None), (False, None)

    for cons in cons_list:
        if cons[0] == 's:':
            off = float(cons[1])
        elif cons[0] == 'r':
            is_rsv = True
        elif cons[0] == 'r:slk':
            rsv_slk = True, cons
        elif cons[0] == 'd':
            is_del = True
        elif cons[0] == 'd:slk':
            del_slk = True, cons

    if not is_rsv and rsv_slk[0]:
        is_rsv = cmp_op[rsv_slk[1][1]](slack, rsv_slk[1][2])
    if not is_del and del_slk[0]:
        is_del = cmp_op[del_slk[1][1]](slack, del_slk[1][2])

    is_active = not is_del or is_rsv
    slack += off

    return is_active, slack
#}}}

def report_cons_brief(rpt_fps: list, cfg_fp: str):
    """Brief for 'report_constraint'"""  #{{{
    #
    # Summary Data Structure:
    #
    # summary(multi) = {'vtype1': {'grp1': [(wns, tns, nvp), (wns, tns, nvp)],
    #                              'grp2': [(wns, tns, nvp), (wns, tns, nvp)], ...},
    #                   'vtype2': {...}, ...}
    #
    # summary(single) = {'vtype1': {'grp1': [(wns, tns, nvp)],
    #                               'grp2': [(wns, tns, nvp)], ...},
    #                    'vtype2': {...}, ...}
    #
    global vio_types, group_vio 

    if cfg_fp is not None:
        grp_col_w, cons_cfg = load_cons_cfg(cfg_fp)
        # print(cons_cfg)
    else:
        grp_col_w, cons_cfg = 50, {'g': {}, 'p': {}}

    IDLE, POS, VT1, VT2 = range(4)
    is_multi = len(rpt_fps) > 1
    stage, summary = IDLE, {}

    for fid, rpt_fp in enumerate(rpt_fps):
        if os.path.splitext(rpt_fp)[1] == '.gz':
            f = gzip.open(rpt_fp, mode='rt')
        else:
            f = open(rpt_fp)

        for line in f:
            toks = line.split()
            toks_len = len(toks)

            if stage == IDLE and toks_len != 0 and toks[0] in vio_types:
                stage, vtype, wns, tns, nvp = POS, toks[0], 0.0, 0.0, 0
                group = toks[1][2:-1] if vtype in group_vio else vtype
                item = []

            elif stage == POS and toks_len != 0:
                if toks[0].startswith('---'):
                    vtype_dict = summary.setdefault(vtype, {})
                    if vtype in clk_vio and pre_toks[-1] == 'Clock':
                        stage = VT2
                        group = ""
                    else:
                        stage = VT1 
                        if is_multi:
                            group_list = vtype_dict.setdefault(group, [(0.0, 0.0, 0), (0.0, 0.0, 0)])
                        else:
                            group_list = vtype_dict.setdefault(group, [(0.0, 0.0, 0)])
                else:
                    pre_toks = toks.copy()

            elif stage == VT1:
                ## type: <endpoint> [scenario] <required delay> <actual delay> <slack>
                if toks_len != 0:
                    item.extend(toks)
                    if item[-1] == '(VIOLATED)':
                        is_active, slack = True, float(item[-2])
                        if len(cons_cfg['p']) != 0:
                            tag = f'{vtype}:{group}:{item[0]}'
                            if is_active and tag in cons_cfg['p']:
                                is_active, slack = ins_cons_check(slack, cons_cfg['p'][tag][fid])
                            tag = f'{vtype}::{item[0]}'
                            if is_active and tag in cons_cfg['p']:
                                is_active, slack = ins_cons_check(slack, cons_cfg['p'][tag][fid])
                            tag = f'{vtype}:{group}:'
                            if is_active and tag in cons_cfg['p']:
                                for ipat, inst_list in cons_cfg['p'][tag].items():
                                    if re.fullmatch(ipat, item[0]):
                                        is_active, slack = ins_cons_check(slack, inst_list[fid])
                                        break
                            tag = f'{vtype}::'
                            if is_active and tag in cons_cfg['p']:
                                for ipat, inst_list in cons_cfg['p'][tag].items():
                                    if re.fullmatch(ipat, item[0]):
                                        is_active, slack = ins_cons_check(slack, inst_list[fid])
                                        break
                        if is_active:
                            tns += slack 
                            nvp += 1
                            if slack < wns:
                                wns = slack
                        item = []
                else:
                    group_list[fid] = (wns, tns, nvp)
                    stage = IDLE

            elif stage == VT2:
                ## type: <endpoint> [scenario] <required delay> <actual delay> <slack> <clock>
                if toks_len != 0:
                    item.extend(toks)
                    if item[-2] == '(VIOLATED)':
                        if group != item[-1]:
                            if group != "":
                                group_list[fid][0] += wns
                                group_list[fid][1] += tns
                                group_list[fid][2] += nvp
                                wns, tns, nvp = 0.0, 0.0, 0
                            group = item[-1]

                            if is_multi:
                                group_list = vtype_dict.setdefault(group, [[0.0, 0.0, 0], [0.0, 0.0, 0]])
                            else:
                                group_list = vtype_dict.setdefault(group, [[0.0, 0.0, 0]])

                        is_active, slack = True, float(item[-3])

                        if len(cons_cfg['p']) != 0:
                            tag = f'{vtype}:{group}:{item[0]}'
                            if is_active and tag in cons_cfg['p']:
                                is_active, slack = ins_cons_check(slack, cons_cfg['p'][tag][fid])
                            tag = f'{vtype}::{item[0]}'
                            if is_active and tag in cons_cfg['p']:
                                is_active, slack = ins_cons_check(slack, cons_cfg['p'][tag][fid])
                            tag = f'{vtype}:{group}:'
                            if is_active and tag in cons_cfg['p']:
                                for ipat, inst_list in cons_cfg['p'][tag].items():
                                    if re.fullmatch(ipat, item[0]):
                                        is_active, slack = ins_cons_check(slack, inst_list[fid])
                                        break
                            tag = f'{vtype}::'
                            if is_active and tag in cons_cfg['p']:
                                for ipat, inst_list in cons_cfg['p'][tag].items():
                                    if re.fullmatch(ipat, item[0]):
                                        is_active, slack = ins_cons_check(slack, inst_list[fid])
                                        break
                        if is_active:
                            tns += slack 
                            nvp += 1
                            if slack < wns:
                                wns = slack
                        item = []
                else:
                    group_list[fid][0] += wns
                    group_list[fid][1] += tns
                    group_list[fid][2] += nvp
                    stage = IDLE

        f.close()

    if True:
        print()
        if is_multi:
            print("Report(left):  {}".format(os.path.abspath(rpt_fps[0])))
            print("Report(right): {}".format(os.path.abspath(rpt_fps[1])))
            print()
            print("Information:   Diff = Left - Right")
        else:
            print("Report:  {}".format(os.path.abspath(rpt_fps[0])))
        print()

        cond_set = set()
        for vtype, vtype_dict in summary.items():
            eq_cnt = grp_col_w + 40
            print("==== {}".format(vtype))
            if is_multi:
                eq_cnt += 80
                print("  {}+{:=^39}+{:=^39}+{:=^39}+".format('=' * grp_col_w, ' Left ', ' Right ', ' Diff '))
                print("  {}".format('Group'.ljust(grp_col_w)), end='')
                print("| {:16}{:16}{:6}".format('WNS', 'TNS', 'NVP'), end='')
                print("| {:16}{:16}{:6}".format('WNS', 'TNS', 'NVP'), end='')
                print("| {:16}{:16}{:6}".format('WNS', 'TNS', 'NVP'), end='')
                print("|")
                print('  ', '=' * eq_cnt, '+', sep='')

                for group, group_list in vtype_dict.items():
                    comm, tag1, tag2 = '', f'{vtype}:{group}', f'{vtype}:'
                    print("  {}".format(group.ljust(grp_col_w)), end='')
                    for rid, values in enumerate(group_list):
                        print("| {0[0]:< 16.4f}{0[1]:< 16.4f}{0[2]:<6}".format(values), end='')
                        if tag1 in cons_cfg['g']:
                            comm = grp_cons_check(rid, values, cons_cfg['g'][tag1][rid], comm, cond_set)
                        if tag2 in cons_cfg['g']:
                            for gpat, group_list in cons_cfg['g'][tag2].items():
                                if re.fullmatch(gpat, group):
                                    comm = grp_cons_check(rid, values, group_list[rid], comm, cond_set)

                    diff_values = [group_list[0][0] - group_list[1][0]]
                    diff_values.append(group_list[0][1] - group_list[1][1])
                    diff_values.append(group_list[0][2] - group_list[1][2])
                    print("| {0[0]:<+16.4f}{0[1]:<+16.4f}{0[2]:<+6}|".format(diff_values), end='')

                    if tag1 in cons_cfg['g']:
                        comm = grp_cons_check(2, diff_values, cons_cfg['g'][tag1][2], comm, cond_set)
                    if tag2 in cons_cfg['g']:
                        for gpat, group_list in cons_cfg['g'][tag2].items():
                            if re.fullmatch(gpat, group):
                                comm = grp_cons_check(2, diff_values, group_list[2], comm, cond_set)
                    if comm != '':
                        print(f" ({comm[:-1]})")
                    else:
                        print()
            else:
                print("  {}  {:16}{:16}{:6}".format('Group'.ljust(grp_col_w), 'WNS', 'TNS', 'NVP'))
                print('  ', '=' * eq_cnt, sep='')
                for group, group_list in vtype_dict.items():
                    values = group_list[0]
                    print("  {}".format(group.ljust(grp_col_w)), end='')
                    print("  {0[0]:< 16.4f}{0[1]:< 16.4f}{0[2]:<6}".format(values), end='')

                    comm, tag = '', f'{vtype}:{group}'
                    if tag in cons_cfg['g']:
                        comm = grp_cons_check(None, values, cons_cfg['g'][tag][0], comm, cond_set)
                    tag = f'{vtype}:'
                    if tag in cons_cfg['g']:
                        for gpat, group_list in cons_cfg['g'][tag].items():
                            if re.fullmatch(gpat, group):
                                comm = grp_cons_check(None, values, group_list[0], comm, cond_set)
                    if comm != '':
                        print(f" ({comm[:-1]})")
                    else:
                        print()
            print()

        if len(cond_set) != 0:
            print("\n[Condition]\n")
            for cond in cond_set:
                print(f"  {cond}")
            print()
#}}}

### Function for 'report_time' ###

def load_time_cfg(cfg_fp) -> dict:
    """Load Configuration for Time Mode"""  #{{{
    #
    # Config Data Structure:
    #
    # cons_cfg = {
    #   'ps': [(tag1, regex_pattern1), (tag2, regex_pattern2), ...]
    # }
    #
    global dps_tag
    cons_cfg = {}

    with open(cfg_fp, 'r') as f:
        for no, line in enumerate(f.readlines(), start=1):
            line = line.split('#')[0].strip()
            if line != "":
                try:
                    if line.startswith('ps:'):
                        tag, pat = line[3:].split()
                        ps_dict = cons_cfg.setdefault('ps', {})
                        ps_dict[tag] = re.compile(pat)
                    elif line.startswith('dps:'):
                        tag, pat = line[4:].split()
                        dps_tag[pat] = tag
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
        cons_cfg = load_time_cfg(cfg_fp)
    else:
        cons_cfg = None

    ST, ED, GR, TY, SL = range(5)
    stage, path = ST, {}
    print("Group  Type  Slack  Endpoint  Startpoint")
    print("==================================================")

    ln_no, line = 1, f.readline()
    while line:
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
        elif stage == SL and line[:9] == "  slack (":
            stage = ST
            toks = line.split()
            if toks[1] != '(MET)' or is_all:
                print(path['group'], path['type'], toks[-1], path['end'], path['start'], end='')
                print(" line:{}".format(path['no']))
        ln_no += 1
        line = f.readline()
    f.close()
#}}}

def parse_time_rpt(rpt_fp, prange_list: list) -> dict:
    """Parsing Timing Report"""  #{{{
    if os.path.splitext(rpt_fp)[1] == '.gz':
        fp = gzip.open(rpt_fp, mode='rt')
    else:
        fp = open(rpt_fp)

    no, opt_set = get_time_opt_set(fp)
    time_rpt_dict = {'opt': opt_set, 'path': []}

    for prange in prange_list:
        rec_cnt, is_ongo = 0, True
        p_st = prange[0] - 1
        while no < p_st:
            line, no = fp.readline(), no + 1

        while is_ongo:
            no, path, is_eof = get_time_path(fp, no, opt_set)
            if is_eof:
                break
            else:
                rec_cnt += 1
            if path is not None:
                time_rpt_dict['path'].append(path)
            if prange[1] is not None and no >= prange[1]:
                is_ongo = False
            elif prange[2] is not None and rec_cnt == prange[2]:
                is_ongo = False

    fp.close()
    return time_rpt_dict
#}}}

def get_time_opt_set(fp) -> tuple:
    """Get Option Set"""  #{{{
    ## return: (read_ln_num, option_set)
    is_ongo, opt_set = False, set()
    line, no = fp.readline(), 1

    while line:
        line = line.strip()
        if is_ongo:
            toks = line.split()
            if toks[0][0] == '*':
                break
            elif toks[0] == '-path_type':
                if toks[1] == 'full':
                    opt_set.add('pf')
                elif toks[1] == 'full_clock':
                    opt_set.add('pfc')
                elif toks[1] == 'full_clock_expanded':
                    opt_set.add('pfce')
            elif toks[0] == '-input_pins':
                opt_set.add('input')
            elif toks[0] == '-nets':
                opt_set.add('net')
            elif toks[0] == '-transition_time':
                opt_set.add('tran')
            elif toks[0] == '-capacitance':
                opt_set.add('cap')
            elif toks[0] == '-show_delta' or toks[0] == '-crosstalk_delta':
                opt_set.add('delta')
            elif toks[0] == '-derate':
                opt_set.add('derate')
        elif line[:6] == "Report":
            is_ongo = True
        line, no = fp.readline(), no + 1

    if 'tran' in opt_set and 'delta' in opt_set:
        opt_set.add('dtran')

    return no, opt_set
#}}}

def get_time_path(fp, no: int, opt_set: set) -> tuple:
    """Parsing Timing Path"""  #{{{
    STD, PREF, LPATH, CPATH, FINAL = range(5)
    time_path, state, p_state = None, STD, 0
    is_eof, line, no = False, fp.readline(), no + 1

    if line == '':
        is_eof = True

    while line != '':
        if state == LPATH or state == CPATH:
            toks = path_re.findall(line)
        else:
            toks = line.strip().split()
        # print("toks:", toks)          # debug
        # import pdb; pdb.set_trace()   # debug

        if len(toks) == 0:
            pass

        elif state == STD and toks[0] == 'Startpoint:':
            state = PREF
            time_path = {'stp': toks[1], 'lpath': [], 'cpath': []}
            if len(toks) == 2:
                toks.extend(fp.readline().strip().split())
                no += 1
            time_path['sed'] = toks[2][1:]
            time_path['sck'] = toks[-1][:-1]

        elif state == PREF:
            if toks[0][0] == '-':
                state, is_1st_cell, is_2nd_cell = LPATH, True, False
                spin, slat, sdt, ddt = None, None, 0, 0
            elif toks[0] == 'Endpoint:':
                time_path['edp'] = toks[1]
                if len(toks) == 2:
                    toks.extend(fp.readline().strip().split())
                    no += 1
                time_path['eed'] = toks[2][1:]
                time_path['eck'] = toks[-1][:-1]
            elif toks[1] == 'Group:':
                time_path['grp'] = toks[2]
            elif toks[1] == 'Type:':
                time_path['type'] = toks[2]
            elif toks[0] == 'Point':
                path_cols = path_re.findall(line)

        elif state == LPATH:
            # import pdb; pdb.set_trace()   # debug
            tag0, tag1 = toks[0].lstrip(), toks[1].lstrip()
            if tag1 == 'arrival':
                # import pdb; pdb.set_trace()   # debug
                state, p_state, edt = CPATH, 0, 0
                time_path['arr'] = float(toks[-1])
                time_path['slat'] = slat - time_path['sev']
                time_path['spin'] = spin
                if 'delta' in opt_set:
                    if 'pf' in opt_set:
                        time_path['ddt'] = ddt
                    else:
                        time_path['sdt'] = sdt
                        time_path['ddt'] = ddt - sdt

            elif tag1 == 'external':
                time_path['idly'] = float(toks[-2])

            elif p_state == 0 and tag0 == 'clock':
                if len(toks) == 4:
                    toks, no = fp.readline().strip().split(), no + 1
                time_path['sev'] = float(toks[-2])
                p_state = 1

            elif p_state == 1 and tag0 == 'clock':
                if len(toks) == 4:
                    toks, no = fp.readline().strip().split(), no + 1
                time_path['sslat'] = float(toks[-2])
                p_state = 2

            elif p_state == 2:
                # import pdb; pdb.set_trace()   # debug
                path = [None, None] + [0] * (TIME_COL_NUM - 2)
                toks_len = len(toks)
                if (toks_len == 2) or \
                   (toks_len == 3 and toks[2].endswith('<-')) or \
                   (toks_len == 4 and toks[2].endswith('(gclock')):
                    toks2, no = path_re.findall(fp.readline()), no + 1
                    start_col = 0
                else:
                    toks2 = toks
                    if (tag2:=toks[2].lstrip()) == '<-':
                        start_col = 3
                    elif tag2 == '(gclock':
                        start_col = 4
                    else:
                        start_col = 2

                if tag1 == '(net)':
                    get_time_cell(opt_set, path_cols, toks2, time_path['lpath'][-1], start_col)
                    # print("path (l-net):", time_path['lpath'][-1])  # debug
                else:
                    path[PT] = tag0
                    get_time_cell(opt_set, path_cols, toks2, path, start_col)
                    ddt += path[DELTA]
                    if (path[PT].split('/')[-1] in CKP) or (spin is None and is_2nd_cell):
                        spin, slat, sdt = path[PT], path[PATH], ddt
                    is_2nd_cell = True if is_1st_cell else False
                    is_1st_cell = False
                    time_path['lpath'].append(path)
                    # print("path (l-nor):", path)  # debug

        elif state == CPATH:
            # import pdb; pdb.set_trace()   # debug
            tag0, tag1 = toks[0].lstrip(), toks[1].lstrip()
            if tag1 == 'required':
                # import pdb; pdb.set_trace()   # debug
                state = FINAL
                time_path['req'] = float(toks[-1])
                time_path['elat'] = time_path['req'] - time_path['eev'] - \
                                    time_path['crpr'] - time_path['unc'] - time_path['odly'] - \
                                    time_path['gate'] - time_path['lib']
                if 'delta' in opt_set and 'pf' not in opt_set:
                    time_path['edt'] = edt

            elif tag1 == 'reconvergence':
                time_path['crpr'] = float(toks[-2])
            elif tag1 == 'uncertainty':
                time_path['unc'] = float(toks[-2])
            elif tag1 == 'external':
                time_path['odly'] = float(toks[-2])
            elif tag1 == 'setup' or tag1 == 'hold':
                time_path['lib'] = float(toks[-2])
            elif tag1 == 'gating':
                time_path['gate'] = float(toks[-2])

            elif p_state == 0 and tag0 == 'clock':
                # default zero
                time_path['crpr'] = 0.0
                time_path['unc']  = 0.0
                time_path['odly'] = 0.0
                time_path['lib']  = 0.0
                time_path['gate'] = 0.0
                if len(toks) == 4:
                    toks, no = fp.readline().strip().split(), no + 1
                time_path['eev'] = float(toks[-2])
                p_state = 1

            elif p_state == 1 and tag0 == 'clock':
                if len(toks) == 4:
                    toks, no = fp.readline().strip().split(), no + 1
                time_path['eslat'] = float(toks[-2])
                p_state = 2

            elif p_state == 2:
                # import pdb; pdb.set_trace()   # debug
                path = [None, None] + [0] * (TIME_COL_NUM - 2)
                toks_len = len(toks)
                if (toks_len == 2) or \
                   (toks_len == 4 and toks[2].endswith('(gclock')):
                    toks2, no = path_re.findall(fp.readline()), no + 1
                    start_col = 0
                else:
                    toks2 = toks
                    if toks[2].endswith('(gclock'):
                        start_col = 4
                    else:
                        start_col = 2

                if tag1 == '(net)':
                    get_time_cell(opt_set, path_cols, toks2, time_path['cpath'][-1], start_col)
                    # print("path (c-net):", time_path['cpath'][-1])  # debug
                else:
                    path[PT] = tag0
                    get_time_cell(opt_set, path_cols, toks2, path, start_col)
                    edt += path[DELTA]
                    time_path['cpath'].append(path)
                    # print("path (c-nor):", path)  # debug

        elif state == FINAL:
            if toks[0] == 'slack':
                time_path['slk'] = float(toks[2])
                break

        line, no = fp.readline(), no + 1
    
    return no, time_path, is_eof
#}}}

def get_time_port(opt_set: set, toks: list, path: list, ptype: str) -> int:
    """Get Time Port"""  #{{{
    path[TYPE] = ptype
    path[PT], cid = toks[0], -1
    if 'phy' in opt_set:
        try:
            path[PHY] = [int(x) for x in toks[cid][1:-1].split(',')]
        except ValueError:
            pass
        cid -= 2
    else:
        cid -= 1

    path[PATH], cid = float(toks[cid]), cid - 1
    if toks[cid] in ANNO_SYM:
        cid -= 1

    path[INCR], cid = float(toks[cid]), cid - 1
    if 'tran' in opt_set:
        path[TRAN], cid = float(toks[cid]), cid - 1
    if 'cap' in opt_set and 'net' not in opt_set:
        try:
            path[CAP] = float(toks[cid])
        except ValueError:
            pass
#}}}

def get_time_cell(opt_set: set, path_cols: list, toks: list, path: list, start_col: int):
    """Get Time Cell"""  #{{{
    cid, cpos = start_col, 0
    for i in range(cid+1):
        cpos += len(toks[i])

    try:
        ## fanout, cap, dtran, tran, derate, delta
        tid, tpos = 0, len(path_cols[0])
        for attr, pid in col_dict.items():
            if attr in opt_set:
                tpos += len(path_cols[tid:=tid+1])
                # import pdb; pdb.set_trace()
                if tpos >= cpos:
                    path[pid] = int(toks[cid]) if attr == 'net' else float(toks[cid])
                    cpos += len(toks[cid:=cid+1])

        ## incr, path, location
        path[INCR], cid = float(toks[cid]), cid + 1
        if toks[cid][-1] in ANNO_SYM:
            cid += 1
        path[PATH], cid = float(toks[cid]), cid + 1
        if toks[cid][-1] == 'r' or toks[cid][-1] == 'f':
            cid += 1
        if 'phy' in opt_set:
            path[PHY] = [int(x) for x in toks[cid].lstrip()[1:-1].split(',')]
    except IndexError:
        pass
    except ValueError:
        pass
    # import pdb; pdb.set_trace()
#}}}

def report_time_detail(args, prange_list: list):
    """Detial Time Path Analysis"""  #{{{
    time_rpt_dict = parse_time_rpt(args.rpt_fp, prange_list)

    if args.cfg_fp is not None:
        cons_cfg = load_time_cfg(args.cfg_fp)
    else:
        cons_cfg = {}

    if args.is_debug:
        print("opt: {}".format(time_rpt_dict['opt']))
        for path in time_rpt_dict['path']:
            for key, val in path.items():
                if key == 'lpath' or key == 'cpath':
                    for cell in val:
                        print("{}: {}".format(key, cell))
                else:
                    print("{}: {}".format(key, val))
    else:
        for path in time_rpt_dict['path']:
            splen = len(spath:=path['spin'])
            if (plen:=len(epath:=path['lpath'][-1][PT])) < splen:
                plen = splen

            print()
            print(" {}".format("=" * 60))
            if plen > 80:
                print(" Startpoint: {}".format(spath))
                print("             ({} {})".format(path['sed'], path['sck']))
                print(" Endpoint:   {}".format(epath))
                print("             ({} {})".format(path['eed'], path['eck']))
            else:
                print(" Startpoint: {} ({} {})".format(spath.ljust(plen), path['sed'], path['sck']))
                print(" Endpoint:   {} ({} {})".format(epath.ljust(plen), path['eed'], path['eck']))
            print(" Path group: {}".format(path['grp']))
            print(" Delay type: {}".format(path['type']))
            print(" {}".format("=" * 60))
            print(" data latency:             {: 5.4f}".format(path['arr'] - path['slat'] - path['sev']))
            print(" arrival:                  {: 5.4f}".format(path['arr']))
            print(" required:                 {: 5.4f}".format(path['req']))
            print(" slack:                    {: 5.4f}".format(path['slk']))
            print(" {}".format("=" * 60))
            print(" launch clock edge value:  {: 5.4f}".format(path['sev']))
            print(" capture clock edge value: {: 5.4f}".format(path['eev']))
            print(" launch clock latency:     {: 5.4f}".format(path['slat']))
            print(" capture clock latency:    {: 5.4f}".format(path['elat']))
            print(" crpr:                     {: 5.4f}".format(path['crpr']))
            print(" clock skew:               {: 5.4f}".format(path['slat'] - path['elat'] - path['crpr']))
            print(" {}".format("=" * 60))

            if args.is_delta:
                if 'ddt' in path:
                    print(" data delta:               {: 5.4f}".format(path['ddt']))
                else:
                    print(" data delta:                N/A")
                if 'sdt' in path:
                    print(" launch clock delta:       {: 5.4f}".format(path['sdt']))
                else:
                    print(" launch clock delta:        N/A")
                if 'edt' in path:
                    print(" capture clock delta:      {: 5.4f}".format(path['edt']))
                else:
                    print(" capture clock delta:       N/A")
                print(" {}".format("=" * 60))

            if args.cfg_fp is not None and 'ps' in cons_cfg:
                show_path_segment(path, time_rpt_dict['opt'], cons_cfg)
            print()

            if args.is_pt_cmd:
                print("[PT_CMD] Data:")
                print("  change_selection [get_timing_path -pba_mode ex -from {} -to {}]".format(
                        path['spin'], path['lpath'][-1][PT]))
                print("[PT_CMD] Launch clock:")
                print("  change_selection [get_timing_path -path_type full_clock_ex -to {}]".format(
                        path['spin']))
                print("[PT_CMD] Capture clock:")
                print("  change_selection [get_timing_path -path_type full_clock_ex -to {}]".format(
                        path['cpath'][-1][PT]))
                print()

    if args.bar is not None:
        if len(args.bar):
            bar_opt = set(args.bar)
        else:
            bar_opt = set(['p','c','t','d','i'])

        if args.path_type is None or len(args.path_type) == 0:
            path_type = set(['f', 'd'])
        else:
            path_type = set(args.path_type)
            if 'f' in path_type:
                path_type.add('d')

        show_time_bar(time_rpt_dict['path'][0], time_rpt_dict['opt'], cons_cfg, 
                      bar_opt, path_type, args.is_rev)
#}}}

def show_path_segment(path: dict, opt_set: set, cons_cfg: dict):
    """Show Path Segment"""  #{{{
    ttag, stag = dps_tag['T'], dps_tag['S']
    tag, is_1st, is_clk = None, True, True
    slat_list, sdt_list, dlat_list, ddt_list = [], [], [], []

    for cell in path['lpath']:
        if tag is None:
            new_tag = None
            for key, ps_re in cons_cfg['ps'].items():
                if (m:=ps_re.fullmatch(cell[PT])):
                    new_tag = key
                    break
            tag = new_tag

            if is_1st:
                is_1st = False
                lat_sum, dt_sum = cell[INCR], cell[DELTA]
            elif new_tag is not None:
                if is_clk:
                    slat_list.append([ttag, lat_sum])
                    sdt_list.append([ttag, dt_sum])
                else:
                    dlat_list.append([ttag, lat_sum])
                    ddt_list.append([ttag, dt_sum])
                lat_sum, dt_sum = cell[INCR], cell[DELTA]
            else:
                lat_sum += cell[INCR]
                dt_sum += cell[DELTA]

        elif cons_cfg['ps'][tag].fullmatch(cell[PT]) is None:
            if is_clk:
                slat_list.append([tag, lat_sum])
                sdt_list.append([tag, dt_sum])
            else:
                dlat_list.append([tag, lat_sum])
                ddt_list.append([tag, dt_sum])
            lat_sum, dt_sum = cell[INCR], cell[DELTA]

            tag = None
            for key, ps_re in cons_cfg['ps'].items():
                if (m:=ps_re.fullmatch(cell[PT])):
                    tag = key
                    break
        else:
            lat_sum += cell[INCR]
            dt_sum += cell[DELTA]

        key = ttag if tag == None else tag
        if cell[PT] == path['spin']:
            slat_list.append([key, lat_sum])
            sdt_list.append([key, dt_sum])
            tag, is_1st, is_clk = None, True, False 
            lat_sum, dt_sum = 0, 0

    dlat_list.append([key, lat_sum])
    ddt_list.append([key, dt_sum])
    tag, is_1st = None, True
    elat_list, edt_list = [], []

    for cell in path['cpath']:
        if tag is None:
            new_tag = None
            for key, ps_re in cons_cfg['ps'].items():
                if (m:=ps_re.fullmatch(cell[PT])):
                    new_tag = key
                    break
            tag = new_tag

            if is_1st:
                is_1st = False
                lat_sum, dt_sum = cell[INCR], cell[DELTA]
            elif new_tag is not None:
                elat_list.append([ttag, lat_sum])
                edt_list.append([ttag, dt_sum])
                lat_sum, dt_sum = cell[INCR], cell[DELTA]
            else:
                lat_sum += cell[INCR]
                dt_sum += cell[DELTA]

        elif cons_cfg['ps'][tag].fullmatch(cell[PT]) is None:
            elat_list.append([tag, lat_sum])
            edt_list.append([tag, dt_sum])
            lat_sum, dt_sum = cell[INCR], cell[DELTA]

            tag = None
            for key, ps_re in cons_cfg['ps'].items():
                if (m:=ps_re.fullmatch(cell[PT])):
                    tag = key
                    break
        else:
            lat_sum += cell[INCR]
            dt_sum += cell[DELTA]

    key = ttag if tag == None else tag
    elat_list.append([key, lat_sum])
    edt_list.append([key, dt_sum])

    print(" Segment:  ", end='')
    if 'pf' in opt_set:
        print("(report path type: full)")
    elif 'pfc' in opt_set:
        print("(report path type: full_clock)")
    elif 'pfce' in opt_set:
        print("(report path type: full_clock_expanded)")
    else:
        print("(report path type: unknown)")

    print(" {}".format("-" * 60))
    
    print(" data latency: ", end='')
    for tag, val in dlat_list:
        print("{}:{: .4f} ".format(tag, val), end='')
    print()

    print(" data delta:   ", end='')
    for tag, val in ddt_list:
        print("{}:{: .4f} ".format(tag, val), end='')
    print()

    print(" {}".format("-" * 60))

    print(" launch clk latency:  ", end='')
    print("{}:{: .4f} ".format(stag, path['sslat']), end='')
    for tag, val in slat_list:
        print("{}:{: .4f} ".format(tag, val), end='')
    print()

    print(" launch clk delta:    ", end='')
    for tag, val in sdt_list:
        print("{}:{: .4f} ".format(tag, val), end='')
    print()

    print(" {}".format("-" * 60))

    print(" capture clk latency: ", end='')
    print("{}:{: .4f} ".format(stag, path['eslat']), end='')
    for tag, val in elat_list:
        print("{}:{: .4f} ".format(tag, val), end='')
    print()

    print(" capture clk delta:   ", end='')
    for tag, val in edt_list:
        print("{}:{: .4f} ".format(tag, val), end='')
    print()

    print(" {}".format("=" * 60))
#}}}

def show_time_bar(path: dict, opt_set: set, cons_cfg: dict, bar_opt: set, path_type: set, is_rev: bool):
    """Show Time Path Barchart"""  #{{{
    global dps_tag
    db, db_dict = [], {}

    ## [c]apacitance
    if 'c' in bar_opt and 'cap' in opt_set:
        db_dict['c'], data = [], []
        for cell in path['lpath']:
            data.append(cell[CAP])
            if cell[PT] == path['spin']:
                if 'l' in path_type:
                    db_dict['c'].append(["Launch Clk Cap (pf)", data.copy()])
                if 'd' not in path_type:
                    data = None
                    break
                if 'f' not in path_type:
                    data = [data[-1]]
        ddata = data

        if 'c' in path_type:
            data = []
            for cell in path['cpath']:
                data.append(cell[CAP])
            db_dict['c'].append(["Capture Clk Cap (pf)", data])

        if ddata is not None:
            db_dict['c'].append(["Path Cap (pf)", ddata])
    else:
        bar_opt.discard('c')

    opt_set.add('incr')
    bar_types = [
        ['p', 'phy', PHY, "Distance (um)"],     ## [p]hysical distance
        ['t', 'tran', TRAN, "Tran (ns)"],       ## [t]ransition
        ['d', 'delta', DELTA, "Delta (ns)"],    ## [d]elta
        ['i', 'incr', INCR, "Increment (ns)"],       ## latency [i]ncrement
    ]

    for btype in bar_types:
        if btype[0] in bar_opt and btype[1] in opt_set:
            db_dict[btype[0]], data = [], []
            for cell in path['lpath']:
                data.append(cell[btype[2]])
                if cell[PT] == path['spin']:
                    if 'l' in path_type:
                        db_dict[btype[0]].append([f"Launch Clk {btype[3]}", data.copy()])
                    if 'd' not in path_type:
                        data = None
                        break
                    if 'f' not in path_type:
                        data = [data[-1]]
            ddata = data

            if 'c' in path_type:
                data = []
                for cell in path['cpath']:
                        data.append(cell[btype[2]])
                db_dict[btype[0]].append([f"Capture Clk {btype[3]}", data])

            if ddata is not None:
                db_dict[btype[0]].append([f"Path {btype[3]}", ddata])
        else:
            bar_opt.discard(btype[0])

    if 'p' in db_dict:          # physical distance
        db.extend(db_dict['p'])
    if 'c' in db_dict:          # capacitance
        c_plist = db_dict['c']
        for key, plist in db_dict.items():
            if key != 'c':
                for i, clist in enumerate(plist):
                    if len(c_plist[i]) < len(clist):
                        c_plist[i].insert(0, 0.0)
                break
        db.extend(c_plist)
    if 't' in db_dict:          # transition
        db.extend(db_dict['t'])
    if 'd' in db_dict:          # delta
        db.extend(db_dict['d'])
    if 'i' in db_dict:          # latency increment
        db.extend(db_dict['i'])

    plt_cnt, pal_num = len(db), len(HIST_PALETTE)
    if plt_cnt != 0:
        hist_lg, lv_c, lv_ha, lv_ec = [], [], [], []
        if 'ps' in cons_cfg:
            for type_ in ('l', 'c', 'd'):
                if type_ in path_type:
                    tag, pal_idx, hist_lg_cell = None, 0, {dps_tag['T']: HIST_DEFAULT_COLOR}
                    lv_c_cell, lv_ha_cell, lv_ec_cell = [], [], []
                    s_path = path['cpath'] if type_ == 'c' else path['lpath']

                    for cell in s_path:
                        if tag is None:
                            new_tag = None
                            for key, ps_re in cons_cfg['ps'].items():
                                if (m:=ps_re.fullmatch(cell[PT])):
                                    new_tag = key
                                    break
                            tag = new_tag
                        elif cons_cfg['ps'][tag].fullmatch(cell[PT]) is None:
                            new_tag = None
                            for key, ps_re in cons_cfg['ps'].items():
                                if (m:=ps_re.fullmatch(cell[PT])):
                                    new_tag = key
                                    break
                            tag = new_tag

                        if cell[PT] == path['spin'] and type_ == 'd' and 'f' not in path_type:
                            pal_idx, hist_lg_cell = 0, {dps_tag['T']: HIST_DEFAULT_COLOR}
                            lv_c_cell, lv_ha_cell, lv_ec_cell = [], [], []

                        key = dps_tag['T'] if tag is None else tag
                        if key not in hist_lg_cell:
                            hist_lg_cell[key] = HIST_PALETTE[pal_idx]
                            pal_idx = (pal_idx + 1) % pal_num

                        lv_c_cell.append(hist_lg_cell[key])
                        if cell[PT] == path['spin'] and type_ == 'd':
                            lv_ha_cell.append('/')
                            lv_ec_cell.append('r')
                        else:
                            lv_ha_cell.append('')
                            lv_ec_cell.append('k')
                        if cell[PT] == path['spin'] and type_ == 'l':
                            break

                    hist_lg.append(hist_lg_cell)
                    lv_c.append(lv_c_cell)
                    lv_ha.append(lv_ha_cell)
                    lv_ec.append(lv_ec_cell)
        else:
            lg_cell = {dps_tag['T']: HIST_PALETTE[0]}
            lv_c_cell = [HIST_PALETTE[0]]
            for type_ in ('l', 'd', 'c'):
                if type_ in path_type:
                    hist_lg.append(lg_cell)
                    lv_c.append(lv_c_cell)
                    if type_ == 'd':
                        lv_ha_cell, lv_ec_cell = [], []
                        for cell in path['lpath']:
                            if cell[PT] == path['spin']:
                                if 'f' in path_type: 
                                    lv_ha_cell.append('/')
                                    lv_ec_cell.append('r')
                                else:
                                    lv_ha_cell = ['/']
                                    lv_ec_cell = ['r']
                            else:
                                lv_ha_cell.append('')
                                lv_ec_cell.append('k')
                        lv_ha.append(lv_ha_cell)
                        lv_ec.append(lv_ec_cell)
                    else:
                        lv_ha.append([''])
                        lv_ec.append(['k'])

        if plt_cnt == 1:
            labels = list(hist_lg[0].keys())
            handles = [plt.Rectangle((0,0), 1, 1, color=hist_lg[0][label]) for label in labels]
            lv_cnt = len(db[-1][1])
            level = range(0, lv_cnt)

            plt.bar(level, db[-1][1], align='center', color=lv_c[0], hatch=lv_ha[0], ec=lv_ec[0], width=1.0)
            plt.grid(axis='y', which='both', ls=':', c='grey')
            plt.xticks(level, [])
            plt.title(db[-1][0])
            plt.legend(handles, labels, loc='upper left', ncol=len(labels))
        else:
            path_type.discard('f')
            opt_cnt, type_cnt = len(bar_opt), len(path_type)
            cy_cnt, cx_cnt = (type_cnt, opt_cnt) if is_rev else (opt_cnt, type_cnt)
            fig, axs = plt.subplots(cy_cnt, cx_cnt, constrained_layout=True)
            for y in range(opt_cnt):
                for x in range(type_cnt):
                    did = type_cnt * y + x
                    aid = (opt_cnt * x + y) if is_rev else (type_cnt * y + x)
                    labels = list(hist_lg[x].keys())
                    handles = [plt.Rectangle((0,0), 1, 1, color=hist_lg[x][label]) for label in labels]
                    lv_cnt = len(db[did][1])
                    level = range(0, lv_cnt)

                    axs = plt.subplot(cy_cnt, cx_cnt, aid+1)
                    axs.bar(level, db[did][1], align='center', 
                            color=lv_c[x], hatch=lv_ha[x], ec=lv_ec[x], width=1.0)
                    axs.grid(axis='y', which='both', ls=':', c='grey')
                    axs.set_xticks(level, [])
                    axs.set_title(db[did][0])
                    axs.legend(handles, labels, loc='upper left', ncol=len(labels))

        plt.xlabel("level")
        plt.show()
#}}}

### Function for 'report_noise' ###

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

    ## report_constraint brief
    parser_cons = subparsers.add_parser('cons', help="Summary of report_constraint\n" + 
                                                     "  --command: 'report_cons -all_vio -path end'")
    parser_cons.add_argument('rpt_fp', help="report path (left or base)") 
    parser_cons.add_argument('rpt_fp2', nargs='?', help="report path (right for compare)") 
    parser_cons.add_argument('-c', dest='cfg_fp', metavar='<config>', 
                                    help="custom configureation file") 

    ## report_timing brief
    parser_time = subparsers.add_parser('time', help="Brief report of report_timing\n" +
                                                     "  --command: 'report_timing'")
    parser_time.add_argument('-a', dest='is_all', action='store_true', 
                                    help="show timing meet path (default: only violation path)")
    parser_time.add_argument('-c', dest='cfg_fp', metavar='<config>', 
                                    help="custom configureation file") 
    parser_time.add_argument('rpt_fp', help="report_path") 

    ## report_timing detail
    parser_time2 = subparsers.add_parser('time2', help="Detail time path analysis\n" +
                                                      "  --command: 'report_timing'")
    parser_time2.add_argument('-c', dest='cfg_fp', metavar='<config>', 
                                        help="custom configureation file") 
    parser_time2.add_argument('-r', dest='range', metavar='<value>', 
                                        help="scan range (ex: 6,16+2,26-100)") 
    parser_time2.add_argument('-delta', dest='is_delta', action='store_true', 
                                        help="show delta")
    parser_time2.add_argument('-path', dest='path_type', metavar='<pat>', nargs='*', 
                                        choices=['f','d','l','c'],
                                        help="bar chart path type \
                                                (f:full data, d:data, l:launch clk, c:capture clk)") 
    parser_time2.add_argument('-bar', dest='bar', metavar='<pat>', nargs='*', 
                                        choices=['p','c','t','d','i'],
                                        help="bar chart content select \
                                                (p:distance, c:cap, t:tran, d:delta, i:incr)") 
    parser_time2.add_argument('-rev', dest='is_rev', action='store_true', help="axis reverse")
    parser_time2.add_argument('-pt', dest='is_pt_cmd', action='store_true', 
                                        help="dump PrimteTime path command")
    parser_time2.add_argument('-debug', dest='is_debug', action='store_true', 
                                        help="enable debug mode")
    parser_time2.add_argument('rpt_fp', help="report_path") 

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

    if args.proc_mode == 'cons':
        rpt_fps = [args.rpt_fp] if args.rpt_fp2 is None else [args.rpt_fp, args.rpt_fp2]
        report_cons_brief(rpt_fps, args.cfg_fp)

    elif args.proc_mode == 'time':
        report_time_brief(args.rpt_fp, args.is_all, args.cfg_fp)

    elif args.proc_mode == 'time2':
        prange_list = []
        if args.range == None:
            prange_list.append([0, None, 1])
        else:
            for prange in args.range.split(','):
                if (m:=prange_re1.fullmatch(args.range)):
                    prange_list.append([int(m[1]), None, int(m[2])])
                elif (m:=prange_re2.fullmatch(args.range)): 
                    prange_list.append([int(m[1]), int(m[2]), None])
                else:
                    prange_list.append([int(args.range), None, 1])
        print("\n Report: {}".format(os.path.abspath(args.rpt_fp)))
        report_time_detail(args, prange_list)

    elif args.proc_mode == 'nois':
        report_noise_brief(args.rpt_fp)
#}}}

if __name__ == '__main__':
    main()
