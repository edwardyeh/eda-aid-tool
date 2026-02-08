#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-only
#
# Design Compiler Area Report Analysis
#
# Copyright (C) 2022 Yeh, Hsin-Hsien <yhh76227@gmail.com>
#
from __future__ import annotations

import argparse
import math
import re
from argparse import Namespace as ArgsNP
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from enum import IntEnum
from re import Pattern as RePat

from .utils.common import PKG_VERSION, DC_AREA_VER

VERSION = f"dc_ana_area version {DC_AREA_VER} ({PKG_VERSION})"


##############################################################################
### Global Variable


INST_COL_SIZE = 32
ISYM = f"{0x251c:c}{0x2500:c}"  # fork symbol
ESYM = f"{0x2514:c}{0x2500:c}"  # end symbol
BSYM = f"{0x2502:c} "           # through symbol

CMD_RE = re.compile(r"(\w+)([><=]{1,2})([\d\.]+)")
CMD_OP = {
    '>' : lambda a, b: a > b,
    '<' : lambda a, b: a < b,
    '==': lambda a, b: a == b,
    '>=': lambda a, b: a >= b,
    '<=': lambda a, b: a <= b
}

class Unit(IntEnum):
    NONE, NORM, SCI = range(3)

class TraceMode(IntEnum):
    TOP, SUB, LEAF = range(3)

class State(IntEnum):
    IDLE, PREF, PROC = range(3)

table_attr, design_db = None, None


##############################################################################
### Class Defintion


@dataclass(slots=True)
class UnitAttr:
    type:  Unit  = Unit.NONE
    tag:   str   = ''
    value: float = 1.0
    info:  str   = '1'


@dataclass (slots=False)
class ConsPathOp:
    re:   RePat           = None
    lv:   int             = 0
    sum:  bool            = False
    sr:   bool            = False
    rn:   str|None        = None
    show: bool|tuple[Any] = False
    hide: bool|tuple[Any] = False
    add:  list[str]       = field(default_factory=list)
    sub:  list[str]       = field(default_factory=list)


@dataclass(slots=True)
class TableAttr:
    args:       ArgsNP
    unit:       UnitAttr
    trace_mode: TraceMode
    area_fs:    str
    icol_w:     int = INST_COL_SIZE


@dataclass (slots=True)
class Node:
    """Record the area information of a instance."""
    name:       list[str]  # format: [dir_name, base_name]
    level:      int        # hierarchical level
    total_area: float
    comb_area:  float
    seq_area:   float
    bbox_area:  float

    is_show:     bool = False
    is_sub_sum:  bool = False
    is_sub_root: bool = False

    parent:        NodeWrap|None = None
    total_percent:    float|None = None
    sub_comb_area:    float|None = None
    sub_seq_area:     float|None = None
    sub_bbox_area:    float|None = None

    group_op: dict[str,int] = field(default_factory=dict)  # format: {gid: [1|-1]}
    childs:   set[NodeWrap] = field(default_factory=set)
    scans:    set[NodeWrap] = field(default_factory=set)


class NodeWrap:
    def __init__(self, node: Node):
        self.node = node

    
@dataclass(slots=True)
class Design:
    """Record the area information of a design report."""
    top_node:   str|None = None
    total_area: float    = 0.0
    comb_area:  float    = 0.0
    seq_area:   float    = 0.0
    bbox_area:  float    = 0.0
    max_lv:     int      = 0
    node_dict:  dict[Node]          = field(default_factory=dict)
    sroot_list: list[Node]          = field(default_factory=list)
    level_list: list[set[NodeWrap]] = field(default_factory=list)


@dataclass(slots=True)
class SumGroup:
    """Summation Group."""
    name:       str
    total_area: float = 0.0
    comb_area:  float = 0.0
    seq_area:   float = 0.0
    bbox_area:  float = 0.0


class DesignDB:
    """Design Database."""
    def __init__(self):
        self.vtop = Design(top_node='virtual_top')
        self.design_list = []
        self.group_dict = {}


##############################################################################
### Sub Function


def gen_path_match(pattern: str, is_regex: bool):
    """Create Path Match Function"""
    if is_regex:
        regexp = re.compile(pattern)
        return lambda x: regexp.fullmatch(x) is not None
    else:
        return lambda x: pattern == x


def load_area() -> list:
    """Load Area from Design Reports."""
    global table_attr

    proc_mode = table_attr.args.proc_mode
    is_verbose = table_attr.args.is_verbose if proc_mode == 'adv' else False
    ratio = table_attr.args.ratio / table_attr.unit.value
    if type(area_fp_list:=table_attr.args.rpt_fn) is not list:
        area_fp_list = [area_fp_list]

    design_list = []
    for area_fp in area_fp_list:
        design_list.append(design:=Design())
        node_dict = design.node_dict
        top_node, ds_max_lv = None, 0
        ds_comb_area = ds_seq_area = ds_bbox_area = 0
        state = State.IDLE

        with open(area_fp) as f:
            line = f.readline()
            while line:
                if state == State.IDLE:
                    if line.strip().startswith("Hierarchical cell"):
                        state = State.PREF
                elif state == State.PREF:
                    if line.strip().startswith("---"):
                        state = State.PROC
                elif state == State.PROC and len(toks:=line.split()):
                    ## report ending check
                    if toks[0].startswith("---"):
                        design.top_node = top_node
                        design.total_area = top_node.total_area
                        design.comb_area = ds_comb_area
                        design.seq_area = ds_seq_area
                        design.bbox_area = ds_bbox_area
                        design.max_lv = ds_max_lv
                        break

                    path = toks[0]
                    names = path.split('/')
                    dname = '/'.join(names[:-1])  # dirname
                    bname = names[-1]             # basename
                    del toks[0]

                    if len(toks) == 0:  # total area
                        line = f.readline()
                        toks = line.split()
                    total_area = float(toks[0]) * ratio
                    del toks[0]

                    if len(toks) == 0:  # total percent
                        line = f.readline()
                        toks = line.split()
                    del toks[0]

                    if len(toks) == 0:  # combination area
                        line = f.readline()
                        toks = line.split()
                    comb_area = float(toks[0]) * ratio
                    del toks[0]

                    if len(toks) == 0:  # sequence area
                        line = f.readline()
                        toks = line.split()
                    seq_area = float(toks[0]) * ratio
                    del toks[0]

                    if len(toks) == 0:  # bbox area
                        line = f.readline()
                        toks = line.split()
                    bbox_area = float(toks[0]) * ratio
                    del toks[0]

                    ds_comb_area += comb_area
                    ds_seq_area += seq_area
                    ds_bbox_area += bbox_area

                    if top_node is None:
                        top_node = node = Node([dname, bname], 0, total_area,
                                               comb_area, seq_area, bbox_area)
                        top_node.total_percent = 1.0
                    elif len(names) == 1:
                        node = Node([dname, bname], 1, total_area, comb_area,
                                    seq_area, bbox_area, parent=NodeWrap(top_node))
                        node.total_percent = total_area / top_node.total_area
                        top_node.childs.add(NodeWrap(node))
                    else:
                        parent_node = node_dict[dname]
                        node = Node([dname, bname], len(names), total_area,
                                    comb_area, seq_area, bbox_area,
                                    parent=NodeWrap(parent_node))
                        node.total_percent = total_area / top_node.total_area
                        parent_node.childs.add(NodeWrap(node))

                    node_dict[path] = node

                    if node.level > ds_max_lv:
                        ds_max_lv = node.level
                    if proc_mode == 'norm':
                        node.scans = node.childs
                    if proc_mode == 'norm' or is_verbose:
                        node.is_show = True

                line = f.readline()
    return design_list


def load_cfg():
    """Load configuration"""
    global table_attr, design_db

    with open(table_attr.args.cfg_fn) as fp:
        for fno, line in enumerate(fp, start=1):
            line = line.split('#')[0].strip()
            if line:
                try:
                    key, *val = line.split() 
                    toks = key.split(':')
                    if toks[0] == 'inst_column_width':
                        ## set instance column width
                        size = int(val[0])
                        table_attr.icol_w = size if size > 10 else 10
                    elif toks[0] == 'g':
                        ## create summation group
                        gid, gname = line[2:].split(':')
                        design_db.group_dict[gid] = SumGroup(name=gname)
                    elif toks[0] in {'p', 'r'}:
                        ## parsing instance operation
                        is_regex = toks[0] == 'r'

                        if toks[1]:
                            edid = (sdid:=int(toks[1])) + 1
                        else:
                            sdid, edid = 0, len(design_db.design_list)

                        pmatch = gen_path_match(toks[2], is_regex)

                        if len(toks) == 4:
                            scan_lv = math.inf if toks[3] == 'inf' else int(toks[3])
                        else:
                            scan_lv = 0

                        for did in range(sdid, edid):
                            node_dict = design_db.design_list[did].node_dict
                            level_list = design_db.design_list[did].level_list
                            for path in node_dict.keys():
                                if pmatch(path):
                                    node = node_dict[path]
                                    max_scan_lv = node.level + scan_lv
                                    parse_cfg_cmd(node, val, max_scan_lv, level_list)
                                    if not is_regex:
                                        break
                except Exception as e:
                    print(f"\nLOAD_CONFIG: syntax error (line:{fno}).\n")
                    raise e

    ## backward scan link
    for level_list in [x.level_list for x in design_db.design_list]:
        for level in range(len(level_list)-1, 0, -1):
            for node in [x.node for x in level_list[level]]:
                if node.parent is not None:
                    node.parent.node.scans.add(NodeWrap(node))
                    level_list[level-1].add(node.parent)


def parse_cfg_cmd(node: Node, cmd_list: list[str], scan_lv: float, lv_list: list):
    """Parsing configure for a node."""
    global table_attr

    for cmd in cmd_list:
        if cmd == 'sum':
            node.is_sub_sum = True
        elif cmd == 'sr':
            node.is_sub_root = True
        elif cmd[:3] == 'rn:':
            node.name = ['', cmd[3:]]
            # if (table_attr.args.is_tree_view or table_attr.args.is_inst_view):
            #     node.name[1] = cmd[3:]
            # else:
            #     node.name = ['', cmd[3:]]
        elif cmd[:4] == 'add:':
            node.group_op[cmd[4:]] = 1
        elif cmd[:4] == 'sub:':
            node.group_op[cmd[4:]] = -1
        elif cmd[:4] == 'show':
            if (op:=cmd.split(':')[1:2]):
                op = CMD_RE.fullmatch(op[0])
                if op[1] == 'att':
                    is_show = CMD_OP[op[2]](node.total_area, float(op[3]))
                elif op[1] == 'ptt':
                    is_show = CMD_OP[op[2]](node.total_percent, float(op[3]))
                else:
                    print(f"LOAD_CONFIG: {op[1]} is not support.")
                    raise SyntaxError
                if is_show:
                    node.is_show = True
            else:
                node.is_show = True
        elif cmd[:4] == 'hide':
            if (op:=cmd.split(':')[1:2]):
                op = CMD_RE.fullmatch(op[0])
                if op[1] == 'att':
                    is_hide = CMD_OP[op[2]](node.total_area, float(op[3]))
                elif op[1] == 'ptt':
                    is_hide = CMD_OP[op[2]](node.total_percent, float(op[3]))
                else:
                    print(f"LOAD_CONFIG: {op[1]} is not support.")
                    raise SyntaxError
                if is_hide:
                    node.is_show = False
            else:
                node.is_show = False

    if (max_lv:=len(lv_list)-1) < node.level:
        for i in range(node.level-max_lv):
            lv_list.append(set())
    lv_list[node.level].add(NodeWrap(node))

    if node.level < scan_lv:
        for wrap in node.childs:
            parse_cfg_cmd(wrap.node, cmd_list, scan_lv, lv_list) 


def show_hier_area():
    """Show hierarchical area."""
    global table_attr, design_db

    ## create group table and remove hide node ##
    virtual_top = design_db.virtual_top
    vtotal = virtual_top.total_area
    dslist = design_db.design_list
    gtable = design_db.group_table
    is_sub_sum = table_attr.is_sub_sum
    area_fs = table_attr.area_fs
    perc_fs = "{:6.1%}"
    path_lv = 0

    # for design in dslist:
    #     for level in range((last_lv := len(design.level_list)-1), -1, -1):
    #         for node in design.level_list[level]:
    #             if node.gid_dict:
    #                 if node.sub_bbox_area is None:
    #                     sub_area_sum(node)
    #                 for gid, sign in node.gid_dict.items():
    #                     gtable[f'{gid}','total':'bbox'] += Array(
    #                         [sign * node.total_area,
    #                          sign * node.sub_comb_area,
    #                          sign * node.sub_seq_area,
    #                          sign * node.sub_bbox_area])
    #             if node.is_hide or not node.is_show:
    #                 if len(node.scans) == 0 and node.parent is not None:
    #                     node.parent.scans.remove(node)
    #                 else:
    #                     node.is_show = False
    #     if last_lv > path_lv:
    #         path_lv = last_lv

    # if table_attr.proc_mode == 'norm':
    #     path_lv = virtual_top.max_lv

    # lv_digi = len(str(path_lv))

    # ## create area table ##

    # design_db.area_table = (atable:=SimpleTable(design_db.ahead))

    # is_multi = len(dslist) > 1
    # is_virtual_en = is_multi and table_attr.trace_root != 'sub'

    # if table_attr.is_show_level:
    #     path_name = '({}) {}'.format('T'.rjust(lv_digi), virtual_top.top_node)
    # else:
    #     path_name = f'{virtual_top.top_node}'

    # if is_virtual_en:
    #     atable.add_row(None, '', [
    #         'virtual_top',          # item
    #         virtual_top.total_area, # total
    #         virtual_top.comb_area,  # comb
    #         virtual_top.seq_area,   # seq
    #         virtual_top.bbox_area,  # bbox
    #         0.0,                    # logic
    #         0.0,                    # ptotal
    #         0.0,                    # pbox
    #         True,                   # sub_sum
    #         False,                  # hide
    #         None,                   # did
    #         None,                   # rid
    #         None,                   # level
    #         '',                     # attr
    #         path_name               # name
    #     ])

    #     last_did = -1
    #     for did, design in enumerate(dslist):
    #         if design.top_node.is_show or len(design.top_node.scans) > 0:
    #             last_did = did

    # for did, design in enumerate(dslist):
    #     if table_attr.trace_root == 'sub':
    #         root_list = design.root_list
    #     else:
    #         root_list = [design.top_node]

    #     for rid, root_node in enumerate(root_list):
    #         if not root_node.is_show and len(root_node.scans) == 0:
    #             continue

    #         scan_stack = [root_node]
    #         sym_list = []
    #         while len(scan_stack):
    #             node = scan_stack.pop()
    #             if table_attr.view_type == 'tree':
    #                 try:
    #                     if node is root_node:
    #                         if is_virtual_en:
    #                             if did == last_did:
    #                                 sym = f"{ESYM}{did}:"
    #                                 sym_list.append("  ")
    #                             else:
    #                                 sym = f"{ISYM}{did}:"
    #                                 sym_list.append(BSYM)
    #                         else:
    #                             sym = ""
    #                     elif scan_stack[-1].level < node.level:
    #                         sym = "".join(sym_list+[ESYM])
    #                         if len(node.scans):
    #                             sym_list.append("  ")
    #                         else:
    #                             sym_lv = scan_stack[-1].level - node.level
    #                             sym_list = sym_list[:sym_lv]
    #                     else:
    #                         for idx in range(len(scan_stack)-1, -1, -1):
    #                             next_node = scan_stack[idx]
    #                             if (next_node.level == node.level
    #                                     and not next_node.is_hide):
    #                                 sym = "".join(sym_list+[ISYM])
    #                                 break
    #                             elif next_node.level < node.level:
    #                                 sym = "".join(sym_list+[ESYM])
    #                                 break
    #                         else:
    #                             sym = "".join(sym_list+[ESYM])

    #                         if len(node.scans):
    #                             sym_list.append(BSYM)
    #                 except Exception:
    #                     sym = "".join(sym_list+[ESYM])
    #                     if len(node.scans):
    #                         sym_list.append("  ")

    #                 if (table_attr.trace_root == 'sub'
    #                         and node.sr_name is not None):
    #                     path_name = "".join((sym, node.sr_name))
    #                 elif node.inst_name is None:
    #                     path_name = "".join((sym, node.bname))
    #                 else:
    #                     path_name = "".join((sym, node.inst_name))
    #             elif table_attr.view_type == 'inst':
    #                 if (table_attr.trace_root == 'sub'
    #                         and node.sr_name is not None):
    #                     path_name = node.sr_name
    #                 elif node.tag_name is not None:
    #                     path_name = node.tag_name
    #                 else:
    #                     if node.inst_name is not None:
    #                         path_name = node.inst_name
    #                     else:
    #                         path_name = node.bname

    #                     if is_multi:
    #                         path_name = f"{did}:{path_name}"
    #             else:
    #                 if (table_attr.trace_root == 'sub'
    #                         and node.sr_name is not None):
    #                     path_name = node.sr_name
    #                 elif node.tag_name is not None:
    #                     path_name = node.tag_name
    #                 else:
    #                     bname = (node.bname if node.inst_name is None
    #                                 else node.inst_name)
    #                     path_name = (bname if node.level < 2
    #                                     else f"{node.dname}/{bname}")
    #                     if is_multi:
    #                         if node.level > 0:
    #                             path_name = f"{root_node.bname}/{path_name}"
    #                         path_name = f"{did}:{path_name}"

    #             if table_attr.is_show_level:
    #                 if table_attr.trace_root == 'sub':
    #                     level = node.level - root_node.level
    #                 else:
    #                     level = node.level
    #                 path_name = '({}) {}'.format(str(level).rjust(lv_digi),
    #                                              path_name)

    #             if node.gid_dict:
    #                 attr = "*"
    #                 for gid, sign in node.gid_dict.items():
    #                     sign = '+' if sign > 0 else '-'
    #                     attr += f"{gid}{sign}"
    #             else:
    #                 attr = ""

    #             if node.is_sub_sum:
    #                 comb_area = node.sub_comb_area
    #                 seq_area = node.sub_seq_area
    #                 bbox_area = node.sub_bbox_area
    #             else:
    #                 comb_area = node.comb_area
    #                 seq_area = node.seq_area
    #                 bbox_area = node.bbox_area

    #             atable.add_row(None, '', [
    #                 ','.join([node.dname, node.bname]),     # item
    #                 node.total_area,                        # total
    #                 comb_area,                              # comb
    #                 seq_area,                               # seq
    #                 bbox_area,                              # bbox
    #                 0.0,                                    # logic
    #                 0.0,                                    # ptotal
    #                 0.0,                                    # pbox
    #                 node.is_sub_sum,                        # sub_sum
    #                 not node.is_show,                       # hide
    #                 did,                                    # did
    #                 rid if node == root_node else None,     # rid
    #                 node.level,                             # level
    #                 attr,                                   # attr
    #                 path_name                               # name
    #             ])

    #             if table_attr.is_reorder:
    #                 scan_stack.extend(
    #                     sorted(node.scans, key=lambda x:x.total_area))
    #             else:
    #                 scan_stack.extend(
    #                     sorted(node.scans, key=lambda x:x.bname, reverse=True))

    # root_total = 0.0
    # for r in range(atable.max_row-1,-1,-1):
    #     atable.attr[r,'total':'pbox'].align = [Align.TR] * 7
    #     if atable[r,'hide']:
    #         if table_attr.trace_root == 'leaf':
    #             atable.del_row(r)
    #         else:
    #             value = " - " if atable[r,'sub_sum'] else "-"
    #             atable[r,'ptotal':'pbox'] = [value] * 2
    #             atable.attr[r,'ptotal':'pbox'].fs = ["{}"] * 2
    #     else:
    #         atable[r,'logic'] = atable[r,'comb'] + atable[r,'seq']
    #         atable.attr[r,'ptotal':'pbox'].fs = [perc_fs] * 2

    #         if table_attr.trace_root == 'sub':
    #             if atable[r,'rid'] is not None:
    #                 atable[r,'name'] = f"<{atable[r,'name']}>"
    #                 root_total = atable[r,'total']
    #             atable[r,'ptotal'] = atable[r,'total'] / root_total
    #         else:
    #             atable[r,'ptotal'] = atable[r,'total'] / vtotal

    #         if (hier_area:=atable[r,'logic']+atable[r,'bbox']) > 0:
    #             atable[r,'pbox'] = atable[r,'bbox'] / hier_area
    #         else:
    #             atable[r,'pbox'] = 0

    # col_area_norm(atable, 'total', table_attr, is_hide_chk=True)
    # for key in ('comb', 'seq', 'bbox', 'logic'):
    #     col_area_norm(atable, key, table_attr, is_sub_sum=is_sub_sum,
    #                   is_hide_chk=True)
    # ## show area report ##

    # unit = table_attr.unit

    # area_t = virtual_top.total_area
    # area_l = virtual_top.comb_area + virtual_top.seq_area
    # area_b = virtual_top.bbox_area

    # area_t2, fs = area_norm(area_t, table_attr)
    # area_l2, *_ = area_norm(area_l, table_attr)
    # area_b2, *_ = area_norm(area_b, table_attr)

    # area_str_t = fs.format(area_t2)
    # area_str_l = fs.format(area_l2).rjust(str_len:=len(area_str_t))
    # area_str_b = fs.format(area_b2).rjust(str_len)

    # print()
    # print(f" Top Summary ".center(32, '='))
    # print("  total: {} ({:>6.1%})".format(area_str_t, 1.0))
    # print("  logic: {} ({:>6.1%})".format(area_str_l, area_l / area_t))
    # print("   bbox: {} ({:>6.1%})".format(area_str_b, area_b / area_t))
    # print("=" * 32)

    # if table_attr.is_sub_sum:
    #     print("\n() : Sub-tree Area Summation")

    # print(f"\nratio: {str(table_attr.ratio)}  unit: {unit.info}\n")

    # ### update group table ###

    # if gtable.max_row > 0:
    #     for r in range(gtable.max_row):
    #         gtable[r,'sub_sum'] = True
    #         gtable[r,'logic'] = gtable[r,'comb'] + gtable[r,'seq']

    #         if table_attr.trace_root == 'sub' and sub_root_cnt > 1:
    #             gtable[r,'ptotal'] = 'NA'
    #             gtable.attr[r,'ptotal'].fs = '{}'
    #         elif table_attr.trace_root == 'sub' and sub_root_cnt == 1:
    #             gtable[r,'ptotal'] = gtable[r,'total'] / root_total
    #         else:
    #             gtable[r,'ptotal'] = gtable[r,'total'] / vtotal

    #         if (hier_area:=gtable[r,'logic']+gtable[r,'bbox']) > 0:
    #             gtable[r,'pbox'] = gtable[r,'bbox'] / hier_area
    #         else:
    #             gtable[r,'pbox'] = 0

    #     col_area_norm(gtable, 'total', table_attr)
    #     gtable.set_col_attr('total', align=Align.TR)
    #     for key in ('comb', 'seq', 'bbox', 'logic'):
    #         col_area_norm(gtable, key, table_attr, is_sub_sum=is_sub_sum)
    #         gtable.set_col_attr(key, align=Align.TR)
    #     for key in ('ptotal', 'pbox'):
    #         gtable.set_col_attr(key, fs=perc_fs, align=Align.TR)

    #     size = max([len(x) for x in gtable.index.id.keys()])
    #     for key in gtable.index.id.keys():
    #         gtable[key,'name'] = \
    #             "{}: {}".format(key.rjust(size), gtable[key,'name'])

    # ### sync column width ###

    # if table_attr.view_type == 'path' and not table_attr.is_nosplit:
    #     plen = table_attr.path_col_size
    #     atable.set_col_attr('name', width=plen, is_sep=True)
    # else:
    #     plen = atable.get_col_width('name')
    #     if plen < table_attr.path_col_size:
    #         plen = table_attr.path_col_size
    #         atable.set_col_attr('name', width=plen)

    # if gtable.max_row > 0:
    #     glen = gtable.get_col_width('name')
    #     if glen > plen:
    #         plen = glen
    #         atable.set_col_attr('name', width=plen)
    #     else:
    #         gtable.set_col_attr('name', width=plen)

    # for key in ('total', 'comb', 'seq', 'bbox', 'logic'):
    #     plen = atable.get_col_width(key)
    #     if plen < DEFAULT_AREA_COL_SIZE:
    #         atable.set_col_attr(key, width=(plen:=DEFAULT_AREA_COL_SIZE))
    #     if gtable.max_row > 0:
    #         glen = gtable.get_col_width(key)
    #         if glen > plen:
    #             plen = glen
    #             atable.set_col_attr(key, width=plen)
    #         else:
    #             gtable.set_col_attr(key, width=plen)

    # ### print table ###

    # hlist = ['name', 'total', 'ptotal']
    # if not table_attr.is_brief:
    #     hlist += ['comb', 'seq'] if table_attr.is_logic_sep else ['logic']
    #     hlist += ['bbox', 'pbox']
    # hlist += ['attr']

    # atable.set_head_attr(border=Border(left=False,right=False))
    # for r in range(ed:=atable.max_row-1):
    #     atable.set_row_attr(r, border=Border(left=False,right=False))
    # if gtable.max_row > 0:
    #     atable.set_row_attr(ed, border=Border(left=False,right=False,
    #                                           bottom=False))
    # else:
    #     atable.set_row_attr(ed, border=Border(left=False,right=False))

    # atable.header['attr'].border = Border(top=False,bottom=False,
    #                                       left=False, right=False)
    # for r in (0, atable.max_row-1):
    #     atable.attr[r,'attr'].border = Border(top=False,bottom=False,
    #                                           left=False,right=False)
    # atable.header['attr'].title = ""
    # atable.print(column=hlist)

    # if gtable.max_row > 0:
    #     gtable.set_head_attr(border=Border(left=False,right=False))
    #     for r in range(ed:=gtable.max_row-1):
    #         gtable.set_row_attr(r, border=Border(left=False,right=False))
    #     gtable.set_row_attr(ed, border=Border(left=False,right=False,
    #                                           bottom=False))
    #     gtable.print(column=hlist[:-1])
    # else:
    #     print()




##############################################################################
### Main Process


def create_argparse() -> argparse.ArgumentParser:
    """Create Argument Parser"""
    parser = argparse.ArgumentParser(
                formatter_class=argparse.RawTextHelpFormatter,
                description="Design compiler area report analysis.")

    subparsers = parser.add_subparsers(dest='proc_mode',
                                       required=True,
                                       help="select one of process modes.")

    parser.add_argument('-version', action='version', version=VERSION, 
                                    help='show program\'s version number and exit\n\n')

    parser.add_argument('-ra', dest='ratio', metavar='<float>', type=float,
                               default=1.0, help="scale ratio")

    unit_gparser = parser.add_mutually_exclusive_group()
    unit_gparser.add_argument('-u1', dest='norm_unit', metavar='unit',
                                     choices=['k','K','w','W','m','M','b','B'],
                                     help="unit change (choices: [kKwWmMbB])")
    unit_gparser.add_argument('-u2', dest='sci_unit', metavar='unit',
                                     choices=['k','K','w','W','m','M','b','B'],
                                     help="scientific notation " + 
                                          "(choices: [kKwWmMbB])\n ")

    parser.add_argument('-dp', dest='dec_place', metavar='<int>', type=int,
                               default=4, 
                               help="number of decimal places of area")
    parser.add_argument('-ts', dest='is_show_ts', action='store_true',
                               help="show thousands separators")

    area_gparser = parser.add_mutually_exclusive_group()
    area_gparser.add_argument('-br', dest='is_brief', action='store_true',
                                     help="only show total area/percent value")
    area_gparser.add_argument('-ls', dest='is_logic_sep', action='store_true',
                                     help="show combi/non-combi area separately")

    parser.add_argument('-ro', dest='is_reorder', action='store_true',
                               help="area reorder (large first)")
    parser.add_argument('-lv', dest='is_show_level', action='store_true',
                               help="show hierarchical level")
    parser.add_argument('-ns', dest='is_nosplit', action='store_true',
                               help="cell path no-split\n ")

    path_gparser = parser.add_mutually_exclusive_group()
    path_gparser.add_argument('-t', dest='is_tree_view', action='store_true',
                                    help="show path with tree view")
    path_gparser.add_argument('-i', dest='is_inst_view', action='store_true',
                                    help="only show instance name " + 
                                         "(instance view)")

    ## create the parser for normal mode
    parser_norm = subparsers.add_parser('norm', help='normal mode', 
                    formatter_class=argparse.RawTextHelpFormatter)
    parser_norm.add_argument('rpt_fn', nargs='+', help="area report path")
    parser_norm.add_argument('-vn', dest='vtop_name', metavar='<str>',
                                    type=str, default='VIRTUAL_TOP',
                                    help="virtual top name for multi-design in")

    ## create the parser for advance mode
    parser_adv = subparsers.add_parser('adv', help='advance mode', 
                    formatter_class=argparse.RawTextHelpFormatter)
    parser_adv.add_argument('cfg_fn', help="configuration file")
    parser_adv.add_argument('rpt_fn', nargs='+', help="area report path")
    parser_adv.add_argument('-vn', dest='vtop_name', metavar='<str>',
                                   type=str, default='VIRTUAL_TOP',
                                   help="virtual top name for multi-design in")
    parser_adv.add_argument('-sr', dest='is_sub_trace', action='store_true',
                                   help="sub root backward trace")
    parser_adv.add_argument('-v', dest='is_verbose', action='store_true',
                                  help="show area of all trace nodes")

    ## create the parser for black-box scan mode
    parser_bbox = subparsers.add_parser('bbox', help='black-box scan mode', 
                    formatter_class=argparse.RawTextHelpFormatter)
    parser_bbox.add_argument('rpt_fn', nargs='+', help="area report path")
    parser_bbox.add_argument('-vn', dest='vtop_name', metavar='<str>',
                                    type=str, default='VIRTUAL_TOP',
                                    help="virtual top name for multi-design in")

    return parser


def main():
    """Main Function"""
    parser = create_argparse()
    args = parser.parse_args()

    unit = UnitAttr()
    if args.norm_unit is not None:
        unit.type = Unit.NORM
        unit.tag = args.norm_unit
    elif args.sci_unit is not None:
        unit.type = Unit.SCI
        unit.tag = args.sci_unit

    match unit.tag.lower():
        case 'k':
            unit.value = pow(10, 3)
            unit.info = "1 thousand"
        case 'w':
            unit.value = pow(10, 4)
            unit.info = "10 thousand"
        case 'm':
            unit.value = pow(10, 6)
            unit.info = "1 million"
        case 'b':
            unit.value = pow(10, 9)
            unit.info = "1 billion"

    if args.proc_mode == 'adv' and args.is_sub_trace:
        trace_mode = TraceMode.SUB
    elif args.is_tree_view:
        trace_mode = TraceMode.TOP
    else:
        trace_mode = TraceMode.LEAF

    ts = ',' if args.is_show_ts else ''
    area_fs = f"{{:{ts}.{args.dec_place}f}}"

    global table_attr, design_db
    table_attr = TableAttr(args, unit, trace_mode, area_fs)
    design_db = DesignDB()

    ### Main process ###
    
    design_db.vtop = (virtual_top:=Design(top_node=args.vtop_name))
    design_db.design_list = (design_list:=load_area())

    if args.proc_mode == 'adv':
        load_cfg()

    # if len(design_list) > 1 and table_attr.trace_root != 'sub':
    #     table_attr.is_sub_sum = True    # for virtual top display

    for design in design_list:
        virtual_top.total_area += design.total_area
        virtual_top.comb_area += design.comb_area
        virtual_top.seq_area += design.seq_area
        virtual_top.bbox_area += design.bbox_area
        if design.max_lv >= virtual_top.max_lv:
            virtual_top.max_lv = design.max_lv

    if args.proc_mode == 'norm' or args.proc_mode == 'adv':
        show_hier_area()
    # elif table_attr.proc_mode == 'bbox':
    #     show_bbox_area(design_db, table_attr)


if __name__ == '__main__':
    main()


