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
    
    design_db.vtop = (vtop:=Design(top_node=args.vtop_name))
    design_db.design_list = (design_list:=load_area())

    if args.proc_mode == 'adv':
        load_cfg()

    # if len(design_list) > 1 and table_attr.trace_root != 'sub':
    #     table_attr.is_sub_sum = True    # for virtual top display

    # for design in design_list:
    #     virtual_top.total_area += design.total_area
    #     virtual_top.comb_area += design.comb_area
    #     virtual_top.seq_area += design.seq_area
    #     virtual_top.bbox_area += design.bbox_area

    #     if design.max_lv >= virtual_top.max_lv:
    #         virtual_top.max_lv = design.max_lv

    # if table_attr.proc_mode == 'norm' or table_attr.proc_mode == 'adv':
    #     show_hier_area(design_db, table_attr)
    # elif table_attr.proc_mode == 'bbox':
    #     show_bbox_area(design_db, table_attr)


if __name__ == '__main__':
    main()


