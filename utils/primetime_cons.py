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
from re import Pattern as RePat
from typing import Any

from simpletools.text import (Align, Array, Border, Index, SimpleTable)


@dataclass (slots=True)
class ConsPathOp:
    re: RePat = None
    l: list = field(default_factory=list)  # cmd: [fno, opteration]
    r: list = field(default_factory=list)
    def __getitem__(self, key):
        if key == 'l': return self.l
        if key == 'r': return self.r


@dataclass (slots=True)
class ConsGroupOp:
    re: RePat = None
    l: list = field(default_factory=list)  # cmd: [fno, opteration]
    r: list = field(default_factory=list)
    d: list = field(default_factory=list)
    def __getitem__(self, key):
        if key == 'l': return self.l
        if key == 'r': return self.r
        if key == 'd': return self.d


@dataclass (slots=True)
class ConsUGroupOp:
    fno: int = 0
    re: RePat = None
    ugroup: str = None
    is_og_rsv: bool = None


class ConsReport:
    """
    Constraint violation report parser.
    """

    _path_hd = (('type', 'Violation.Type'), ('group', 'Path.Group'), 
                ('pin', 'Pin'), ('sc', 'Scenario'), ('arr', 'Arrival.Time'), 
                ('req', 'Required.Time'), ('slk', 'Slack'), 
                ('attr', 'Attributes'), ('off', 'Slack.Offset'), 
                ('is_rsv', 'Reserve?'), ('is_del', 'Delete?'), 
                ('ugroup', 'User.Group'), 
                ('is_og_rsv', 'Original.Group.Reserve?'))

    _sum_hd = (('group', 'Group'), 
               ('lwns', 'L-WNS'), ('ltns', 'L-TNS'), ('lnvp', 'L-NVP'),
               ('rwns', 'R-WNS'), ('rtns', 'R-TNS'), ('rnvp', 'R-NVP'),
               ('dwns', 'D-WNS'), ('dtns', 'D-TNS'), ('dnvp', 'D-NVP'),
               ('comm', ''))

    _grp_cons = ('max_delay/setup', 'min_delay/hold')
    _nogrp_cons = ('recovery', 'removal', 
                   'clock_gating_setup', 'clock_gating_hold', 
                   'max_capacitance', 'min_capacitance', 
                   'max_transition', 'min_transition')
    _clk_cons = ('clock_tree_pulse_width', 'sequential_tree_pulse_width', 
                 'sequential_clock_min_period')

    _cons_type_set = set(_grp_cons + _nogrp_cons + _clk_cons)

    _path_op = {'r:slk', 'd:slk'}
    _group_op = {'w:wns', 'w:tns', 'w:nvp'}

    _cmp_op = {
        '>' : lambda a, b: a > b,
        '<' : lambda a, b: a < b,
        '==': lambda a, b: a == b,
        '>=': lambda a, b: a >= b,
        '<=': lambda a, b: a <= b
    }

    def __init__(self, gcol_w: int=50, 
                 wns_w: int=16, tns_w: int=16, nvp_w: int=6, 
                 path_cfg: dict=None, grp_cfg: dict=None, ugrp_cfg: dict=None,
                 gtag_cfg: dict=None, gmsg_cfg: dict=None):
        """
        Parameters
        ----------
        gcol_w : int, optional
            The column width of the path group column.
        wns_w : int, optional
            The column width of the WNS.
        tns_w : int, optional
            The column width of the TNS.
        nvp_w : int, optional
            The column width of the NVP.
        path_cfg : dict, optional
            Configurations for paths.
        grp_cfg : dict, optional
            Configurations for path groups.
        ugrp_cfg : dict, optional
            Configurations for user-defined path groups.
        gtag_cfg : dict, optional
            Tags for group configurations.
        gmsg_cfg : dict, optional
            Messages for group configurations.
        """
        ### attributes
        self.gcol_w = gcol_w
        self.wns_w = wns_w
        self.tns_w = tns_w
        self.nvp_w = nvp_w
        self.path_cfg = {} if path_cfg is None else copy.deepcopy(path_cfg)
        self.grp_cfg = {} if grp_cfg is None else copy.deepcopy(grp_cfg)
        self.ugrp_cfg = {} if ugrp_cfg is None else copy.deepcopy(ugrp_cfg)
        self.gtag_cfg = {} if gtag_cfg is None else copy.deepcopy(gtag_cfg)
        self.gmsg_cfg = {} if gmsg_cfg is None else copy.deepcopy(gmsg_cfg)
        self.comm_set = set()
        ### data
        self.cons_tables = []
        self.sum_tables = {}

        self._parse_cfg_cmd()

    def _parse_cfg_cmd(self):
        """
        Parsing config commands.
        """
        for plist in self.path_cfg.values():
            for pobj in plist:
                for i, cmd in enumerate(pobj.l):
                    pobj.l[i] = (cmd[0], self._parse_path_cmd(cmd))
                for i, cmd in enumerate(pobj.r):
                    pobj.r[i] = (cmd[0], self._parse_path_cmd(cmd))

        for glist in self.grp_cfg.values():
            for gobj in glist:
                for i, cmd in enumerate(gobj.l):
                    gobj.l[i] = (cmd[0], self._parse_group_cmd(cmd))
                for i, cmd in enumerate(gobj.r):
                    gobj.r[i] = (cmd[0], self._parse_group_cmd(cmd))
                for i, cmd in enumerate(gobj.d):
                    gobj.d[i] = (cmd[0], self._parse_group_cmd(cmd))

    def _parse_path_cmd(self, cmd: tuple[str, str]) -> tuple[Any, ...]:
        """
        Parsing config commands (path).
        """
        no, op = cmd
        if op.startswith('s:'):
            return 's', float(op.split(':')[1])
        if op.startswith('r:') or op.startswith('d:'):
            op_list = re.fullmatch(r"(\w:\w{3})([><=]{1,2})(.+)", op)
            if op_list[1] not in self._path_op:
                raise SyntaxError(f"Error: config syntax error (ln:{no})")
            type_, tar = op_list[1].split(':')
            return type_, tar, op_list[2], float(op_list[3])
        if op == 'r' or op == 'd':
            return op, True
        raise SyntaxError(f"Error: config syntax error (ln:{no})")

    def _parse_group_cmd(self, cmd: tuple[str, str]) -> tuple[Any, ...]:
        """
        Parsing config commands (path group).
        """
        no, op = cmd
        if op.startswith('w:'):
            op_list = re.fullmatch(r"(\w:\w{3})([><=]{1,2})(.+?)(?::(.+)*)*", op)
            if op_list[1] not in self._group_op:
                raise SyntaxError(f"Error: config syntax error (ln:{no})")
            type_, tar = op_list[1].split(':')
            return type_, tar, op_list[2], float(op_list[3]), op_list[4]
        raise SyntaxError(f"Error: config syntax error (ln:{no})")

    def parse_report(self, rpt_fps: list[str]):
        """
        Parse the timing report.

        Parameters
        ----------
        rpt_fps : list[str]
            A list of the file path of constraint reports. (max number: 2)
        """
        st_idle, st_prefix, st_parsing = range(3)
        grp_re = re.compile(r"(?P<t>[\w\/]+)(?:\s+\('(?P<g>[\w\/]+)'\sgroup\))?")

        for fid, rpt_fp in enumerate(rpt_fps[:2]):
            if os.path.splitext(rpt_fp)[1] == '.gz':
                fp = gzip.open(rpt_fp, mode='rt')
            else:
                fp = open(rpt_fp)

            table = SimpleTable(self._path_hd)
            self.cons_tables.append(table) 

            stage, is_dmsa = st_idle, False
            line, fno = fp.readline(), 1
            while line:
                line = line.strip()
                if not (toks:=line.split()):
                    pass
                elif stage == st_idle and toks[0][0] == '*':
                    stage = st_prefix
                elif stage == st_prefix and toks[0][0] == '*':
                    stage = st_parsing
                elif stage == st_prefix and toks[0] == 'Design':
                    if toks[1] == 'multi_scenario':
                        is_dmsa = True
                elif stage == st_parsing:
                    m = grp_re.fullmatch(line)
                    if m and m['t'] in self._cons_type_set:
                        group = "" if m['g'] is None else m['g']
                        fno = self._parse_group(
                                fp, fid, fno, m['t'], group, is_dmsa)
                line, fno = fp.readline(), fno+1
            fp.close()

        self._create_sum_table()

    def _parse_group(self, fp, fid: int, fno: int, gtype: str, group: str, 
                     is_dmsa: bool) -> int:
        """
        Parsing a violation group.

        Parameters
        ----------
        fp : file
            File point of the report.
        fid : int
            File id of the report.
        fno : int
            Current line number of the report (before parsing).
        gtype : str    
            Constraint type.
        group : str
            Path group name
        is_dmsa : bool 
            If current report is a DMSA report?

        Returns
        -------
        fno : int
            Current line number of the report (after parsing).
        """
        is_start, is_rec = False, False
        table = self.cons_tables[fid]
        content = []
        line, fno = fp.readline(), fno+1
        rid = 'l' if fid == 0 else 'r'

        while line:
            toks = line.strip().split()
            if is_start:
                content.extend(toks)
            if not is_start:
                if toks and toks[0][0] == '-':
                    is_start = True
            elif not toks:
                break
            elif content[-1] == '(VIOLATED)':
                is_rec, cid, is_pulse_chk = True, -2, False
            elif len(content) >= 2 and content[-2] == '(VIOLATED)':
                is_rec, cid, is_pulse_chk = True, -3, True

            if is_rec:
                slk, cid = float(content[cid]), cid-1
                arr, cid = float(content[cid]), cid-1
                req, cid = float(content[cid]), cid-1 
                sc, cid = (content[cid], cid-1) if is_dmsa else ("", cid)
                if is_pulse_chk:
                    pulse_type = ' '.join(content[1:cid+1])[1:-1].split()[-1]
                    attr = f"{content[-1]},{pulse_type}"
                else:
                    attr = ''
                pin = content[0]
                is_rec, content = False, []
                key1 = f"{gtype}:{group}"
                key2 = f"{gtype}:*"

                ## path config check
                off, is_rsv, is_del = 0.0, False, False
                pcons_set = (self.path_cfg.get(key1, []) + 
                             self.path_cfg.get(key2, []))

                # add slack offset first
                for pcons in pcons_set:
                    if pcons.re.fullmatch(pin):
                        for ln, cmd in pcons[rid]:
                            if ln != 0 and cmd[0] == 's':
                                off += cmd[1]
                slk += off

                # check reserve/discard second
                for pcons in pcons_set:
                    if pcons.re.fullmatch(pin):
                        for ln, cmd in pcons[rid]:
                            if ln != 0 and cmd[0] == 'r':
                                if cmd[1] == True:
                                    is_rsv = True
                                else:
                                    is_rsv = self._cmp_op[cmd[2]](slk, cmd[3])
                            elif ln != 0 and cmd[0] == 'd':
                                if cmd[1] == True:
                                    is_del = True
                                else:
                                    is_del = self._cmp_op[cmd[2]](slk, cmd[3])

                ## user group config check
                ugroup, is_og_rsv = None, False
                for pobj in (list(self.ugrp_cfg.get(key1, {}).values()) +
                             list(self.ugrp_cfg.get(key2, {}).values())):
                    if pobj.re.fullmatch(pin):
                        ugroup = pobj.ugroup
                        is_og_rsv = pobj.is_og_rsv
                        break

                table.add_row(None, '', 
                    [gtype, group, pin, sc, arr, req, slk, attr, off, 
                     is_rsv, is_del, ugroup, is_og_rsv])

            line, fno = fp.readline(), fno+1
        return fno

    def _create_sum_table(self):
        """
        Create summary table.
        """
        stable = self.sum_tables
        ustable = {}
        hid = None      # header id

        def update_gtable(rid: int, rcnt: int, gtable: SimpleTable, 
                          rkey: str, pgroup: str, slk: float):
            """
            Parameters
            ----------
            rid : int
                Report ID.
            rcnt : int
                Number of constraint reports.
            gtable : SimpleTable
                Group table.
            rkey : str
                Row hash key.
            pgroup : str
                Path group name
            slk : float
                Path slack
            """
            if rkey not in gtable.index.id:
                gtable.add_row(
                    key=rkey, title='', 
                    data=[pgroup, slk, slk, 1, 0, 0, 0, 0, 0, 0],
                    border=Border(False, False, False, False))
                gtable.attr[-1, COM].border.set(
                        False, False, False, False)
                if rcnt > 1:
                    for ckey in (LW, LT, RW, RT, DW, DT):
                        gtable.attr[-1, ckey].fs = '{: .4f}'
                    for ckey in (LW, RW, DW):
                        gtable.attr[-1, ckey].border.left = True
                    for ckey in (LN, RN, DN):
                        gtable.attr[-1, ckey].fs = '{: d}'
                        gtable.attr[-1, ckey].border.right = True
                else:
                    for ckey in (LW, LT):
                        gtable.attr[-1, ckey].fs = '{: .4f}'
            else:
                if rid == 0:
                    if slk < gtable[rkey, LW]:
                        gtable[rkey, LW] = slk
                    gtable[rkey, LT] += slk
                    gtable[rkey, LN] += 1 
                else:
                    if slk < gtable[rkey, RW]:
                        gtable[rkey, RW] = slk
                    gtable[rkey, RT] += slk
                    gtable[rkey, RN] += 1 

        top_bor = False if (rcnt:=len(self.cons_tables)) == 1 else True
        table_bor = Border(top_bor, False, False, False)
        head_bor = Border(left=False, right=False)

        for rid in range(rcnt):
            ctable = self.cons_tables[rid]
            for r in range(ctable.max_row):
                # create new group table for the new violation type
                if (vtype:=ctable[r,'type']) not in stable:
                    gtable = SimpleTable(heads=self._sum_hd, border=table_bor,
                                         lsh=2, hpat='=', hcpat='=', 
                                         cpat_force_on=True)
                    gtable.set_head_attr(border=head_bor)

                    # gen column id tag
                    if hid is None:
                        hid = gtable.header.id
                        GRP, COM = hid['group'], hid['comm']
                        LW, LT, LN = hid['lwns'], hid['ltns'], hid['lnvp']
                        RW, RT, RN = hid['rwns'], hid['rtns'], hid['rnvp']
                        DW, DT, DN = hid['dwns'], hid['dtns'], hid['dnvp']

                    # adjust table style
                    gtable.header[COM].border.set(
                            False, False, False, False)
                    gtable.set_col_attr(GRP, width=self.gcol_w)

                    if rcnt > 1:
                        for key in (LW, RW, DW):
                            gtable.set_col_attr(key, width=self.wns_w)
                            gtable.header[key].border.left = True
                        for key in (LT, RT, DT):
                            gtable.set_col_attr(key, width=self.tns_w)
                        for key in (LN, RN, DN):
                            gtable.set_col_attr(key, width=self.nvp_w)
                            gtable.header[key].border.right = True
                    else:
                        gtable.set_col_attr(LW, width=self.wns_w)
                        gtable.set_col_attr(LT, width=self.tns_w)
                        gtable.set_col_attr(LN, width=self.nvp_w)

                    stable[vtype] = gtable
                    ustable[vtype] = (ugtable:=copy.deepcopy(gtable))
                else:
                    gtable, ugtable = stable[vtype], ustable[vtype]

                # dicide group name
                if vtype in self._nogrp_cons:
                    pgroup = vtype
                elif vtype in self._clk_cons:
                    pgroup = "({1:4}) {0}".format(*ctable[r,'attr'].split(','))
                else:
                    pgroup = ctable[r,'group']

                # user group check
                is_del = False
                if (upgroup:=ctable[r, 'ugroup']) is not None:
                    if not ctable[r, 'is_og_rsv']:
                        is_del = True
                    update_gtable(rid, rcnt, ugtable, f'{vtype}:{upgroup}', 
                                  f'(user) {upgroup}', ctable[r,'slk'])

                # get data value and update to the table
                # delete check priority: 
                #   is_og_rsv > is_rsv > is_del
                is_del |= ctable[r,'is_del'] and not ctable[r,'is_rsv']
                if not is_del:
                    update_gtable(rid, rcnt, gtable, f'{vtype}:{pgroup}', 
                                  pgroup, ctable[r,'slk'])

        ## group config check
        for vtype, gtable in stable.items():
            # merge user group table
            if vtype in ustable:
                for row in ustable[vtype]._table:
                    gtable.add_row(
                        key=f'{vtype}:{row[0]}', title='',
                        data=row,
                        border=Border(False, False, False, False))

            # update title if single report mode
            if rcnt == 1:
                for key in (LW, LT, LN):
                    title = gtable.header[key].title
                    gtable.header[key].title = title[2:]
            else:
                for row in gtable._table:
                    row[DW] = row[LW] - row[RW]
                    row[DT] = row[LT] - row[RT]
                    row[DN] = row[LN] - row[RN]

            if (gclist:=self.grp_cfg.get(vtype)):
                # condition check
                for row in gtable._table:
                    for gcons in gclist:
                        if gcons.re.fullmatch(row[GRP]):
                            for i, (ln, cmd) in enumerate(gcons.l):
                                cid = hid[f"l{cmd[1]}"]
                                if self._cmp_op[cmd[2]](row[cid], cmd[3]):
                                    tag = f"w{ln}L{i}"
                                    if cmd[4] != None and cmd[4] in self.gtag_cfg:
                                        row[COM] += ", {}: {}".format(tag, self.gtag_cfg[cmd[4]])
                                    else:
                                        row[COM] += ", {}".format(tag)
                                    if cmd[4] != None and cmd[4] in self.gmsg_cfg:
                                        cond = "{}:{}{}".format(*cmd[1:4])
                                        self.comm_set.add("{:10}{:20}{}".format(f"{tag}:", cond, self.gmsg_cfg[cmd[4]]))
                                    else:
                                        self.comm_set.add("{0:10}{1}:{2}{3}".format(f"{tag}:", *cmd[1:]))

                            if rcnt > 1:
                                for i, (ln, cmd) in enumerate(gcons.r):
                                    cid = hid[f"r{cmd[1]}"]
                                    if self._cmp_op[cmd[2]](row[cid], cmd[3]):
                                        row[COM] += ", {}".format(msg:=f"w{ln}R{i}")
                                        self.comm_set.add("{0:10}{1}:{2}{3}".format(f"{msg}:", *cmd[1:]))

                                for i, (ln, cmd) in enumerate(gcons.d):
                                    cid = hid[f"d{cmd[1]}"]
                                    if self._cmp_op[cmd[2]](row[cid], cmd[3]):
                                        row[COM] += ", {}".format(msg:=f"w{ln}D{i}")
                                        self.comm_set.add("{0:10}{1}:{2}{3}".format(f"{msg}:", *cmd[1:]))

                # adjust comment string
                for row in gtable._table:
                    if (msg:=row[COM]) != "":
                        row[COM] = f"({msg[2:]})"


