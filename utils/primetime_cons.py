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
        'group_column_width': ('gcol_w', 48),
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
            print("\n=== cons_cfg (path)")
            for key, value in cons_cfg['p'].items():
                print(f"{key}: {value}")
        elif type_ == 'g':
            print("\n=== cons_cfg (group)")
            for key, value in cons_cfg['g'].items():
                print(f"{key}: {value}")
        elif type_ == 'm':
            print("\n=== cons_cfg (message)")
            for key, value in cons_cfg['m'].items():
                print(f"{key}: {value}")
        else:
            print(f"{type_}: {content}")
    print()
    if end:
        exit(1)
    import pdb; pdb.set_trace()


class PathTableTitle(IntEnum):
    PIN, SC, REQ, ACT, SLK, ORGP = range(6)


class GroupTableTitle(IntEnum):
    GRP = 0
    LW, LT, LN = range(1, 4)
    RW, RT, RN = range(4, 7)
    DW, DT, DN = range(7, 10)
    MAK, COM = range(10, 12)


@dataclass (slots=False)
class GroupTable:
    name: str
    user: bool
    modify: list[bool]
    ptable: list[list]
    def __post_init__(self):
        self.summary = [self.name] + [0.0] * 9 + [''] * 2
    def update_diff(self):
        for l, r, d in zip(*[range(1, 4), range(4, 7), range(7, 10)]):
            self.summary[d] = self.summary[l] - self.summary[r]


def _print_cons_table(table: dict):
    """"Print constraint table (for debug)."""
    gtt = GroupTableTitle
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
                divide = sst.Divider(lsh=sst.Lsh(), bound=sst.Bound('+-', '-+'),
                                     cross=['-+-'] * 6, col_len=[12, 2, 3, 3, 3, 4],
                                     border='-' * 6)
                tblock = sst.Block(lsh=sst.Lsh(), bound=sst.Bound('| ', ' |'),
                                   border=[' | '] * 6, col_len=divide.col_len,
                                   align='l' * 6, 
                                   data=[[f'PIN (RID:{rid:2})', 'SC', 'REQ', 'ACT', 'SLK', 'ORGP']])
                dblock = sst.Block(lsh=sst.Lsh(), bound=sst.Bound('| ', ' |'),
                                   border=[' | '] * 6, col_len=divide.col_len,
                                   align='l' * 6, data=ptable)
                dblock.update_col_len()
                print_table = sst.SimpleTable()
                print_table.table.append(divide)
                print_table.table.append(tblock)
                print_table.table.append(divide)
                print_table.table.append(dblock)
                print_table.table.append(divide)
                print()
                print_table.draw()
                if rid == 1:
                    print(">>> Summary(WNS|TNS|NVP): {: 9.4f}, {: 9.4f}, {: 9.4f}".format(
                            gtable.summary[gtt.RW],
                            gtable.summary[gtt.RT],
                            gtable.summary[gtt.RN],
                         ))
                else:
                    print(">>> Summary(WNS|TNS|NVP): {: 9.4f}, {: 9.4f}, {: 9.4f}".format(
                            gtable.summary[gtt.LW],
                            gtable.summary[gtt.LT],
                            gtable.summary[gtt.LN],
                         ))
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
        self.gtitle = GroupTableTitle
        self.cons_num = 0
        self.cons_table = {} 
        # self.sum_tables = {}
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
        ST_IDLE, ST_PREFIX, ST_PARSING = range(3)
        grp_re = re.compile(r"(?P<t>[\w\/]+)(?:\s+\('(?P<g>[\w\/]+)'\sgroup\))?")
        self.cons_num = len(rpt_fps[:2])

        for fid, rpt_fp in enumerate(rpt_fps[:2]):
            if os.path.splitext(rpt_fp)[1] == '.gz':
                fp = gzip.open(rpt_fp, mode='rt')
            else:
                fp = open(rpt_fp)

            state, is_dmsa = ST_IDLE, False
            line, fno = fp.readline(), 1
            while line:
                line = line.strip()
                if not (toks:=line.split()):
                    pass
                elif state == ST_IDLE and toks[0][0] == '*':
                    state = ST_PREFIX
                elif state == ST_PREFIX and toks[0][0] == '*':
                    state = ST_PARSING
                elif state == ST_PREFIX and toks[0] == 'Design':
                    if toks[1] == 'multi_scenario':
                        is_dmsa = True
                elif state == ST_PARSING:
                    m = grp_re.fullmatch(line)
                    if m and m['t'] in CONS_TYPE:
                        group = '**default**' if m['g'] is None else m['g']
                        fno = self._parse_group(fid, fp, fno, m['t'], group, is_dmsa)
                line, fno = fp.readline(), fno+1
            fp.close()

        _print_cons_table(self.cons_table)    # debug
        # self._create_sum_table()

    def _parse_group(self, fid: int, fp, fno: int, vtype: str, group: str, 
                     is_dmsa: bool) -> int:
        """
        Parsing a violation group.

        Parameters
        ----------
        fid : int
            File id of the report.
        fp : file
            File object of the report.
        fno : int
            Current line number of the report (before parsing).
        vtype : str
            Violation type of the group
        group : str
            Path group name
        is_dmsa : bool 
            If current report is a DMSA report?

        Returns
        -------
        fno : int
            Current line number of the report (after parsing).
        """
        start_par = False   # start parsing
        start_ana = False   # start path analysis

        ttable = self.cons_table.setdefault(vtype, {})
        if group in ttable:
            gtable = ttable[group]
        else:
            modify = [False] * self.cons_num
            ptable = [[] for i in range(self.cons_num)]
            ttable[group] = (gtable:=GroupTable(group, False, modify, ptable))

        path = []
        line, fno = fp.readline(), fno+1
        while line:
            toks = line.strip().split()
            if start_par:
                path.extend(toks)
            if not start_par:
                if toks and toks[0][0] == '-':
                    start_par = True
            elif not toks:
                break
            elif path[-1] == '(VIOLATED)':
                start_ana, cid, pulse_chk = True, -2, False
            elif path[-1] == 'digits)':
                start_ana, cid, pulse_chk = True, -5, False
            elif len(path) >= 2 and path[-2] == '(VIOLATED)':
                start_ana, cid, pulse_chk = True, -3, True
            elif len(path) >= 2 and path[-2] == 'digits)':
                start_ana, cid, pulse_chk = True, -6, True

            if start_ana:
                slk, cid = float(path[cid]), cid-1
                act, cid = float(path[cid]), cid-1
                req, cid = float(path[cid]), cid-1 
                sc, cid = (path[cid], cid-1) if is_dmsa else ("", cid)

                if pulse_chk:
                    pulse_type = ' '.join(path[1:cid+1])[1:-1].split()[-1]
                    pgroup = f"{path[-1]},{pulse_type}"
                    if pgroup in ttable:
                        gtable2 = ttable[pgroup]
                    else:
                        modify = [False] * self.cons_num
                        ptable = [[] for i in range(self.cons_num)]
                        ttable[pgroup] = (gtable2:=GroupTable(pgroup, False, modify, ptable))
                else:
                    gtable2 = gtable

                pin = path[0]
                start_ana, path = False, []

                ### path config check
                key1 = f"{vtype}:{group}"
                key2 = f"{vtype}:*"
                cfg_path = (self.cfg_path.get(key1, []) + 
                            self.cfg_path.get(key2, []))                
                ugroup = None

                for cfg in cfg_path:
                    if cfg.re.fullmatch(pin):
                        for ln, *cmd in cfg[fid]:
                            if ln and cmd[0] == 'u':
                                # check if path move to user group
                                if CMP_OP[cmd[2]](slk, cmd[3]):
                                    ugroup = cmd[4]

                if ugroup is not None:
                    org_group = gtable2.name
                    gtable2.modify[fid] = True
                    if ugroup in ttable:
                        gtable2 = ttable[ugroup]
                    else:
                        modify = [False] * self.cons_num
                        ptable = [[] for i in range(self.cons_num)]
                        ttable[ugroup] = (gtable2:=GroupTable(ugroup, True, modify, ptable))
                    gtable2.ptable[fid].append([pin, sc, req, act, slk, org_group])
                else:
                    gtable2.ptable[fid].append([pin, sc, req, act, slk, ""])

                if fid == 1:
                    if gtable2.summary[self.gtitle.RW] > slk:
                        gtable2.summary[self.gtitle.RW] = slk
                    gtable2.summary[self.gtitle.RT] += slk
                    gtable2.summary[self.gtitle.RN] += 1
                else:
                    if gtable2.summary[self.gtitle.LW] > slk:
                        gtable2.summary[self.gtitle.LW] = slk
                    gtable2.summary[self.gtitle.LT] += slk
                    gtable2.summary[self.gtitle.LN] += 1

            line, fno = fp.readline(), fno+1
        return fno

#     def _create_sum_table(self):
#         """
#         Create summary table.
#         """
#         stable = self.sum_tables
#         ustable = {}
#         hid = None      # header id

#         def update_gtable(rid: int, rcnt: int, gtable: SimpleTable, 
#                           rkey: str, pgroup: str, slk: float):
#             """
#             Parameters
#             ----------
#             rid : int
#                 Report ID.
#             rcnt : int
#                 Number of constraint reports.
#             gtable : SimpleTable
#                 Group table.
#             rkey : str
#                 Row hash key.
#             pgroup : str
#                 Path group name
#             slk : float
#                 Path slack
#             """
#             if rkey not in gtable.index.id:
#                 gtable.add_row(
#                     key=rkey, title='', 
#                     data=[pgroup, slk, slk, 1, 0, 0, 0, 0, 0, 0],
#                     border=Border(False, False, False, False))
#                 gtable.attr[-1, COM].border.set(
#                         False, False, False, False)
#                 if rcnt > 1:
#                     for ckey in (LW, LT, RW, RT, DW, DT):
#                         gtable.attr[-1, ckey].fs = '{: .4f}'
#                     for ckey in (LW, RW, DW):
#                         gtable.attr[-1, ckey].border.left = True
#                     for ckey in (LN, RN, DN):
#                         gtable.attr[-1, ckey].fs = '{: d}'
#                         gtable.attr[-1, ckey].border.right = True
#                 else:
#                     for ckey in (LW, LT):
#                         gtable.attr[-1, ckey].fs = '{: .4f}'
#             else:
#                 if rid == 0:
#                     if slk < gtable[rkey, LW]:
#                         gtable[rkey, LW] = slk
#                     gtable[rkey, LT] += slk
#                     gtable[rkey, LN] += 1 
#                 else:
#                     if slk < gtable[rkey, RW]:
#                         gtable[rkey, RW] = slk
#                     gtable[rkey, RT] += slk
#                     gtable[rkey, RN] += 1 

#         top_bor = False if (rcnt:=len(self.cons_table)) == 1 else True
#         table_bor = Border(top_bor, False, False, False)
#         head_bor = Border(left=False, right=False)

#         for rid in range(rcnt):
#             ctable = self.cons_table[rid]
#             if self.plot_grp is not None:
#                 self.plot_data.append([])

#             for r in range(ctable.max_row):
#                 # create new group table for the new violation type
#                 if (vtype:=ctable[r,'type']) not in stable:
#                     gtable = SimpleTable(heads=self._sum_hd, border=table_bor,
#                                          lsh=2, hpat='=', hcpat='=', 
#                                          cpat_force_on=True)
#                     gtable.set_head_attr(border=head_bor)

#                     # gen column id tag
#                     if hid is None:
#                         hid = gtable.header.id
#                         GRP, COM = hid['group'], hid['comm']
#                         LW, LT, LN = hid['lwns'], hid['ltns'], hid['lnvp']
#                         RW, RT, RN = hid['rwns'], hid['rtns'], hid['rnvp']
#                         DW, DT, DN = hid['dwns'], hid['dtns'], hid['dnvp']

#                     # adjust table style
#                     gtable.header[COM].border.set(
#                             False, False, False, False)
#                     gtable.set_col_attr(GRP, width=self.gcol_w)

#                     if rcnt > 1:
#                         for key in (LW, RW, DW):
#                             gtable.set_col_attr(key, width=self.wns_w)
#                             gtable.header[key].border.left = True
#                         for key in (LT, RT, DT):
#                             gtable.set_col_attr(key, width=self.tns_w)
#                         for key in (LN, RN, DN):
#                             gtable.set_col_attr(key, width=self.nvp_w)
#                             gtable.header[key].border.right = True
#                     else:
#                         gtable.set_col_attr(LW, width=self.wns_w)
#                         gtable.set_col_attr(LT, width=self.tns_w)
#                         gtable.set_col_attr(LN, width=self.nvp_w)

#                     stable[vtype] = gtable
#                     ustable[vtype] = (ugtable:=copy.deepcopy(gtable))
#                 else:
#                     gtable, ugtable = stable[vtype], ustable[vtype]

#                 # dicide group name
#                 if vtype in self._nogrp_cons:
#                     pgroup = vtype
#                 elif vtype in self._clk_cons:
#                     pgroup = "({1:4}) {0}".format(*ctable[r,'attr'].split(','))
#                 else:
#                     pgroup = ctable[r,'group']

#                 # user group check
#                 is_del = False
#                 if (upgroup:=ctable[r, 'ugroup']) is not None:
#                     if not ctable[r, 'is_og_rsv']:
#                         is_del = True
#                     gkey, slk = f'{vtype}:{upgroup}', ctable[r,'slk']
#                     update_gtable(rid, rcnt, ugtable, gkey, f'(user) {upgroup}', slk)
#                     if self.plot_grp is not None and self.plot_grp == gkey:
#                         self.plot_data[rid].append(slk)

#                 # get data value and update to the table
#                 # delete check priority: 
#                 #   is_og_rsv > is_rsv > is_del
#                 is_del |= ctable[r,'is_del'] and not ctable[r,'is_rsv']
#                 if not is_del:
#                     gkey, slk = f'{vtype}:{pgroup}', ctable[r,'slk']
#                     update_gtable(rid, rcnt, gtable, gkey, pgroup, slk)
#                     if self.plot_grp is not None and self.plot_grp == gkey:
#                         self.plot_data[rid].append(slk)

#         ## group config check
#         for vtype, gtable in stable.items():
#             # merge user group table
#             if vtype in ustable:
#                 for row in ustable[vtype]._table:
#                     gtable.add_row(
#                         key=f'{vtype}:{row[0]}', title='',
#                         data=row,
#                         border=Border(False, False, False, False))

#             # update title if single report mode
#             if rcnt == 1:
#                 for key in (LW, LT, LN):
#                     title = gtable.header[key].title
#                     gtable.header[key].title = title[2:]
#             else:
#                 for row in gtable._table:
#                     row[DW] = row[LW] - row[RW]
#                     row[DT] = row[LT] - row[RT]
#                     row[DN] = row[LN] - row[RN]

#             if (gclist:=self.grp_cfg.get(vtype)):
#                 # condition check
#                 for row in gtable._table:
#                     for gcons in gclist:
#                         if gcons.re.fullmatch(row[GRP]):
#                             for i, (ln, cmd) in enumerate(gcons.l):
#                                 cid = hid[f"l{cmd[1]}"]
#                                 if self._cmp_op[cmd[2]](row[cid], cmd[3]):
#                                     tag = f"w{ln}L{i}"
#                                     if cmd[4] != None and cmd[4] in self.gtag_cfg:
#                                         row[COM] += ", {}: {}".format(tag, self.gtag_cfg[cmd[4]])
#                                     else:
#                                         row[COM] += ", {}".format(tag)
#                                     if cmd[4] != None and cmd[4] in self.gmsg_cfg:
#                                         cond = "{}:{}{}".format(*cmd[1:4])
#                                         self.comm_set.add("{:10}{:20}{}".format(f"{tag}:", cond, self.gmsg_cfg[cmd[4]]))
#                                     else:
#                                         self.comm_set.add("{0:10}{1}:{2}{3}".format(f"{tag}:", *cmd[1:]))

#                             if rcnt > 1:
#                                 for i, (ln, cmd) in enumerate(gcons.r):
#                                     cid = hid[f"r{cmd[1]}"]
#                                     if self._cmp_op[cmd[2]](row[cid], cmd[3]):
#                                         row[COM] += ", {}".format(msg:=f"w{ln}R{i}")
#                                         self.comm_set.add("{0:10}{1}:{2}{3}".format(f"{msg}:", *cmd[1:]))

#                                 for i, (ln, cmd) in enumerate(gcons.d):
#                                     cid = hid[f"d{cmd[1]}"]
#                                     if self._cmp_op[cmd[2]](row[cid], cmd[3]):
#                                         row[COM] += ", {}".format(msg:=f"w{ln}D{i}")
#                                         self.comm_set.add("{0:10}{1}:{2}{3}".format(f"{msg}:", *cmd[1:]))

#                 # adjust comment string
#                 for row in gtable._table:
#                     if (msg:=row[COM]) != "":
#                         row[COM] = f"({msg[2:]})"


