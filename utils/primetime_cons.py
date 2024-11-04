# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-only
#
# Copyright (C) 2023 Yeh, Hsin-Hsien <yhh76227@gmail.com>
#
"""
Global Function for PrimeTime Report Analysis
"""
import copy
import gzip
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from enum import IntEnum
from re import Pattern as RePat
from typing import Any

import simpletools.simpletable as sst


GRP_CONS = ( 'max_delay/setup', 'min_delay/hold' )

NOGRP_CONS = ( 'recovery', 'removal', 
               'clock_gating_setup', 'clock_gating_hold', 
               'max_capacitance', 'min_capacitance', 
               'max_transition', 'min_transition',
               'max_fanout' )

CLK_CONS = ( 'clock_tree_pulse_width', 
             'sequential_tree_pulse_width', 
             'sequential_clock_min_period' )

CONS_TYPE = set(GRP_CONS + NOGRP_CONS + CLK_CONS)

_PATH_OP = set()
for i in ('u'):
    _PATH_OP.update((f"{i}:act", f"{i}:slk"))

_GROUP_OP = set()
for i in ('h', 'm'):
    _GROUP_OP.update(f"{i}:wns", f"{i}:tns", f"{i}:nvp")

CMP_OP = { '>' : lambda a, b: a > b,
           '<' : lambda a, b: a < b,
           '==': lambda a, b: a == b,
           '>=': lambda a, b: a >= b,
           '<=': lambda a, b: a <= b }


@dataclass (slots=False)
class _ConsPathOp:
    re: RePat = None
    l:  list[Any] = field(init=False)
    r:  list[Any] = field(init=False)
    def __post_init__(self):
        # cmd: [fno, opteration]
        self.l = [(0, 'u')]
        self.r = [(0, 'u')]
    def __getitem__(self, key):
        if key in {'l', 0}: return self.l
        if key in {'r', 1}: return self.r


@dataclass (slots=False)
class _ConsGroupOp:
    re: RePat = None
    l:  list[Any] = field(init=False)
    r:  list[Any] = field(init=False)
    d:  list[Any] = field(init=False)
    def __post_init__(self):
        # cmd: [fno, opteration]
        self.l = [(0, 'h'), (0, 'm')]
        self.r = [(0, 'h'), (0, 'm')]
        self.d = [(0, 'h'), (0, 'm')]
    def __getitem__(self, key):
        if key in {'l', 0}: return self.l
        if key in {'r', 1}: return self.r
        if key in {'d', 2}: return self.d


def _parse_path_cmd(no: int, cmd: str) -> tuple[Any, ...]:
    """
    Parsing config commands (path).
    """
    if cmd[:3] in ("u::", ):
        return no, cmd[0], cmd[3:]

    if cmd[:2] in ("u:", ):
        m = re.fullmatch(r"(\w:\w{3})([><=]{1,2})([\-\d\.]+):(\w+)", cmd)
        if m[1] not in _PATH_OP:
            raise SyntaxError(f"Error: config syntax error (ln:{no})")
        return no, m[1][0], m[1][2:], m[2], float(m[3]), m[4]

    raise SyntaxError(f"Error: config syntax error (ln:{no})")


def _parse_group_cmd(no: int, cmd: str) -> tuple[Any, ...]:
    """
    Parsing config commands (group).
    """
    if cmd[:3] in ("h::", "m::"):
        return no, cmd[0], cmd[3:]

    if cmd[:2] in ("h:", "m:"):
        m = re.fullmatch(r"(\w:\w{3})([><=]{1,2})([\-\d\.]+):(\w+)", cmd)
        if m[1] not in _GROUP_OP:
            raise SyntaxError(f"Error: config syntax error (ln:{no})")
        return no, m[1][0], m[1][2:], m[2], float(m[3]), m[4]

    raise SyntaxError(f"Error: config syntax error (ln:{no})")


def _load_cons_cfg(cfg_fp : str) -> dict:
    """
    Load configurations from the file to database.

    Parameters
    ----------
    cfg_fp : str
        configuration file path

    Returns
    -------
    cons_cfg : dict
        The config dictionary base on the config data structure.
    """
    attr = {
        'group_column_width': ('gcol_w', 36),
        'wns_width': ('wns_w', 12),
        'tns_width': ('tns_w', 12),
        'nvp_width': ('nvp_w', 6),
    }

    cons_cfg = dict(attr.values())
    cons_cfg.update({ 'p': {}, 'g': {}, 'm': {} })
    if cfg_fp is None:
        return cons_cfg

    with open(cfg_fp, 'r') as fp:
        for fno, line in enumerate(fp, 1):
            if (line:=line.split('#')[0].strip()):
                try:
                    key, value, *other = line.split(':')
                    key, value = key.strip(), value.strip()
                    if key in attr:
                        key2, value2 = attr[key]
                        if (ktype:=type(value2)) is bool:
                            if value.lower() == str(not value2).lower():
                                cons_cfg[key2] = not value2
                        elif ktype is int:
                            cons_cfg[key2] = int(value)
                        elif ktype is float:
                            cons_cfg[key2] = float(value)
                        else:
                            raise SyntaxError(
                                f"Attributes - unsupported data type ({ktype}).")
                    elif key == 'p':
                        tag, *cmd_src = line[2:].split()
                        type_, group, path, rid = tag.split(':')
                        gid = ':'.join((type_, group))
                        plist = cons_cfg['p'].setdefault(gid, [])
                        plist.append(pobj:=_ConsPathOp(re=re.compile(path)))
                        for cmd in cmd_src:
                            for i in (['l', 'r'] if rid == 'a' else [rid]):
                                if cmd[:1] == 'u':
                                    pobj[i][0] = _parse_path_cmd(fno, cmd)
                                else:
                                    raise SyntaxError(
                                        f"Attributes - unknown path command ({cmd}).")
                    elif key == 'g':
                        tag, *cmd_src = line[2:].split()
                        type_, group, rid = tag.split(':')
                        glist = cons_cfg['g'].setdefault(type_, [])
                        glist.append(gobj:=_ConsGroupOp(re=re.compile(group)))
                        for cmd in cmd_src:
                            if cmd[:1] == 'h':
                                gobj[rid][0] = _parse_group_cmd(fno, cmd) 
                            elif cmd[:1] == 'm':
                                gobj[rid][1] = _parse_group_cmd(fno, cmd) 
                            else:
                                raise SyntaxError(
                                    f"Attributes - unknown group command ({cmd}).")
                    elif key == 'mtag':
                        msg = other[0].strip(" \"\'")
                        cons_cfg['m'][value] = msg
                    elif key != '':
                        print(f"[WARNING] unknown operation '{key}', ignore. (CFG-001)")
                except SyntaxError:
                    raise SyntaxError(f"config syntax error (ln:{fno})")

    return cons_cfg


def _print_cons_cfg(cons_cfg: dict, end: bool=False):
    for type_, content in cons_cfg.items():
        if type_ == 'p':
            print("\n=== cons_cfg (path, dictionary)")
            for key, value in cons_cfg['p'].items():
                print(f"{key}: {value}")
        elif type_ == 'g':
            print("\n=== cons_cfg (group, dictionary)")
            for key, value in cons_cfg['g'].items():
                print(f"{key}: {value}")
        elif type_ == 'm':
            print("\n=== cons_cfg (message, dictionary)")
            for key, value in cons_cfg['m'].items():
                print(f"{key}: {value}")
        else:
            print(f"{type_}: {content}")
    print()
    if end:
        exit(1)
    import pdb; pdb.set_trace()


class PTT(IntEnum):  # PathTableTitle
    PIN, SC, REQ, ACT, SLK, ORGP = range(6)


class GTT(IntEnum):  # GroupTableTitle
    MAK, GRP = range(0, 2)
    LW, LT, LN = range(2, 5)
    RW, RT, RN = range(5, 8)
    DW, DT, DN = range(8, 11)


@dataclass (slots=False)
class GroupTable:
    name:   str
    user:   bool
    modify: list[bool]
    ptable: list[list]
    sum:    list[Any] = field(init=False)
    def __post_init__(self):
        if len(self.modify) == 2:
            self.sum = ['', self.name] + [0.0] * 9 + ['']
        else:
            self.sum = ['', self.name] + [0.0] * 3 + ['']
    def update_diff(self):
        for l, r, d in zip(*[range(2, 5), range(5, 8), range(8, 11)]):
            self.sum[d] = self.sum[l] - self.sum[r]


def _print_cons_table(table: dict):
    """"Print constraint table."""
    print()
    for vtype, vtable in table.items():
        print(f"###### Violation: {vtype}\n")
        def_gtables, usr_gtables = [], []
        for gtable in vtable.values():
            if gtable.user:
                usr_gtables.append(gtable)
            else:
                def_gtables.append(gtable)

        for gtable in (def_gtables + usr_gtables):
            gtitle = f"== Group: {gtable.name}"
            print(f"{gtitle:30}(modify:{gtable.modify})")
            for rid, ptable in enumerate(gtable.ptable):
                title_va = [f'PIN (RID:{rid:2})', 'SC', 'REQ', 'ACT', 'SLK', 'ORGP']
                title_fs = ['{}', '{}', '{:< .4f}', '{:< .4f}', '{:< .4f}', '']
                title_len = [len(s) for s in title_va]
                title_len[2:5] = [10] * 3

                data = sst.Block(data=ptable, col_len=title_len, fs=title_fs)
                title = sst.Block(data=[title_va], col_len=data.col_len)
                data.divider = (div:=sst.Divider(data.col_len))
                data.update_col_len()
                sst.SimpleTable([div, title, div, data, div]).draw()

                if rid == 1:
                    print(">>> Summary(WNS|TNS|NVP): {: 9.4f}, {: 9.4f}, {: 9.4f}".format(
                            *gtable.sum[GTT.RW:GTT.RN+1]))
                else:
                    print(">>> Summary(WNS|TNS|NVP): {: 9.4f}, {: 9.4f}, {: 9.4f}".format(
                            *gtable.sum[GTT.LW:GTT.LN+1]))
            print()
    exit(1)


class ConsReport:
    """
    Constraint violation report parser.
    """
    # _sum_hd = (('group', 'Group'), 
    #            ('lwns', 'L-WNS'), ('ltns', 'L-TNS'), ('lnvp', 'L-NVP'),
    #            ('rwns', 'R-WNS'), ('rtns', 'R-TNS'), ('rnvp', 'R-NVP'),
    #            ('dwns', 'D-WNS'), ('dtns', 'D-TNS'), ('dnvp', 'D-NVP'),
    #            ('comm', ''))

    def __init__(self, cfg_fp: [None|str]=None):
        """
        Parameters
        ----------
        cfg_fp : {None, str}, optional
            Configuration file path, default is None.
        """
        cons_cfg = _load_cons_cfg(cfg_fp)
        # _print_cons_cfg(cons_cfg, True)    # debug
        ### attributes
        self.gcol_w = cons_cfg['gcol_w']
        self.wns_w = cons_cfg['wns_w']
        self.tns_w = cons_cfg['tns_w']
        self.nvp_w = cons_cfg['nvp_w']
        self.cfg_path = cons_cfg['p']
        self.cfg_grp = cons_cfg['g']
        self.cfg_msg = cons_cfg['m']
        ### data
        self.is_multi = False
        self.cons_table = defaultdict(dict) 
        self.sum_tables = {}
        ### plot
        # self.plot_grp = plot_grp
        # self.plot_data = []

    def parse_report(self, rpt_fps: list[str]):
        """
        Parse the timing report.

        Parameters
        ----------
        rpt_fps : list[str]
            A list of the file path of constraint reports. (max number: 2)
        """
        PRE, IDLE, TITLE, VT1, VT2 = range(5)
        self.is_multi = len(rpt_fps[:2]) > 1
        state = PRE

        for fid, rpt_fp in enumerate(rpt_fps[:2]):
            if os.path.splitext(rpt_fp)[1] == '.gz':
                fp = gzip.open(rpt_fp, mode='rt')
            else:
                fp = open(rpt_fp)

            # state, is_dmsa, path = ST_IDLE, False, []
            for line in fp:
                toks = line.split()
                toks_len = len(toks)

                if state == PRE and toks_len and toks[0] == 'Design':
                    is_dmsa = True if toks[2] == 'multi_scenario' else False
                    state = IDLE

                elif state == IDLE and toks_len and toks[0] in CONS_TYPE:
                    vtype = toks[0]
                    group = toks[1][2:-1] if toks_len > 1 else '**default**'
                    state, ttable = TITLE, self.cons_table[vtype]

                elif state == TITLE and toks_len:
                    if toks[0][0] == '-':
                        wns, tns, nvp = 0.0, 0.0, 0
                        if pre_toks[-1] == 'Clock':
                            state, path, is_act = VT2, [], False
                            # print(f"=== (debug_info) VT2: {vtype}, {group}")
                        else:
                            if group in ttable:
                                gtable = ttable[group]
                            elif self.is_multi:
                                modify, ptable = [False, False], [[], []]
                                gtable = GroupTable(group, False, modify, ptable)
                                ttable[group] = gtable
                            else:
                                gtable = GroupTable(group, False, [False], [[]])
                                ttable[group] = gtable
                            cfg_path = []
                            if (key:=f"{vtype}:{group}") in self.cfg_path:
                                cfg_path.extend(self.cfg_path[key])
                            if (key:=f"{vtype}:*") in self.cfg_path:
                                cfg_path.extend(self.cfg_path[key])
                            state, path, is_act = VT1, [], False
                            # print(f"=== (debug_info) VT1: {vtype}, {group}")
                    else:
                        pre_toks = toks.copy()

                elif state == VT1:
                    if toks_len:
                        path.extend(toks)
                        if path[-1] == '(VIOLATED)':
                            is_act, cid = True, -2
                        elif path[-1] == 'digits)':
                            is_act, cid = True, -5

                        if is_act:
                            slk, cid = float(path[cid]), cid-1
                            act, cid = float(path[cid]), cid-1
                            req, cid = float(path[cid]), cid-1 
                            sc = path[cid] if is_dmsa else ""
                            pin = path[0]

                            ### path config check
                            ugroup = None
                            for cfg in cfg_path:
                                if cfg.re.fullmatch(pin):
                                    for ln, *cmd in cfg[fid]:
                                        if ln and cmd[0] == 'u':
                                            # check if path move to user group
                                            if len(cmd) == 2:
                                                ugroup = cmd[1]
                                            elif cmd[1] == 'slk' and CMP_OP[cmd[2]](slk, cmd[3]):
                                                ugroup = cmd[4]
                                            elif cmd[1] == 'act' and CMP_OP[cmd[2]](act, cmd[3]):
                                                ugroup = cmd[4]

                            ### add data to path table
                            if ugroup is not None:
                                gtable.modify[fid] = True
                                org_group = gtable.name
                                if ugroup in ttable:
                                    gtable2 = ttable[ugroup]
                                elif self.is_multi:
                                    modify, ptable = [False, False], [[], []]
                                    gtable2 = GroupTable(ugroup, True, modify, ptable)
                                    ttable[ugroup] = gtable2
                                else:
                                    gtable2 = GroupTable(ugroup, True, [False], [[]])
                                    ttable[ugroup] = gtable2
                                gtable2.ptable[fid].append([pin, sc, req, act, slk, org_group])
                                ### add data to sum table
                                if fid == 1:
                                    if gtable2.sum[GTT.RW] > slk:
                                        gtable2.sum[GTT.RW] = slk
                                    gtable2.sum[GTT.RT] += slk
                                    gtable2.sum[GTT.RN] += 1
                                else:
                                    if gtable2.sum[GTT.LW] > slk:
                                        gtable2.sum[GTT.LW] = slk
                                    gtable2.sum[GTT.LT] += slk
                                    gtable2.sum[GTT.LN] += 1
                            else:
                                gtable.ptable[fid].append([pin, sc, req, act, slk, ""])
                                ### add data to sum table
                                if wns > slk:
                                    wns = slk
                                tns += slk
                                nvp += 1

                            is_act, path = False, []
                    else:
                        if fid == 1:
                            gtable.sum[GTT.RW] = wns
                            gtable.sum[GTT.RT] = tns
                            gtable.sum[GTT.RN] = nvp
                        else:
                            gtable.sum[GTT.LW] = wns
                            gtable.sum[GTT.LT] = tns
                            gtable.sum[GTT.LN] = nvp
                        state = IDLE

                elif state == VT2:
                    if toks_len:
                        path.extend(toks)
                        if path[-2] == '(VIOLATED)':
                            is_act, cid = True, -3
                        elif path[-2] == 'digits)':
                            is_act, cid = True, -6

                        if is_act:
                            slk, cid = float(path[cid]), cid-1
                            act, cid = float(path[cid]), cid-1
                            req, cid = float(path[cid]), cid-1 
                            sc = path[cid] if is_dmsa else ""
                            pin = path[0]

                            ### get group for specific clock
                            pulse_type = ' '.join(path[1:cid+1])[1:-1].split()[-1]
                            group2 = f"{path[-1]},{pulse_type}"
                            if group2 != group:
                                group = group2
                                if group in ttable:
                                    gtable = ttable[group]
                                elif self.is_multi:
                                    modify, ptable = [False, False], [[], []]
                                    gtable = GroupTable(group, False, modify, ptable)
                                    ttable[group] = gtable
                                else:
                                    gtable = GroupTable(group, False, [False], [[]])
                                    ttable[group] = gtable
                                cfg_path = []
                                if (key:=f"{vtype}:{group}") in self.cfg_path:
                                    cfg_path.extend(self.cfg_path[key])
                                if (key:=f"{vtype}:*") in self.cfg_path:
                                    cfg_path.extend(self.cfg_path[key])

                            ### path config check
                            ugroup = None
                            for cfg in cfg_path:
                                if cfg.re.fullmatch(pin):
                                    for ln, *cmd in cfg[fid]:
                                        if ln and cmd[0] == 'u':
                                            # check if path move to user group
                                            if cmd[1] == 'slk' and CMP_OP[cmd[2]](slk, cmd[3]):
                                                ugroup = cmd[4]
                                            elif cmd[1] == 'act' and CMP_OP[cmd[2]](act, cmd[3]):
                                                ugroup = cmd[4]

                            ### add data to path table
                            if ugroup is not None:
                                org_group = gtable.name
                                if ugroup in ttable:
                                    gtable2 = ttable[ugroup]
                                elif self.is_multi:
                                    modify, ptable = [False, False], [[], []]
                                    gtable2 = GroupTable(ugroup, True, modify, ptable)
                                    ttable[ugroup] = gtable2
                                else:
                                    gtable2 = GroupTable(ugroup, True, [False], [[]])
                                    ttable[ugroup] = gtable2
                                gtable2.ptable[fid].append([pin, sc, req, act, slk, org_group])
                            else:
                                gtable2 = gtable
                                gtable2.ptable[fid].append([pin, sc, req, act, slk, ""])

                            ### add data to sum table
                            if fid == 1:
                                if gtable2.sum[GTT.RW] > slk:
                                    gtable2.sum[GTT.RW] = slk
                                gtable2.sum[GTT.RT] += slk
                                gtable2.sum[GTT.RN] += 1
                            else:
                                if gtable2.sum[GTT.LW] > slk:
                                    gtable2.sum[GTT.LW] = slk
                                gtable2.sum[GTT.LT] += slk
                                gtable2.sum[GTT.LN] += 1

                            is_act, path = False, []
                    else:
                        state = IDLE
        
        self._update_summary()
        # _print_cons_table(self.cons_table)    # debug

    def _update_summary(self):
        """Update summary information."""
        for vtype, vtable in self.cons_table.items():
            for gname, gt in vtable.items():
                if self.is_multi:
                    gt.update_diff()
                for cfg in self.cfg_grp.get(vtype, []):
                    if cfg.re.fullmatch(gname):
                        self._group_cfg_check(gt, GTT.LW, cfg['l'])
                        if self.is_multi:
                            self._group_cfg_check(gt, GTT.RW, cfg['r'])
                            self._group_cfg_check(gt, GTT.DW, cfg['d'])

    def _group_cfg_check(self, gt, wns_id, cfg):
        wns, tns, nvp = range(wns_id, wns_id+3)
        for ln, *cmd in cfg:
            if ln and cmd[0] == 'h':
                if len(cmd) == 2:
                    gt.sum[GTT.MAK] = cmd[-1]
                elif cmd[1] == 'wns' and CMP_OP[cmd[2]](gt.sum[wns], cmd[3]):
                    gt.sum[GTT.MAK] = cmd[-1]
                elif cmd[1] == 'tns' and CMP_OP[cmd[2]](gt.sum[tns], cmd[3]):
                    gt.sum[GTT.MAK] = cmd[-1]
                elif cmd[1] == 'nvp' and CMP_OP[cmd[2]](gt.sum[nvp], cmd[3]):
                    gt.sum[GTT.MAK] = cmd[-1]
            elif ln and cmd[0] == 'm':
                if len(cmd) == 2:
                    gt.sum[-1] = f"{self.cfg_msg[cmd[-1]]},"
                elif cmd[1] == 'wns' and CMP_OP[cmd[2]](gt.sum[wns], cmd[3]):
                    gt.sum[-1] = f"{self.cfg_msg[cmd[-1]]},"
                elif cmd[1] == 'tns' and CMP_OP[cmd[2]](gt.sum[tns], cmd[3]):
                    gt.sum[-1] = f"{self.cfg_msg[cmd[-1]]},"
                elif cmd[1] == 'nvp' and CMP_OP[cmd[2]](gt.sum[nvp], cmd[3]):
                    gt.sum[-1] = f"{self.cfg_msg[cmd[-1]]},"

    def print_summary(self):
        """Print summary for single report."""
        head  = f"   {'Group'.ljust(self.gcol_w)}"
        head += f"   {'WNS'.ljust(self.wns_w)}"
        head += f"   {'TNS'.ljust(self.tns_w)}"
        head += f"   {'NVP'.ljust(self.nvp_w)}  "

        div_len = self.gcol_w + self.wns_w + self.tns_w + self.nvp_w + 9
        div = "   " + "=" * div_len

        data_fs  = f"{{:3}}{{:{self.gcol_w}}}   "
        data_fs += f"{{:< {self.wns_w}.4f}}   "
        data_fs += f"{{:< {self.tns_w}.4f}}   "
        data_fs += f"{{:<{self.nvp_w}.0f}}  {{}}"

        for vtype, vtable in self.cons_table.items():
            print("====== {}".format(vtype))
            print(head, div, sep='\n')
            ugt = []
            for gt in vtable.values():
                if vtype in NOGRP_CONS and len(vtable) == 1:
                    gt.sum[GTT.GRP] = vtype
                if gt.user:
                    ugt.append(gt)
                else:
                    msg = '' if gt.sum[-1] == '' else f"({gt.sum[-1][:-1]})"
                    print(data_fs.format(*gt.sum[GTT.MAK:GTT.LN+1], msg))
            for gt in ugt:
                    msg = '' if gt.sum[-1] == '' else f"({gt.sum[-1][:-1]})"
                    print(data_fs.format(*gt.sum[GTT.MAK:GTT.LN+1], msg))
            print()

    def print_summary2(self):
        """Print summary for multi reports."""
        shead_f = lambda x: "=+={}== {}==={}".format("".ljust(self.wns_w, '='),
                                                      x.ljust(self.tns_w, '='),
                                                     "".ljust(self.nvp_w, '=')) 

        shead = "   {}{}{}{}=+".format("".ljust(self.gcol_w, '='),
                                       shead_f("Left "),
                                       shead_f("Right "),
                                       shead_f("Diff "))

        head = " | {}   {}   {}".format("WNS".ljust(self.wns_w),
                                        "TNS".ljust(self.tns_w),
                                        "NVP".ljust(self.nvp_w))
        head = "   {0}{1}{1}{1} |".format("Group".ljust(self.gcol_w), head)

        div = "=" * (self.wns_w + self.tns_w + self.nvp_w + 9)
        div = "   " + "=" * self.gcol_w + div * 3 + "=+"

        data_fs  = f" | {{:< {self.wns_w}.4f}}"
        data_fs += f"   {{:< {self.tns_w}.4f}}"
        data_fs += f"   {{:<{self.nvp_w}.0f}}"
        data_fs  = f"{{:3}}{{:{self.gcol_w}}}" + data_fs * 2 \
                   + f" | {{:< {self.wns_w}.4f}}" \
                   + f"   {{:< {self.tns_w}.4f}}" \
                   + f"   {{:<+{self.nvp_w}.0f}} | {{}}"

        for vtype, vtable in self.cons_table.items():
            print("====== {}".format(vtype))
            print(shead, head, div, sep='\n')
            # print(head)
            # print(div)
            ugt = []
            for gt in vtable.values():
                if vtype in NOGRP_CONS and len(vtable) == 1:
                    gt.sum[GTT.GRP] = vtype
                if gt.user:
                    ugt.append(gt)
                else:
                    msg = '' if gt.sum[-1] == '' else f"({gt.sum[-1][:-1]})"
                    print(data_fs.format(*gt.sum[GTT.MAK:GTT.DN+1], msg))
            for gt in ugt:
                    msg = '' if gt.sum[-1] == '' else f"({gt.sum[-1][:-1]})"
                    print(data_fs.format(*gt.sum[GTT.MAK:GTT.DN+1], msg))
            print()


