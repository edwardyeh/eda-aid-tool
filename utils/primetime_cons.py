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

CMP_OP = { '>' : lambda a, b: a > b,
           '<' : lambda a, b: a < b,
           '==': lambda a, b: a == b,
           '>=': lambda a, b: a >= b,
           '<=': lambda a, b: a <= b }


_PATH_OP = set()
for i in ('u'):
    _PATH_OP.update((f"{i}:req", f"{i}:act", f"{i}:slk"))


@dataclass (slots=False)
class _ConsPathOp:
    re: RePat = None
    cmd: list[Any] = field(init=False)
    def __post_init__(self):
        ### cmd: (fno, opteration)
        self.cmd = {'u': None}


_GROUP_OP = set()
for i in ('t', 's', 'm', 'c'):
    _GROUP_OP.update((f"{i}:wns", f"{i}:tns", f"{i}:nvp"))


@dataclass (slots=False)
class _ConsGroupOp:
    re: RePat = None
    cmd: list[Any] = field(init=False)
    def __post_init__(self):
        ### cmd: (fno, opteration)
        self.cmd = {'t': None, 's': None, 'm': None, 'c': None, 'r': None}


@dataclass (slots=False)
class _ConsVioOp:
    cmd: dict = field(init=False)
    def __post_init__(self):
        ### cmd: (fno, opteration)
        self.cmd = {'go': None, 'gh': None, 'ro': None}


class PTT(IntEnum):  # PathTableTitle
    PIN, SC, REQ, ACT, SLK, ORGP = range(6)


class GTT(IntEnum):  # GroupTableTitle
    MAK, GRP, TAG = range( 0,  3)
    LW, LT, LN    = range( 3,  6)
    RW, RT, RN    = range( 6,  9)
    DW, DT, DN    = range( 9, 12)


@dataclass (slots=False)
class GroupTable:
    name:   str
    user:   bool
    modify: list[bool]
    ptable: list[list]
    sum:    list[Any] = field(init=False)
    def __post_init__(self):
        if len(self.modify) == 2:
            self.sum = ['', self.name, ''] + [0.0] * 9 + ['']
        else:
            self.sum = ['', self.name, ''] + [0.0] * 3 + ['']
    def update_diff(self):
        for l, r, d in zip(*[range(3, 6), range(6, 9), range(9, 12)]):
            self.sum[d] = self.sum[l] - self.sum[r]


def _parse_path_cmd(no: int, cmd: str) -> tuple[Any, ...]:
    """
    Parsing config commands (path).
    """
    if cmd[1:3] == "::":
        return no, cmd[3:]
    if cmd[:2] in ("u:", ):
        m = re.fullmatch(r"(\w:\w{3})([><=]{1,2})([\-\d\.]+):(\S+)", cmd)
        if m[1] not in _PATH_OP:
            raise SyntaxError(f"Error: config syntax error (ln:{no})")
        return no, m[1][2:], m[2], float(m[3]), m[4]

    raise SyntaxError(f"Error: config syntax error (ln:{no})")


def _parse_group_cmd(no: int, cmd: str) -> tuple[Any, ...]:
    """
    Parsing config commands (group).
    """
    if cmd[1:3] == "::":
        return no, cmd[3:]
    if cmd[:2] in {"t:", "s:", "m:", "c:"}:
        m = re.fullmatch(r"(\w:\w{3})([><=]{1,2})([\-\d\.]+):(\S+)", cmd)
        if m[1] not in _GROUP_OP:
            raise SyntaxError(f"Error: config syntax error (ln:{no})")
        return no, m[1][2:], m[2], float(m[3]), m[4]

    raise SyntaxError(f"Error: config syntax error (ln:{no})")


def _load_cons_cfg(cfg_fp: str, is_multi: bool) -> dict:
    """
    Load configurations from the file to database.

    Parameters
    ----------
    cfg_fp : str
        Configuration file path

    Returns
    -------
    cons_cfg : dict
        The config dictionary base on the config data structure.
    """
    attr = {
        "grp_width": ("grp_w", [48, False]),  # size/is_user_defined?
        "wns_width": ("wns_w", [12, False]),
        "tns_width": ("tns_w", [12, False]),
        "nvp_width": ("nvp_w", [ 6, False]),
        "clean_sign_enable": ("clr_en", False),
        "clean_sign": ("clr_sign", "***"),
    }

    bool_map = {
        "true": True,
        "false": False
    }

    cons_cfg = dict(attr.values())
    # path/group/message/violation
    cons_cfg.update({ 'p': {}, 'g': {}, 'v': {}, 'm': {} })  
    if cfg_fp is None:
        return cons_cfg

    with open(cfg_fp, 'r') as fp:
        for fno, line in enumerate(fp, 1):
            if (line:=line.split('#')[0].strip()):
                try:
                    key, value, *other = line.split(':')
                    key, value = key.strip(), value.strip()

                    if key in attr:
                        key = attr[key][0]  # update key to real index
                        if key in {"grp_w", "wns_w", "tns_w", "nvp_w"}:
                            cons_cfg[key] = [int(value), True]
                        elif key == "clr_en":
                            cons_cfg[key] = bool_map[value.lower()]
                        elif key == "clr_sign":
                            cons_cfg[key] = value

                    elif key == 'p':
                        select, *cmd_list = line[2:].split()
                        vtype, group, path = select.split(':')
                        gid = ':'.join((vtype, group))
                        plist = cons_cfg['p'].setdefault(gid, [])
                        plist.append(pobj:=_ConsPathOp(re=re.compile(path)))
                        for cmd in cmd_list:
                            if cmd[:1] == 'u':
                                pobj.cmd[cmd[:1]] = _parse_path_cmd(fno, cmd)
                            else:
                                raise SyntaxError(
                                    f"[ATTR] Unknown path command ({cmd}).")

                    elif key == 'g':
                        select, *cmd_list = line[2:].split()
                        vtype, group = select.split(':')
                        glist = cons_cfg['g'].setdefault(vtype, [])
                        glist.append(gobj:=_ConsGroupOp(re=re.compile(group)))
                        for cmd in cmd_list:
                            if cmd[:1] in {'t', 's', 'm', 'c'}:
                                gobj.cmd[cmd[:1]] = _parse_group_cmd(fno, cmd)
                            elif cmd[:1] == 'r':
                                ctype, pat, rep, *_ = cmd.split(':')
                                gobj.cmd[cmd[:1]] = (fno, re.compile(pat), rep)
                            else:
                                raise SyntaxError(
                                    f"[ATTR] Unknown group command ({cmd}).")

                    elif key == 'v':
                        vtype, *cmd_list = line[2:].split()
                        for cmd in cmd_list:
                            if cmd[:2] == 'go':
                                rid, target, order = cmd[3:].split(':')
                                if is_multi and rid == 's':
                                    continue
                                if not is_multi and rid != 's':
                                    continue
                                vobj = cons_cfg['v'].setdefault(vtype, _ConsVioOp())

                                if rid == 'r':
                                    cid = GTT.RW
                                elif rid == 'd':
                                    cid = GTT.DW
                                else:
                                    cid = GTT.LW

                                if target == 'tns':
                                    cid += 1
                                elif target == 'nvp':
                                    cid += 2

                                order = 0 if order == 'inc' else 1
                                vobj.cmd['go'] = (fno, cid, order)

                            elif cmd[:2] == 'gh':
                                pass
                            elif cmd[:2] == 'co':
                                pass
                            else:
                                raise SyntaxError(
                                    f"[ATTR] Unknown violation command ({cmd}).")

                    elif key == 'm':
                        msg = other[0].strip(" \"\'")
                        cons_cfg['m'][value] = msg

                    elif key != '':
                        print(f"[WARNING] unknown operation '{key}', ignore. " + 
                              f"(CFG-001)")

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

    def __init__(self, cfg_fp: [None|str]=None, is_multi: bool=False):
        """
        Parameters
        ----------
        cfg_fp : {None, str}, optional
            Configuration file path, default is None.
        """
        cons_cfg = _load_cons_cfg(cfg_fp, is_multi)
        # _print_cons_cfg(cons_cfg, True)    # debug
        ### Attributes
        self.grp_w = cons_cfg["grp_w"]
        self.wns_w = cons_cfg["wns_w"]
        self.tns_w = cons_cfg["tns_w"]
        self.nvp_w = cons_cfg["nvp_w"]
        self.clr_en = cons_cfg["clr_en"]
        self.clr_sign = cons_cfg["clr_sign"]
        self.cfg_path = cons_cfg['p']
        self.cfg_grp = cons_cfg['g']
        self.cfg_vio = cons_cfg['v']
        self.cfg_msg = cons_cfg['m']
        ### Data
        self.is_multi = is_multi
        self.cons_table = defaultdict(dict) 
        self.sum_table = {}
        ### Plot
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
        MODE, TYPE, HEAD, VIO_CASE1, VIO_CASE2 = range(5)
        state = MODE

        # Parsing violation paths
        for fid, rpt_fp in enumerate(rpt_fps[:2]):
            if os.path.splitext(rpt_fp)[1] == '.gz':
                fp = gzip.open(rpt_fp, mode='rt')
            else:
                fp = open(rpt_fp)

            for line in fp:
                toks = line.split()
                toks_len = len(toks)

                if state == MODE and toks_len and toks[0] == 'Design':
                    # Check the design is the single or multi scenario mode
                    is_dmsa = True if toks[2] == 'multi_scenario' else False
                    state = TYPE 

                elif state == TYPE and toks_len and toks[0] in CONS_TYPE:
                    # Get the constraint type and group name
                    # vtable: a violation path table of the specific type
                    vtype = toks[0]
                    group = toks[1][2:-1] if toks_len > 1 else '**default**'
                    state, vtable = HEAD, self.cons_table[vtype]

                elif state == HEAD and toks_len:
                    # Check the header to decide the path parsing format
                    if toks[0][0] == '-':
                        path, is_act = [], False
                        state = VIO_CASE2 if pre_toks[-1] == 'Clock' else VIO_CASE1
                    else:
                        pre_toks = toks.copy()

                elif state in {VIO_CASE1, VIO_CASE2}:
                    if toks_len:
                        pid = -1 if state == VIO_CASE1 else -2
                        path.extend(toks)
                        if path[pid] == '(VIOLATED)':
                            is_act, cid = True, (-2 if state == VIO_CASE1 else -3)
                        elif path[pid] == 'digits)':
                            is_act, cid = True, (-5 if state == VIO_CASE1 else -6)

                        if is_act:
                            slk, cid = float(path[cid]), cid-1
                            act, cid = float(path[cid]), cid-1
                            req, cid = float(path[cid]), cid-1 
                            sc = path[cid] if is_dmsa else ""
                            pin = path[0]

                            # Get group table of the specific group
                            if state == VIO_CASE2:
                                pulse_type = ' '.join(path[1:cid+1])[1:-1].split()[-1]
                                group = f"{path[-1]},{pulse_type}"

                            if group in vtable:
                                gtable = vtable[group]
                            elif self.is_multi:
                                modify, ptable = [False, False], [[], []]
                                gtable = GroupTable(group, False, modify, ptable)
                                vtable[group] = gtable
                            else:
                                modify, ptable = [False], [[]]
                                gtable = GroupTable(group, False, modify, ptable)
                                vtable[group] = gtable

                            cfg_path = []
                            if (key:=f"{vtype}:{group}") in self.cfg_path:
                                cfg_path.extend(self.cfg_path[key])
                            if (key:=f"{vtype}:*") in self.cfg_path:
                                cfg_path.extend(self.cfg_path[key])

                            # Path config check
                            path_info = (pin, req, act, slk)
                            ugroup = self._path_cfg_check(path_info, cfg_path)

                            # Add data to path table
                            if ugroup is not None:
                                gtable.modify[fid] = True
                                org_group = gtable.name
                                if ugroup in vtable:
                                    gtable2 = vtable[ugroup]
                                elif self.is_multi:
                                    modify, ptable = [False, False], [[], []]
                                    gtable2 = GroupTable(ugroup, True, modify, ptable)
                                    vtable[ugroup] = gtable2
                                else:
                                    gtable2 = GroupTable(ugroup, True, [False], [[]])
                                    vtable[ugroup] = gtable2
                                gtable2.ptable[fid].append([pin, sc, req, act, slk, org_group])
                            else:
                                gtable2 = gtable
                                gtable2.ptable[fid].append([pin, sc, req, act, slk, ""])

                            # Add data value to sum table
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
                        state = TYPE

        # Update the violation summary
        for vtype, vtable in self.cons_table.items():
            self.sum_table[vtype] = defaultdict(list)
            self.sum_table[vtype]["default"] = []
            for gname, gtable in vtable.items():
                gclass = "default"
                if self.is_multi:
                    gtable.update_diff()
                for cfg in self.cfg_grp.get(vtype, []):
                    if cfg.re.fullmatch(gname):
                        gclass = self._group_cfg_check(gtable, GTT.LW, cfg.cmd, gclass)
                self.sum_table[vtype][gclass].append(gtable)

        # For debug
        # _print_cons_table(self.cons_table)

    def _path_cfg_check(self, path_info, cfg_path):
        pin, req, act, slk = path_info
        ugroup = None
        for cfg in cfg_path:
            if cfg.re.fullmatch(pin):
                for ctype, value in cfg.cmd.items():
                    if value is None:
                        continue
                    ln, *cmd = value
                    if ctype == 'u':  # user group
                        if len(cmd) == 1:
                            ugroup = cmd[-1]
                        elif CMP_OP[cmd[1]](locals()[cmd[0]], cmd[2]):
                            ugroup = cmd[-1]
        return ugroup

    def _group_cfg_check(self, gtable, wns_id, cfg, gclass):
        wns, tns, nvp = range(wns_id, wns_id+3)
        for ctype, value in cfg.items():
            if value is None:
                continue
            ln, *cmd = value
            if ctype == 't':
                if len(cmd) == 1:
                    gtable.sum[GTT.TAG] = f"({cmd[-1]})"
                elif CMP_OP[cmd[1]](gtable.sum[locals()[cmd[0]]], cmd[2]):
                    gtable.sum[GTT.TAG] = f"({cmd[-1]})"
            elif ctype == 's':
                if len(cmd) == 1:
                    gtable.sum[GTT.MAK] = cmd[-1]
                elif CMP_OP[cmd[1]](gtable.sum[locals()[cmd[0]]], cmd[2]):
                    gtable.sum[GTT.MAK] = cmd[-1]
            elif ctype == 'm':
                if len(cmd) == 1:
                    gtable.sum[-1] = f"{self.cfg_msg[cmd[-1]]},"
                elif CMP_OP[cmd[1]](gtable.sum[locals()[cmd[0]]], cmd[2]):
                    gtable.sum[-1] = f"{self.cfg_msg[cmd[-1]]},"
            elif ctype == 'c':
                if len(cmd) == 1:
                    gclass = cmd[-1]
                elif CMP_OP[cmd[1]](gtable.sum[locals()[cmd[0]]], cmd[2]):
                    gclass = cmd[-1]
            elif ctype == 'r':
                try:
                    gtable.sum[GTT.GRP] = cmd[0].sub(cmd[1], gtable.sum[GTT.GRP])
                except Exception as e:
                    print("Error: Group config check error.\n" +
                          "  config ln: {}\n".format(ln) +
                          "  command:   {}\n".format(cmd))
                    raise e
        return gclass


    def print_summary(self):
        """Print summary for single report."""
        max_grp_w, max_nvp_w, tag_w = [0] * 3 
        for vtable in self.cons_table.values():
            for gtable in vtable.values():
                if (new_len := len(gtable.sum[GTT.GRP])) > max_grp_w:
                    max_grp_w = new_len
                if (new_len := len(str(int(gtable.sum[GTT.LN])))) > max_grp_w:
                    max_grp_w = new_len
                if (new_len := len(gtable.sum[GTT.TAG])) > tag_w:
                    tag_w = new_len

        grp_w = self.grp_w[0]
        if not self.grp_w[1] and max_grp_w > grp_w:
            grp_w = max_grp_w
        wns_w = self.wns_w[0]
        tns_w = self.tns_w[0]
        nvp_w = self.nvp_w[0]
        if not self.nvp_w[1] and max_nvp_w > nvp_w:
            nvp_w = max_nvp_w

        if tag_w == 0:
            grp_w2 = grp_w
        elif (grp_w - tag_w - 2) >= max_grp_w:
            grp_w2 = grp_w - tag_w
        else:
            grp_w2 = grp_w + 2
            grp_w += tag_w + 2

        head  = f"   {'Group'.ljust(grp_w)}"
        head += f"   {'WNS'.ljust(wns_w)}"
        head += f"   {'TNS'.ljust(tns_w)}"
        head += f"   {'NVP'.ljust(nvp_w)}  "

        div_len = grp_w + wns_w + tns_w + nvp_w + 9
        div = "   " + "=" * div_len

        data_fs  = f"{{:3}}{{:{grp_w2}}}{{:{tag_w}}}   "
        data_fs += f"{{:< {wns_w}.4f}}   "
        data_fs += f"{{:< {tns_w}.4f}}   "
        data_fs += f"{{:<{nvp_w}.0f}}  {{}}"

        class_fs = f"   {{:-<{grp_w}}}"

        for vtype, ctable in self.sum_table.items():
            print("====== {}".format(vtype))
            print(head, div, sep='\n')

            clist = list(ctable.items())
            for cname, vlist in clist[1:] + clist[:1]:
                if len(vlist) == 0:
                    continue

                if cname == "default" and len(clist) == 1:
                    pass
                elif cname == "default":
                    print(class_fs.format(f"------ other "))
                else:
                    print(class_fs.format(f"------ {cname} "))

                if vtype in self.cfg_vio:
                    _, sort_type, sort_order = self.cfg_vio[vtype].cmd['go']
                elif 'default' in self.cfg_vio:
                    _, sort_type, sort_order = self.cfg_vio['default'].cmd['go']
                else:
                    sort_type, sort_order = None, None

                if sort_type is not None:
                    vlist = sorted(vlist, key=lambda x: x.sum[sort_type], 
                                   reverse=sort_order)

                ugt = []
                for gt in vlist:
                    if vtype in NOGRP_CONS and len(vlist) == 1:
                        gt.sum[GTT.GRP] = vtype

                    if gt.sum[GTT.LN] == 0:
                        pass
                    elif gt.user and sort_type is None:
                        ugt.append(gt)
                    else:
                        msg = '' if gt.sum[-1] == '' else f"({gt.sum[-1][:-1]})"
                        print(data_fs.format(
                            *gt.sum[GTT.MAK:GTT.TAG+1], 
                            *gt.sum[GTT.LW:GTT.LN+1], 
                            msg
                        ))

                for gt in ugt:
                        msg = '' if gt.sum[-1] == '' else f"({gt.sum[-1][:-1]})"
                        print(data_fs.format(
                            *gt.sum[GTT.MAK:GTT.TAG+1], 
                            *gt.sum[GTT.LW:GTT.LN+1], 
                            msg
                        ))
            print()

    def print_summary_multi(self):
        """Print summary for multi reports."""
        max_grp_w, max_nvp_w, tag_w = [0] * 3 
        for vtable in self.cons_table.values():
            for gtable in vtable.values():
                if (new_len := len(gtable.sum[GTT.GRP])) > max_grp_w:
                    max_grp_w = new_len
                if (new_len := len(str(int(gtable.sum[GTT.LN])))) > max_grp_w:
                    max_grp_w = new_len
                if (new_len := len(str(int(gtable.sum[GTT.RN])))) > max_grp_w:
                    max_grp_w = new_len
                if (new_len := len(str(int(gtable.sum[GTT.DN])))) > max_grp_w:
                    max_grp_w = new_len
                if (new_len := len(gtable.sum[GTT.TAG])) > tag_w:
                    tag_w = new_len

        grp_w = self.grp_w[0]
        if not self.grp_w[1] and max_grp_w > grp_w:
            grp_w = max_grp_w
        wns_w = self.wns_w[0]
        tns_w = self.tns_w[0]
        nvp_w = self.nvp_w[0]
        if not self.nvp_w[1] and max_nvp_w > nvp_w:
            nvp_w = max_nvp_w

        if tag_w == 0:
            grp_w2 = grp_w
        elif (grp_w - tag_w - 2) >= max_grp_w:
            grp_w2 = grp_w - tag_w
        else:
            grp_w2 = grp_w + 2
            grp_w += tag_w + 2

        shead_f = lambda x: "=+={}== {}==={}".format("".ljust(wns_w, '='),
                                                      x.ljust(tns_w, '='),
                                                     "".ljust(nvp_w, '=')) 

        shead = "   {}{}{}{}=+".format("".ljust(grp_w, '='),
                                       shead_f("Left "),
                                       shead_f("Right "),
                                       shead_f("Diff "))

        head = " | {}   {}   {}".format("WNS".ljust(wns_w),
                                        "TNS".ljust(tns_w),
                                        "NVP".ljust(nvp_w))
        head = "   {0}{1}{1}{1} |".format("Group".ljust(grp_w), head)

        div = "=" * (wns_w + tns_w + nvp_w + 9)
        div = "   " + "=" * grp_w + div * 3 + "=+"

        data_fs  = f" | {{:< {wns_w}.4f}}"
        data_fs += f"   {{:< {tns_w}.4f}}"
        data_fs += f"   {{:<{nvp_w}.0f}}"
        data_fs  = f"{{:3}}{{:{grp_w2}}}{{:{tag_w}}}" \
                   + data_fs * 2 \
                   + f" | {{:< {wns_w}.4f}}" \
                   + f"   {{:< {tns_w}.4f}}" \
                   + f"   {{:<+{nvp_w}.0f}} | {{}}"

        class_fs = "-+-" + "-" * (wns_w + tns_w + nvp_w + 6)
        class_fs = f"   {{:-<{grp_w}}}" + class_fs * 3 + '-+'

        for vtype, ctable in self.sum_table.items():
            print("====== {}".format(vtype))
            print(shead, head, div, sep='\n')

            clist = list(ctable.items())
            for cname, vlist in clist[1:] + clist[:1]:
                if len(vlist) == 0:
                    continue

                if cname == "default" and len(clist) == 1:
                    pass
                elif cname == "default":
                    print(class_fs.format(f"------ other "))
                else:
                    print(class_fs.format(f"------ {cname} "))

                if vtype in self.cfg_vio:
                    _, sort_type, sort_order = self.cfg_vio[vtype].cmd['go']
                elif 'default' in self.cfg_vio:
                    _, sort_type, sort_order = self.cfg_vio['default'].cmd['go']
                else:
                    sort_type, sort_order = None, None

                if sort_type is not None:
                    vlist = sorted(vlist, key=lambda x: x.sum[sort_type], 
                                   reverse=sort_order)

                ugt = []
                for gt in vlist:
                    if vtype in NOGRP_CONS and len(vlist) == 1:
                        gt.sum[GTT.GRP] = vtype

                    if gt.sum[GTT.LN] == 0 and gt.sum[GTT.RN] == 0:
                        pass
                    elif gt.user and sort_type is None:
                        ugt.append(gt)
                    else:
                        msg = '' if gt.sum[-1] == '' else f"({gt.sum[-1][:-1]})"
                        print(data_fs.format(
                            *gt.sum[GTT.MAK:GTT.TAG+1], 
                            *gt.sum[GTT.LW:GTT.DN+1], 
                            msg
                        ))

                for gt in ugt:
                        msg = '' if gt.sum[-1] == '' else f"({gt.sum[-1][:-1]})"
                        print(data_fs.format(
                            *gt.sum[GTT.MAK:GTT.TAG+1], 
                            *gt.sum[GTT.LW:GTT.DN+1], 
                            msg
                        ))
            print()


