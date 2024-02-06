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
import os
import re

from .utils.common import PKG_VERSION, PT_CONS_VER

VERSION = f"pt_ana_cons version {PT_CONS_VER} ({PKG_VERSION})"

### Global Variable ###    {{{

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

### Function ###

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
                        rid = 0 if rid == 'l' else 1 if rid == 'r' else 2
                        tag = f'{vtype}:{group}' if vtype in group_vio else f'{vtype}:{vtype}'
                        grp_list = cons_cfg['g'].setdefault(tag, [[], [], []])
                        parse_grp_cmd(ln_no, grp_list[rid], cmd_list)

                    elif line.startswith('gr:'):
                        item, *cmd_list = line[3:].split()
                        vtype, group, rid = item.split(':') 
                        rid = 0 if rid == 'l' else 1 if rid == 'r' else 2
                        if vtype not in group_vio:
                            group = vtype
                        vtype_dict = cons_cfg['g'].setdefault(f'{vtype}:', {})
                        grp_list = vtype_dict.setdefault(group, [[], [], []])
                        parse_grp_cmd(ln_no, grp_list[rid], cmd_list)

                    elif line.startswith('i:'):
                        item, *cmd_list = line[2:].split()
                        vtype, group, rid, ins = item.split(':')
                        rid = 0 if rid == 'l' else 1 if rid == 'r' else 2
                        tag = f'{vtype}:{group}:{ins}' if vtype in group_vio else f'{vtype}:{vtype}:{ins}'
                        ins_list = cons_cfg['p'].setdefault(tag, [[], []])
                        if rid == 2:
                            parse_ins_cmd(ins_list[0], cmd_list)
                            parse_ins_cmd(ins_list[1], cmd_list)
                        else:
                            parse_ins_cmd(ins_list[rid], cmd_list)

                    elif line.startswith('ir:'):
                        item, *cmd_list = line[3:].split()
                        vtype, group, rid, ins = item.split(':')
                        rid = 0 if rid == 'l' else 1 if rid == 'r' else 2
                        tag = f'{vtype}:{group}:' if vtype in group_vio else f'{vtype}:{vtype}:'
                        grp_dict = cons_cfg['p'].setdefault(tag, {})
                        ins_list = grp_dict.setdefault(ins, [[], []])
                        if rid == 2:
                            parse_ins_cmd(ins_list[0], cmd_list)
                            parse_ins_cmd(ins_list[1], cmd_list)
                        else:
                            parse_ins_cmd(ins_list[rid], cmd_list)

                except SyntaxError:
                    raise SyntaxError(f"config syntax error (ln:{ln_no})")

    # print(cons_cfg)                 # debug
    # import pdb; pdb.set_trace()     # debug
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

def report_cons_summary(rpt_fps: list, cfg_fp: str):
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
                            for gpat, gcons_list in cons_cfg['g'][tag2].items():
                                if re.fullmatch(gpat, group):
                                    comm = grp_cons_check(rid, values, gcons_list[rid], comm, cond_set)

                    diff_values = [group_list[0][0] - group_list[1][0]]
                    diff_values.append(group_list[0][1] - group_list[1][1])
                    diff_values.append(group_list[0][2] - group_list[1][2])
                    print("| {0[0]:<+16.4f}{0[1]:<+16.4f}{0[2]:<+6}|".format(diff_values), end='')

                    if tag1 in cons_cfg['g']:
                        comm = grp_cons_check(2, diff_values, cons_cfg['g'][tag1][2], comm, cond_set)
                    if tag2 in cons_cfg['g']:
                        for gpat, gcons_list in cons_cfg['g'][tag2].items():
                            if re.fullmatch(gpat, group):
                                comm = grp_cons_check(2, diff_values, gcons_list[2], comm, cond_set)
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
                        for gpat, gcons_list in cons_cfg['g'][tag].items():
                            if re.fullmatch(gpat, group):
                                comm = grp_cons_check(None, values, gcons_list[0], comm, cond_set)
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

### Main ###

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

    rpt_fps = [args.rpt_fp] if args.rpt_fp2 is None else [args.rpt_fp, args.rpt_fp2]
    report_cons_summary(rpt_fps, args.cfg_fp)
#}}}

if __name__ == '__main__':
    main()
