#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-only
#
# Design Compiler Area Report Analysis
#
# Copyright (C) 2022 Yeh, Hsin-Hsien <yhh76227@gmail.com>
#
import argparse
import copy
import gzip
import math
import os
import re
import sys
import textwrap
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .utils.common import PKG_VERSION, DC_AREA_VER

VERSION = f"dc_ana_area version {DC_AREA_VER} ({PKG_VERSION})"

### Global Parameter ###  

#{{{
DEFAULT_PATH_COL_SIZE = 32
DEFAULT_AREA_COL_SIZE = 9
TABLE_INIT_ROWS = 128
ISYM = f"{0x251c:c}{0x2500:c}"      # fork symbol
ESYM = f"{0x2514:c}{0x2500:c}"      # end symbol
BSYM = f"{0x2502:c} "               # through symbol

hide_op = {
    '>' : lambda a, b: a > b,
    '<' : lambda a, b: a < b,
    '==': lambda a, b: a == b,
    '>=': lambda a, b: a >= b,
    '<=': lambda a, b: a <= b
}

# at: area total
# pt: percent total
hide_cmp = {
    'at': lambda node, op, val: hide_op[op](node.total_area, val),
    'pt': lambda node, op, val: hide_op[op](node.total_percent, val)
}
#}}}

### Class Defintion ###

@dataclass (slots=True)
class UnitAttr:
#{{{
    type:  int   = 0
    value: float = 1
    tag:   str   = ''
    info:  str   = '1'
#}}}

@dataclass(slots=True)
class TableAttr:
#{{{
    area_fs:       str
    ratio:         float
    unit:          UnitAttr
    dec_place:     int
    is_show_ts:    bool
    is_brief:      bool
    is_logic_sep:  bool
    is_reorder:    bool
    is_show_level: bool
    is_nosplit:    bool
    view_type:     str
    trace_root:    str
    proc_mode:     str
    vtop_name:     str  = 'VIRTUAL_TOP'
    is_verbose:    bool = False
    is_sub_sum:    bool = field(init=False, default=False)
    path_col_size: int  = DEFAULT_PATH_COL_SIZE
    is_cmp_pr:     bool = False
    cmp_type:      int  = 0
    cmp_base:      int  = 0
    design_name:   list = field(default_factory=list)
#}}}

@dataclass (slots=True)
class SumGroup:
#{{{
    name:       str
    total_area: int = 0
    comb_area:  int = 0
    seq_area:   int = 0
    bbox_area:  int = 0
    diff_area:  int = 0
#}}}

class Node:
#{{{
    def __init__(self, dname: str, bname: str, level: int, 
                 total_area: float=0.0, comb_area: float=0.0, seq_area: float=0.0, bbox_area: float=0.0,
                 parent=None, childs=None, scans=None):
        self.dname      = dname
        self.bname      = bname
        self.level      = level
        self.total_area = total_area
        self.comb_area  = comb_area
        self.seq_area   = seq_area
        self.bbox_area  = bbox_area
        self.parent     = parent
        self.childs     = set() if childs is None else childs
        self.scans      = set() if scans is None else sncas

        self.total_percent = -1
        self.is_show       = False
        self.is_hide       = False
        self.is_sub_sum    = False
        self.sub_comb_area = None
        self.sub_seq_area  = None
        self.sub_bbox_area = None
        self.gid           = None
        self.is_sub_root   = False
        self.sr_name       = None
        self.tag_name      = None
        self.inst_name     = None
#}}}

class Design:
#{{{
    def __init__(self, top_node=None):
        self.total_area = 0
        self.comb_area  = 0
        self.seq_area   = 0
        self.bbox_area  = 0
        self.max_lv     = 0
        self.top_node   = top_node
        self.node_dict  = {}
        self.diff_dict  = {}
        self.root_list  = []
        self.level_list = []
#}}}

class DesignDB:
#{{{
    grp_hd = ('name', 'total', 'comb', 'seq', 'bbox', 'attr')
    area_hd = grp_hd + ('did', 'rid', 'level', 'hide', 'sub_sum', 'path_name')

    def __init__(self):
        self.virtual_top = Design(top_node='virtual_top') 
        self.design_list = []
        self.group_list = [pd.DataFrame(columns=self.grp_hd)]
        self.area_table = None
#}}}

### Sub Function ###

def load_area(area_fps, table_attr: TableAttr) -> list:  
    """Load area report"""  #{{{
    design_list = []
    area_ratio = table_attr.ratio
    area_unit = table_attr.unit.value

    if type(area_fps) is not list:
        area_fps = [area_fps]

    for fid, area_fp in enumerate(area_fps, start=0):
        table_attr.design_name.append(f'Design{fid}')
        design_list.append(design:=Design())
        node_dict = design.node_dict
        top_node = None
        fsm = ds_max_lv = 0
        ds_comb_area = ds_seq_area = ds_bbox_area = 0

        with open(area_fp) as f:
            line = f.readline()
            while line:
                if fsm == 2 and len(toks:=line.split()):
                    if toks[0].startswith("---"):
                        design.total_area = top_node.total_area
                        design.comb_area = ds_comb_area
                        design.seq_area = ds_seq_area
                        design.bbox_area = ds_bbox_area
                        design.max_lv = ds_max_lv
                        design.top_node = top_node
                        break

                    path = toks[0]
                    del toks[0]

                    names = path.split('/')
                    dname = '/'.join(names[:-1])  # dirname
                    bname = names[-1]             # basename

                    if len(toks) == 0:  # total area
                        line = f.readline()
                        toks = line.split()
                    total_area = float(toks[0]) * area_ratio / area_unit
                    del toks[0]

                    if len(toks) == 0:  # total percent
                        line = f.readline()
                        toks = line.split()
                    del toks[0]

                    if len(toks) == 0:  # combination area
                        line = f.readline()
                        toks = line.split()
                    comb_area = float(toks[0]) * area_ratio / area_unit
                    del toks[0]

                    if len(toks) == 0:  # sequence area
                        line = f.readline()
                        toks = line.split()
                    seq_area = float(toks[0]) * area_ratio / area_unit
                    del toks[0]

                    if len(toks) == 0:  # bbox area
                        line = f.readline()
                        toks = line.split()
                    bbox_area = float(toks[0]) * area_ratio / area_unit
                    del toks[0]

                    ds_comb_area += comb_area
                    ds_seq_area += seq_area
                    ds_bbox_area += bbox_area

                    if top_node is None:
                        top_node = node = Node(dname, bname, 0, total_area, comb_area, seq_area, bbox_area)
                        top_node.total_percent = 1.0
                    elif len(names) == 1:
                        node = Node(dname, bname, 1, total_area, comb_area, seq_area, bbox_area, parent=top_node)
                        node.total_percent = total_area / top_node.total_area
                        top_node.childs.add(node)
                    else:
                        parent_node = node_dict[dname]
                        node = Node(dname, bname, len(names), total_area, comb_area, seq_area, bbox_area, 
                                    parent=parent_node)
                        node.total_percent = total_area / top_node.total_area
                        parent_node.childs.add(node)

                    node_dict[path] = node

                    if node.level > ds_max_lv:
                        ds_max_lv = node.level

                    if table_attr.proc_mode == 'norm':
                        node.scans = node.childs

                    if table_attr.proc_mode == 'norm' or table_attr.is_verbose:
                        node.is_show = True

                elif fsm == 1:
                    if line.strip().startswith("---"):
                        fsm = 2

                elif fsm == 0:
                    if line.strip().startswith("Hierarchical cell"):
                        fsm = 1

                line = f.readline()

    return design_list
#}}}

def load_cfg(cfg_fp, design_db: DesignDB, table_attr: TableAttr):
    """Load configuration"""  #{{{

    design_list = design_db.design_list
    group_table = design_db.group_list[0]

    regexp_dplen  = re.compile(r'^default_path_length:\s{0,80}(?P<size>\d{1,3})')
    regexp_dsname = re.compile(r'^design_name:\s{0,80}(?P<pat>[^#]+)')
    regexp_grp    = re.compile(r'^grp(?P<id>\d{1,2})?:\s{0,80}(?P<pat>[^#]+)')
    regexp_tag    = re.compile(r'^tag(?P<id>\d)?:\s{0,80}(?P<pat>[^#]+)')
    regexp_inst   = re.compile(r'^inst(?P<id>\d)?:\s{0,80}(?P<pat>[^#]+)')
    regexp_re     = re.compile(r'^re(?P<id>\d)?:\s{0,80}(?P<pat>[^#]+)')
    regexp_node   = re.compile(r'^(?:(?P<id>\d):)?(?P<pat>[^#]+)')

    with open(cfg_fp) as f:
        line_no = 0
        for line in f.readlines():
            line_no += 1
            if len(line:=line.strip()):
                if line[0] == '#':
                    continue

                try:
                    if (m:=regexp_dplen.match(line)):
                        path_len = int(m.group('size'))
                        table_attr.path_col_size = path_len if path_len > 10 else 10
                        continue

                    if (m:=regexp_dsname.match(line)):
                        for pattern in m.group('pat').split():
                            did, name = pattern.split('-')
                            try:
                                table_attr.design_name[int(did)] = name
                            except IndexError:
                                pass
                        continue

                    if (m:=regexp_grp.match(line)):
                        gid = int(m.group('id')) if m.group('id') else 0
                        name = m.group('pat').strip('\"\'\n ')
                        if gid not in group_table.index:
                            group_table.loc[gid] = np.zeros(group_table.shape[1])
                        group_table['name'][gid] = name
                        continue

                    if (m:=regexp_tag.match(line)):
                        path, tag = m.group('pat').split()
                        if (did:=m.group('id')):
                            design_list[int(did)].node_dict[path].tag_name = tag
                        else:
                            for design in design_list:
                                try:
                                    design.node_dict[path].tag_name = tag
                                except:
                                    pass
                        continue

                    if (m:=regexp_inst.match(line)):
                        path, inst = m.group('pat').split()
                        if (did:=m.group('id')):
                            design_list[int(did)].node_dict[path].inst_name = inst
                        else:
                            for design in design_list:
                                try:
                                    design.node_dict[path].inst_name = inst
                                except:
                                    pass
                        continue

                    ## Load node from configuration ##

                    if (m:=regexp_re.match(line)):
                        pattern, *cmd_list = m.group('pat').split()
                        regexp = re.compile(pattern)

                        if (did:=m.group('id')):
                            start_id = int(did)
                            end_id = start_id + 1
                        else:
                            start_id = 0
                            end_id = len(design_list) 

                        for did in range(start_id, end_id):
                            node_dict = design_list[did].node_dict
                            level_list = design_list[did].level_list
                            for path in node_dict.keys():
                                if regexp.match(path):
                                    node = node_dict[path]
                                    node.is_show = True
                                    max_lv = len(level_list) - 1
                                    if max_lv < node.level:
                                        level_list.extend([set() for i in range(node.level - max_lv)])
                                    level_list[node.level].add(node)
                                    parse_cmd(node, cmd_list, design_list[did], group_table, table_attr) 
                        continue

                    if (m:=regexp_node.match(line)):
                        path, *cmd_list = m.group('pat').split()

                        if (did:=m.group('id')):
                            start_id = int(did)
                            end_id = start_id + 1
                        else:
                            start_id = 0
                            end_id = len(design_list) 

                        for did in range(start_id, end_id):
                            node_dict = design_list[did].node_dict
                            level_list = design_list[did].level_list
                            if (node:=node_dict.get(path)):
                                node.is_show = True
                                max_lv = len(level_list) - 1
                                if max_lv < node.level:
                                    level_list.extend([set() for i in range(node.level - max_lv)])
                                level_list[node.level].add(node)
                                parse_cmd(node, cmd_list, design_list[did], group_table, table_attr) 
                        continue

                except Exception as e:
                    print(f"\nLOAD_CONFIG: syntax error (line:{line_no}).\n")
                    raise e

    if group_table.shape[0] > 0:
        table_attr.is_sub_sum = True

    ## backward scan link ##

    for design in design_list:
        level_list = design.level_list
        for level in range(len(level_list)-1, 0, -1):
            for node in level_list[level]:
                if node.parent is not None:
                    node.parent.scans.add(node)
                    level_list[level-1].add(node.parent)
#}}}

def parse_cmd(node: Node, cmd_list: list, design: Design, group_table: pd.DataFrame, 
                table_attr: TableAttr):
    """Parsing command"""  #{{{
    end_cond = len(cmd_list)
    idx = 0

    while idx < end_cond:
        cmd = cmd_list[idx]
        idx += 1

        if cmd == '':
            continue

        if cmd == 'sum':
            sub_area_sum(node)
            table_attr.is_sub_sum = node.is_sub_sum = True

        elif cmd.startswith('hide'):
            toks = cmd.split(':')
            try:
                if len(toks) == 1:
                    node.is_hide = True
                else:
                    pat = toks[1]
                    if pat.startswith('\"'):
                        while not pat.endswith('\"'):
                            pat += f" {cmd_list[idx]}"
                            idx += 1
                    elif pat.startswith('\''):
                        while not pat.endswith('\''):
                            pat += f" {cmd_list[idx]}"
                            idx += 1
                    pat = pat.strip('\"\'\n ')

                    try:
                        ma = re.fullmatch("(\w{2})\s{0,10}([><=]{1,2})\s{0,10}(\w+)", pat)
                        if ma is None or len(ma_grp:=ma.groups()) != 3:
                            raise SyntaxError
                        else:
                            node.is_hide = hide_cmp[ma_grp[0]](node, ma_grp[1], float(ma_grp[2]))
                    except Exception as e:
                        print("\nPARSE_CMD: error command syntax (cmd: hide)\n")
                        raise e
            except Exception as e:
                raise e

        elif cmd.startswith('sr'):
            node.is_sub_root = True
            design.root_list.append(node)
            toks = cmd.split(':')
            if len(toks) > 1:
                node.sr_name = toks[1].strip()

        elif cmd.startswith('add') or cmd.startswith('sub') :
            toks = cmd.split(':')
            gid = 0 if len(toks[0]) == 3 else int(toks[0][3:])
            node.gid = gid if toks[0][0:3] == 'add' else -gid - 1
            if gid not in group_table.index:
                group_table.loc[gid] = np.zeros(group_table.shape[1])
                group_table['name'][gid] = f'Group {gid}'
            if len(toks) > 1:
                name = toks[1]
                if name.startswith('\"'):
                    while not name.endswith('\"'):
                        name += f" {cmd_list[idx]}"
                        idx += 1
                elif name.startswith('\''):
                    while not name.endswith('\''):
                        name += f" {cmd_list[idx]}"
                        idx += 1
                group_table['name'][gid] = name.strip('\"\'\n ')

        elif cmd == 'inf':
            trace_sub_node(node, 'inf', cmd_list[idx:], design, group_table, table_attr)

        elif cmd[0] == 'l':
            trace_sub_node(node, cmd[1:], cmd_list[idx:], design, group_table, table_attr)

        else:
            print("\nPARSE_CMD: error command\n")
            raise SyntaxError
#}}}

def trace_sub_node(cur_node: Node, trace_lv: str, cmd_list: list, design: Design, 
                    group_table: pd.DataFrame, table_attr: TableAttr):
    """Trace sub nodes"""  #{{{
    level_list = design.level_list
    scan_lv = math.inf if trace_lv == 'inf' else cur_node.level + int(trace_lv)
    max_lv = len(level_list) - 1
    scan_stack = []

    if cur_node.level < scan_lv:
        cur_node.scans = cur_node.childs
        scan_stack.extend(cur_node.childs)

    while len(scan_stack):
        node = scan_stack.pop()
        node.is_show = True
        parse_cmd(node, cmd_list, design, group_table, table_attr)

        if max_lv < node.level:
            level_list.extend([set() for i in range(node.level - max_lv)])
            max_lv = node.level

        level_list[node.level].add(node)

        if node.level < scan_lv:
            node.scans = node.childs
            scan_stack.extend(node.childs)
#}}}

def sub_area_sum(cur_node: Node):
    """Trace and Sum sub-node area"""  #{{{
    sub_comb_area = sub_seq_area = sub_bbox_area = 0
    scan_stack = [cur_node]

    while len(scan_stack):
        node = scan_stack.pop()
        sub_comb_area += node.comb_area
        sub_seq_area  += node.seq_area
        sub_bbox_area += node.bbox_area
        scan_stack.extend(node.childs)

    cur_node.sub_comb_area = sub_comb_area
    cur_node.sub_seq_area = sub_seq_area
    cur_node.sub_bbox_area = sub_bbox_area
#}}}

def show_hier_area(design_db: DesignDB, table_attr: TableAttr):
    """Show hierarchical area"""  #{{{

    ## create group table and remove hide node ##

    virtual_top = design_db.virtual_top
    design_list = design_db.design_list
    group_table = design_db.group_list[0]
    path_lv = 0

    for design in design_list:
        for level in range((last_lv := len(design.level_list)-1), -1, -1):
            for node in design.level_list[level]:
                if node.gid is not None:
                    if node.sub_bbox_area is None:
                        sub_area_sum(node)

                    if node.gid >= 0:
                        group_table.loc[node.gid, 'total':'bbox'] += (
                            node.total_area,
                            node.sub_comb_area,
                            node.sub_seq_area,
                            node.sub_bbox_area)
                    else:
                        group_table.loc[abs(node.gid+1), 'total':'bbox'] -= (
                            node.total_area,
                            node.sub_comb_area,
                            node.sub_seq_area,
                            node.sub_bbox_area)

                if node.is_hide or not node.is_show:
                    if len(node.scans) == 0 and node.parent is not None:
                        node.parent.scans.remove(node)
                    else:
                        node.is_show = False

        if last_lv > path_lv:
            path_lv = last_lv

    if table_attr.proc_mode == 'norm':
        path_lv = virtual_top.max_lv

    lv_digi = len(str(path_lv))

    ## create area table ##

    area_hd = design_db.area_hd
    area_table = pd.DataFrame(np.full((TABLE_INIT_ROWS, len(area_hd)), np.NaN), 
                                columns=area_hd, dtype='object')

    area_table_v = area_table.values

    is_multi = (len(design_list) - 1) > 0
    is_virtual_en = is_multi and table_attr.trace_root != 'sub'

    if table_attr.is_show_level:
        path_name = '({}) {}'.format('T'.rjust(lv_digi), virtual_top.top_node)
    else:
        path_name = f'{virtual_top.top_node}'

    if is_virtual_en:
        row_cnt = 1
        area_table.iloc[0] = {
            'name'      : 'virtual_top',
            'total'     : virtual_top.total_area,
            'comb'      : virtual_top.comb_area,
            'seq'       : virtual_top.seq_area,
            'bbox'      : virtual_top.bbox_area,
            'attr'      : '',
            'hide'      : False,
            'sub_sum'   : True,
            'path_name' : path_name
        }

        last_did = -1
        for did, design in enumerate(design_list):
            if design.top_node.is_show or len(design.top_node.scans) > 0:
                last_did = did
    else:
        row_cnt = 0

    row_mask = TABLE_INIT_ROWS - 1

    for did, design in enumerate(design_list):
        if table_attr.trace_root == 'sub':
            root_list = design.root_list
        else:
            root_list = [design.top_node]

        for rid, root_node in enumerate(root_list):
            if not root_node.is_show and len(root_node.scans) == 0:
                continue

            scan_stack = [root_node]
            sym_list = []
            while len(scan_stack):
                node = scan_stack.pop()
                if table_attr.view_type == 'tree':
                    try:
                        if node is root_node:
                            if is_virtual_en:
                                if did == last_did:
                                    sym = f"{ESYM}{did}:"
                                    sym_list.append("  ")
                                else:
                                    sym = f"{ISYM}{did}:"
                                    sym_list.append(BSYM)
                            else:
                                sym = ""
                        elif scan_stack[-1].level < node.level:
                            sym = "".join(sym_list + [ESYM])
                            if len(node.scans):
                                sym_list.append("  ")
                            else:
                                sym_list = sym_list[:scan_stack[-1].level - node.level]
                        else:
                            for idx in range(len(scan_stack)-1, -1, -1):
                                next_node = scan_stack[idx]
                                if next_node.level == node.level and not next_node.is_hide:
                                    sym = "".join(sym_list + [ISYM]) 
                                    break
                                elif next_node.level < node.level:
                                    sym = "".join(sym_list + [ESYM])
                                    break
                            else:
                                sym = "".join(sym_list + [ESYM])

                            if len(node.scans):
                                sym_list.append(BSYM)
                    except Exception:
                        sym = "".join(sym_list + [ESYM])
                        if len(node.scans):
                            sym_list.append("  ")

                    if table_attr.trace_root == 'sub' and node.sr_name is not None:
                        path_name = "".join((sym, node.sr_name))
                    elif node.inst_name is None:
                        path_name = "".join((sym, node.bname))
                    else:
                        path_name = "".join((sym, node.inst_name))
                elif table_attr.view_type == 'inst':
                    if table_attr.trace_root == 'sub' and node.sr_name is not None:
                        path_name = node.sr_name
                    elif node.tag_name is not None:
                        path_name = node.tag_name
                    else:
                        if node.inst_name is not None:
                            path_name = node.inst_name
                        else:
                            path_name = node.bname

                        if is_multi:
                            path_name = f"{did}:{path_name}"
                else:
                    if table_attr.trace_root == 'sub' and node.sr_name is not None:
                        path_name = node.sr_name
                    elif node.tag_name is not None:
                        path_name = node.tag_name
                    else:
                        bname  = node.bname if node.inst_name is None else node.inst_name
                        path_name = bname if node.level < 2 else f"{node.dname}/{bname}"
                        if is_multi:
                            if node.level > 0:
                                path_name = f"{root_node.bname}/{path_name}"
                            path_name = f"{did}:{path_name}"

                if table_attr.is_show_level:
                    if table_attr.trace_root == 'sub':
                        level = node.level - root_node.level
                    else:
                        level = node.level
                    path_name = '({}) {}'.format(str(level).rjust(lv_digi), path_name)

                if (gid := node.gid) is not None:
                    if gid >= 0:
                        attr = " *{}+".format(gid)
                    else:
                        attr = " *{}-".format(abs(gid+1))
                else:
                    attr = ""

                area_table_v[row_cnt] = (
                    ','.join([node.dname, node.bname]),                         # name
                    node.total_area,                                            # total
                    node.sub_comb_area if node.is_sub_sum else node.comb_area,  # comb
                    node.sub_seq_area if node.is_sub_sum else node.seq_area,    # seq
                    node.sub_bbox_area if node.is_sub_sum else node.bbox_area,  # bbox
                    attr,                                                       # attr
                    did,                                                        # did
                    rid if node == root_node else np.NaN,                       # rid
                    node.level,                                                 # level
                    not node.is_show,                                           # hide
                    node.is_sub_sum,                                            # sub_sum
                    path_name                                                   # path_name
                )

                row_cnt += 1
                if (row_cnt & row_mask) == 0:
                    new = pd.DataFrame(np.full((TABLE_INIT_ROWS, len(area_hd)), np.NaN), 
                                        columns=area_hd, dtype='object')
                    area_table = pd.concat([area_table, new], ignore_index=True)
                    area_table_v = area_table.values

                if table_attr.is_reorder:
                    scan_stack.extend(sorted(node.scans, key=lambda x:x.total_area))
                else:
                    scan_stack.extend(sorted(node.scans, key=lambda x:x.bname, reverse=True))

    if row_cnt < area_table.shape[0]:
        area_table = area_table.drop(range(row_cnt, area_table.shape[0]))
    design_db.area_table = area_table

    ## show area report ##

    unit = table_attr.unit
    area_fs = table_attr.area_fs

    area_t = virtual_top.total_area
    area_l = virtual_top.comb_area + virtual_top.seq_area
    area_b = virtual_top.bbox_area

    area_len_t = len(str(math.ceil(area_t))) + 1 + table_attr.dec_place + len(unit.tag)

    if table_attr.is_show_ts:
        area_len_t += int(math.log(area_t) / math.log(1000))

    area_str_t = area_norm(area_t, unit, area_fs).rjust(area_len_t)
    area_str_l = area_norm(area_l, unit, area_fs).rjust(area_len_t)
    area_str_b = area_norm(area_b, unit, area_fs).rjust(area_len_t)

    print()
    print(f" Top Summary ".center(32, '='))
    print("  total: {} ({:>6.1%})".format(area_str_t, 1.0))
    print("  logic: {} ({:>6.1%})".format(area_str_l, area_l / area_t))
    print("   bbox: {} ({:>6.1%})".format(area_str_b, area_b / area_t))
    print("=" * 32)

    if table_attr.is_sub_sum:
        print("\n() : Sub-tree Area Summation")

    print(f"\nratio: {str(table_attr.ratio)}  unit: {unit.info}\n")

    if table_attr.view_type == 'path' and not table_attr.is_nosplit:
        path_len = table_attr.path_col_size
    else:
        path_len = area_table['path_name'].apply(len).max()
        if path_len < table_attr.path_col_size:
            path_len = table_attr.path_col_size

    if group_table.shape[0] > 0:
        name_len = group_table['name'].apply(len)
        grp_len = len(str(name_len.idxmax())) + 2 + name_len.max()
        if grp_len > path_len:
            path_len = grp_len

    max_abs_area = area_table['total'].max()
    area_len = len(str(math.ceil(max_abs_area)))

    if group_table.shape[0] > 0:
        area_g = group_table['total'].max()
        area_ln_g = len(str(math.ceil(area_g)))
        if area_ln_g > area_len:
            max_abs_area = abs(area_g)
            area_len = area_ln_g

        area_g = group_table['total'].min()
        area_ln_g = len(str(math.ceil(area_g)))
        if area_ln_g > area_len:
            max_abs_area = abs(area_g)
            area_len = area_ln_g

    area_len += 1 + table_attr.dec_place
    area_len += len(unit.tag)

    if table_attr.is_show_ts:
        area_len += int(math.log(max_abs_area) / math.log(1000))
    if table_attr.is_sub_sum and not table_attr.is_brief:
        area_len += 2
    if area_len < DEFAULT_AREA_COL_SIZE:
        area_len = DEFAULT_AREA_COL_SIZE 

    header_lens = [path_len, area_len, 7]
    header_list = ['Instance/', 'Absolute/Total', 'Percent/Total']

    if table_attr.is_brief:
        pass
    elif table_attr.is_logic_sep:
        header_lens += [area_len] * 3 + [7]
        header_list += ['Combi-/national', 'Noncombi-/national', 'Black-/Boxes', 'Percent/Boxes']
    else:
        header_lens += [area_len] * 2 + [7]
        header_list += ['Logic/Area', 'Black-/Boxes', 'Percent/Boxes']

    show_divider(header_lens)
    show_header(header_lens, header_list)
    show_divider(header_lens)

    area_table_v = area_table.values

    for idx in range(area_table.shape[0]):
        area_row = dict(zip(area_hd, area_table_v[idx]))

        if table_attr.trace_root == 'sub':
            if area_row['did'] > 0 and area_row['rid'] == 0:
                print()
            elif not math.isnan(area_row['rid']) and area_row['rid'] > 0:
                print()

        if table_attr.trace_root == 'sub':
            if not math.isnan(area_row['rid']):
                root_total = area_row['total']
            percent_t = area_row['total'] / root_total
        else:
            percent_t = area_row['total'] / virtual_top.total_area

        logic_area = area_row['comb'] + area_row['seq']

        if (hier_area := logic_area + area_row['bbox']):
            percent_b = area_row['bbox'] / hier_area
        else:
            percent_b = 0

        is_hide = area_row['hide']

        if is_hide and table_attr.trace_root == 'leaf':
            pass
        else:
            if area_row['sub_sum']:
                bk = ['(', ')']
            else:
                bk = [' ' if table_attr.is_sub_sum else ''] * 2

            if table_attr.trace_root == 'sub' and not math.isnan(area_row['rid']):
                path_name = "<{}>".format(area_row['path_name'])
            else:
                path_name = area_row['path_name']

            if len(path_name) > path_len:
                data_row = [path_name + '\n'.ljust(path_len+1)]
            else:
                data_row = [path_name.ljust(path_len)]

            data_row.append(area_norm(area_row['total'], unit, area_fs, None, is_hide).rjust(area_len))
            data_row.append(area_norm(percent_t, unit, "{2}{0:.1%}{3}", None, is_hide).rjust(7))

            if not table_attr.is_brief: 
                if table_attr.is_logic_sep:
                    data_row.append(area_norm(area_row['comb'], unit, area_fs, bk, is_hide).rjust(area_len))
                    data_row.append(area_norm(area_row['seq'], unit, area_fs, bk, is_hide).rjust(area_len))
                else:
                    data_row.append(area_norm(logic_area, unit, area_fs, bk, is_hide).rjust(area_len))

                data_row.append(area_norm(area_row['bbox'], unit, area_fs, bk, is_hide).rjust(area_len))
                data_row.append(area_norm(percent_b, unit, "{2}{0:.1%}{3}", None, is_hide).rjust(7))

            data_row.append(area_row['attr'])

            for str_ in data_row:
                print(str_, end='  ')
            print()

    if group_table.shape[0] > 0:
        print()
        header_list[0] = 'Summation Group/'
        show_divider(header_lens)
        show_header(header_lens, header_list)
        show_divider(header_lens)

        grp_len = len(str(group_table.index.max()))
        bk = ['(', ')']

        for idx in range(group_table.shape[0]):
            area_row = group_table.iloc[idx, :]

            if table_attr.trace_root == 'sub':
                percent_t = area_row['total'] / root_total
            else:
                percent_t = area_row['total'] / virtual_top.total_area

            logic_area = area_row['comb'] + area_row['seq']

            if (hier_area := logic_area + area_row['bbox']):
                percent_b = area_row['bbox'] / hier_area
            else:
                percent_b = 0

            path_name = "{}: {}".format(str(area_row.name).rjust(grp_len), area_row['name'])

            if len(path_name) > path_len:
                data_row = [path_name + '\n'.ljust(path_len+1)]
            else:
                data_row = [path_name.ljust(path_len)]

            data_row.append(area_norm(area_row['total'], unit, area_fs, None, is_hide).rjust(area_len))
            data_row.append(area_norm(percent_t, unit, "{2}{0:.1%}{3}", None, is_hide).rjust(7))

            if not table_attr.is_brief: 
                if table_attr.is_logic_sep:
                    data_row.append(area_norm(area_row['comb'], unit, area_fs, bk, is_hide).rjust(area_len))
                    data_row.append(area_norm(area_row['seq'], unit, area_fs, bk, is_hide).rjust(area_len))
                else:
                    data_row.append(area_norm(logic_area, unit, area_fs, bk, is_hide).rjust(area_len))

                data_row.append(area_norm(area_row['bbox'], unit, area_fs, bk, is_hide).rjust(area_len))
                data_row.append(area_norm(percent_b, unit, "{2}{0:.1%}{3}", None, is_hide).rjust(7))

            for str_ in data_row:
                print(str_, end='  ')
            print()
    else:
        show_divider(header_lens)

    print()
#}}}

def show_bbox_area(design_db: DesignDB, table_attr: TableAttr):
    """Scan and show all black-box area"""  #{{{

    ## backward trace from nodes with bbox

    virtual_top = design_db.virtual_top
    design_list = design_db.design_list
    path_lv = 0

    is_multi = (last_did := len(design_list) - 1) > 0

    for design in design_list:
        for node in design.node_dict.values():
            if node is design.top_node and not is_multi:
                node.is_show = True
                node.sub_comb_area = design.comb_area
                node.sub_seq_area  = design.seq_area
                node.sub_bbox_area = design.bbox_area
                node.is_sub_sum = True
            elif node.bbox_area != 0:
                node.is_show = True
                if node.level > path_lv:
                    path_lv = node.level

                while True:
                    try:
                        node.parent.scans.add(node)
                        if len(node.parent.scans) > 1:
                            break
                        node = node.parent
                    except Exception:
                        break

    lv_digi = len(str(path_lv))
    table_attr.is_sub_sum = True

    ## create area table ##

    area_hd = design_db.area_hd
    area_table = pd.DataFrame(np.full((TABLE_INIT_ROWS, len(area_hd)), np.NaN), 
                                columns=design_db.area_hd, dtype='object')

    area_table_v = area_table.values

    if table_attr.is_show_level:
        path_name = '({}) {}'.format('T'.rjust(lv_digi), virtual_top.top_node)
    else:
        path_name = f'{virtual_top.top_node}'

    if is_multi:
        row_cnt = 1
        area_table.iloc[0] = {
            'name'      : 'virtual_top',
            'total'     : virtual_top.total_area,
            'comb'      : virtual_top.comb_area,
            'seq'       : virtual_top.seq_area,
            'bbox'      : virtual_top.bbox_area,
            'attr'      : '',
            'hide'      : False,
            'sub_sum'   : True,
            'path_name' : path_name
        }
    else:
        row_cnt = 0

    row_mask = TABLE_INIT_ROWS - 1

    for did, design in enumerate(design_list):
        scan_stack = [root_node := design.top_node]
        sym_list = []
        while len(scan_stack):
            node = scan_stack.pop()
            if table_attr.view_type == 'tree':
                try:
                    if node is root_node:
                        if is_multi:
                            if did == last_did:
                                sym = f"{ESYM}{did}:"
                                sym_list.append("  ")
                            else:
                                sym = f"{ISYM}{did}:"
                                sym_list.append(BSYM)
                        else:
                            sym = ""
                    elif scan_stack[-1].level < node.level:
                        sym = "".join(sym_list + [ESYM])
                        if len(node.scans):
                            sym_list.append("  ")
                        else:
                            sym_list = sym_list[:scan_stack[-1].level - node.level]
                    else:
                        for idx in range(len(scan_stack)-1, -1, -1):
                            next_node = scan_stack[idx]
                            if next_node.level == node.level and not next_node.is_hide:
                                sym = "".join(sym_list + [ISYM]) 
                                break
                            elif next_node.level < node.level:
                                sym = "".join(sym_list + [ESYM])
                                break
                        else:
                            sym = "".join(sym_list + [ESYM])

                        if len(node.scans):
                            sym_list.append(BSYM)
                except Exception:
                    sym = "".join(sym_list + [ESYM])
                    if len(node.scans):
                        sym_list.append("  ")

                path_name = "".join((sym, node.bname))
            elif table_attr.view_type == 'inst':
                path_name = node.bname
                if is_multi:
                    path_name = f"{did}:{path_name}"
            else:
                if node.tag_name is not None:
                    path_name = node.tag_name
                else:
                    path_name = node.bname if node.level < 2 else f"{node.dname}/{node.bname}"
                    if is_multi:
                        if node.level > 0:
                            path_name = f"{root_node.bname}/{path_name}"
                        path_name = f"{did}:{path_name}"

            if table_attr.is_show_level:
                path_name = '({}) {}'.format(str(node.level).rjust(lv_digi), path_name)

            area_table_v[row_cnt] = (
                ','.join([node.dname, node.bname]),                         # name
                node.total_area,                                            # total
                node.sub_comb_area if node.is_sub_sum else node.comb_area,  # comb
                node.sub_seq_area if node.is_sub_sum else node.seq_area,    # seq
                node.sub_bbox_area if node.is_sub_sum else node.bbox_area,  # bbox
                '',                                                         # attr
                did,                                                        # did
                np.NaN,                                                     # rid
                node.level,                                                 # level
                not node.is_show,                                           # hide
                node.is_sub_sum,                                            # sub_sum
                path_name                                                   # path_name
            )                                                                               

            row_cnt += 1
            if (row_cnt & row_mask) == 0:
                new = pd.DataFrame(np.full((TABLE_INIT_ROWS, len(area_hd)), np.NaN), 
                                    columns=area_hd, dtype='object')
                area_table = pd.concat([area_table, new], ignore_index=True)
                area_table_v = area_table.values

            if table_attr.is_reorder:
                scan_stack.extend(sorted(node.scans, key=lambda x:x.total_area))
            else:
                scan_stack.extend(sorted(node.scans, key=lambda x:x.bname, reverse=True))

    if row_cnt < area_table.shape[0]:
        area_table = area_table.drop(range(row_cnt, area_table.shape[0]))
    design_db.area_table = area_table

    ## show area report ##

    unit = table_attr.unit
    area_fs = table_attr.area_fs

    area_t = virtual_top.total_area
    area_l = virtual_top.comb_area + virtual_top.seq_area
    area_b = virtual_top.bbox_area

    area_len_t = len(str(math.ceil(area_t))) + 1 + table_attr.dec_place + len(unit.tag)

    if table_attr.is_show_ts:
        area_len_t += int(math.log(area_t) / math.log(1000))

    area_str_t = area_norm(area_t, unit, area_fs).rjust(area_len_t)
    area_str_l = area_norm(area_l, unit, area_fs).rjust(area_len_t)
    area_str_b = area_norm(area_b, unit, area_fs).rjust(area_len_t)

    print()
    print(f" Top Summary ".center(32, '='))
    print("  total: {} ({:>6.1%})".format(area_str_t, 1.0))
    print("  logic: {} ({:>6.1%})".format(area_str_l, area_l / area_t))
    print("   bbox: {} ({:>6.1%})".format(area_str_b, area_b / area_t))
    print("=" * 32)

    if table_attr.is_sub_sum:
        print("\n() : Sub-tree Area Summation")

    print(f"\nratio: {str(table_attr.ratio)}  unit: {unit.info}\n")

    if table_attr.view_type == 'path' and not table_attr.is_nosplit:
        path_len = table_attr.path_col_size
    else:
        path_len = area_table['path_name'].apply(len).max()
        if path_len < table_attr.path_col_size:
            path_len = table_attr.path_col_size

    max_area = area_table['bbox'].max()
    area_len = len(str(math.ceil(max_area))) + 1 + table_attr.dec_place
    area_len += len(unit.tag)

    if table_attr.is_show_ts:
        area_len += int(math.log(max_area) / math.log(1000))
    if table_attr.is_sub_sum and not table_attr.is_brief:
        area_len += 2
    if area_len < DEFAULT_AREA_COL_SIZE:
        area_len = DEFAULT_AREA_COL_SIZE 

    header_lens = [path_len, area_len, 7]
    header_list = ['Instance/', 'Black-/Boxes', 'Percent/Boxes']

    show_divider(header_lens)
    show_header(header_lens, header_list)
    show_divider(header_lens)

    area_table_v = area_table.values

    for idx in range(area_table.shape[0]):
        area_row = dict(zip(area_hd, area_table_v[idx]))

        if (hier_area := area_row['comb'] + area_row['seq'] + area_row['bbox']):
            percent_b = area_row['bbox'] / hier_area
        else:
            percent_b = 0

        is_hide = area_row['hide']

        if area_row['sub_sum']:
            bk = ['(', ')']
        else:
            bk = [' ' if table_attr.is_sub_sum else ''] * 2

        if len(area_row['path_name']) > path_len:
            data_row = [area_row['path_name'] + '\n'.ljust(path_len+1)]
        else:
            data_row = [area_row['path_name'].ljust(path_len)]

        data_row.append(area_norm(area_row['bbox'], unit, area_fs, bk, is_hide).rjust(area_len))
        data_row.append(area_norm(percent_b, unit, "{1}{0:.1%}{2}", None, is_hide).rjust(7))

        for str_ in data_row:
            print(str_, end='  ')
        print()

    show_divider(header_lens)
    print()
#}}}

def show_cmp_area(design_db: DesignDB, table_attr: TableAttr):
    """Show hierarchical area (compare mode)"""  #{{{

    ## create group tables and remove hide node ##
    
    virtual_top = design_db.virtual_top
    design_list = design_db.design_list
    group_list = design_db.group_list.extend([design_db.group_list[0] for i in range(len(design_list)-1)])
#}}}

def show_divider(header_lens: list):
    """Show divider"""  #{{{
    for length in header_lens:
        print('{}  '.format('-' * length), end='')
    print()
#}}}

def show_header(header_lens: list, header_list: list):
    """Show header"""  #{{{
    for i, head in enumerate(header_list):
        print("{}  ".format(head.split('/')[0].ljust(header_lens[i])), end='')
    print()

    try:
        for i, head in enumerate(header_list):
            print("{}  ".format(head.split('/')[1].ljust(header_lens[i])), end='')
        print()
    except:
        pass
#}}}

def area_norm(value: float, unit: UnitAttr, area_fs: str, bk=None, is_hide=False):
    """Return normalize area string"""  #{{{
    if is_hide:
        return "-" if bk is None else " - "
    else:
        unit_cnt = 1 if unit.type != 0 else 0
        if unit.type == 2:
            while value >= unit.value:
                value /= unit.value
                unit_cnt += 1
        if bk is None:
            return area_fs.format(value, unit.tag * unit_cnt, '', '')
        else:
            return area_fs.format(value, unit.tag * unit_cnt, bk[0], bk[1])
#}}}

### Main Function ###

def create_argparse() -> argparse.ArgumentParser:
    """Create Argument Parser"""  #{{{
    parser = argparse.ArgumentParser(
                formatter_class=argparse.RawTextHelpFormatter,
                description="Design compiler area report analysis.")

    subparsers = parser.add_subparsers(dest='proc_mode', required=True, help="select one of process modes.")

    parser.add_argument('-version', action='version', version=VERSION)
    parser.add_argument('-dump', dest='dump_fn', metavar='<file>', 
                                    help="dump leaf nodes in the list\n ")

    parser.add_argument('-ra', dest='ratio', metavar='<float>', type=float, default=1.0, 
                                    help="convert ratio")

    unit_gparser = parser.add_mutually_exclusive_group()
    unit_gparser.add_argument('-u1', dest='unit1', metavar='unit', 
                                    choices=['k', 'K', 'w', 'W', 'm', 'M', 'b', 'B'],
                                    help="unit change (choices: [kKwWmMbB])") 
    unit_gparser.add_argument('-u2', dest='unit2', metavar='unit', 
                                    choices=['k', 'K', 'w', 'W', 'm', 'M', 'b', 'B'],
                                    help="scientific notation (choices: [kKwWmMbB])\n ") 

    parser.add_argument('-dp', dest='dec_place', metavar='<int>', type=int, default=4, 
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
                                    help="only show instance name (instance view)")

    # create the parser for normal mode
    parser_norm = subparsers.add_parser('norm', help='normal mode')
    parser_norm.add_argument('-vn', dest='vtop_name', metavar='<str>', type=str, default='VIRTUAL_TOP', 
                                    help="virtual top name for multi-design in")
    parser_norm.add_argument('rpt_fn', nargs='+', help="area report path") 

    # create the parser for advance mode
    parser_adv = subparsers.add_parser('adv', help='advance mode')
    parser_adv.add_argument('cfg_fn', help="configuration file") 
    parser_adv.add_argument('rpt_fn', nargs='+', help="area report path") 

    parser_adv.add_argument('-vn', dest='vtop_name', metavar='<str>', type=str, default='VIRTUAL_TOP', 
                                    help="virtual top name for multi-design in")
    parser_adv.add_argument('-sr', dest='is_sub_trace', action='store_true',
                                    help="sub root backward trace")
    parser_adv.add_argument('-v', dest='is_verbose', action='store_true',
                                    help="show area of all trace nodes")

    # create the parser for compare mode
    # parser_cmp = subparsers.add_parser('cmp', help='compare mode')
    # parser_cmp.add_argument('cfg_fn', help="configuration file") 
    # parser_cmp.add_argument('rpt_fn1', nargs=2, help="area report path (essential 2 files)") 
    # parser_cmp.add_argument('rpt_fn2', nargs='*', help="area report path (option files)") 

    # parser_cmp.add_argument('-pr', dest='is_cmp_pr', action='store_true',
    #                                 help="show difference percent")
    # parser_cmp.add_argument('-v', dest='is_verbose', action='store_true',
    #                                 help="show area of all trace nodes")

    # cmp_tparser = parser_cmp.add_mutually_exclusive_group(required=True)

    # cmp_tparser.add_argument('-t1', dest='is_cmp_t1', action='store_true',
    #                                 help="type1: only show areas -------------------- \
    #                                         (A0 A1 A2 ...)")
    # cmp_tparser.add_argument('-t2', dest='is_cmp_t2', action='store_true',
    #                                 help="type2: areas and diff with left design ---- \
    #                                         (A0 D01 A1 D12 A2 ...)")
    # cmp_tparser.add_argument('-t3', dest='cmp_base', metavar='<did>', type=int, 
    #                                 help="type3: areas and diff with select design -- \
    #                                         (A0 DS0 A1 DS1 A2 DS2 ...)")

    # create the parser for black-box scan mode
    parser_bbox = subparsers.add_parser('bbox', help='black-box scan mode')
    parser_bbox.add_argument('-vn', dest='vtop_name', metavar='<str>', type=str, default='VIRTUAL_TOP', 
                                    help="virtual top name for multi-design in")
    parser_bbox.add_argument('rpt_fn', nargs='+', help="area report path") 

    return parser
#}}}

def main():
    """Main Function"""  #{{{

    parser = create_argparse()
    args = parser.parse_args()

    unit = UnitAttr()
    if args.unit1 is not None:
        unit.tag = args.unit1
        unit.type = 1
    elif args.unit2 is not None:
        unit.tag = args.unit2
        unit.type = 2

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
        trace_root = 'sub'
    else:
        trace_root = 'top' if args.is_tree_view else 'leaf'

    if args.is_show_ts:
        area_fs = "{2}{0:,." + str(args.dec_place) + "f}{1}{3}"
    else:
        area_fs = "{2}{0:." + str(args.dec_place) + "f}{1}{3}"

    table_attr = TableAttr(
                    area_fs=area_fs,
                    ratio=args.ratio,
                    unit=unit,
                    dec_place=args.dec_place,
                    is_show_ts=args.is_show_ts,
                    is_brief=args.is_brief,
                    is_logic_sep=args.is_logic_sep,
                    is_reorder=args.is_reorder,
                    is_show_level=args.is_show_level,
                    is_nosplit=args.is_nosplit,
                    view_type=('tree' if args.is_tree_view else 'inst' if args.is_inst_view else 'path'),
                    trace_root=trace_root,
                    proc_mode=args.proc_mode)

    if args.proc_mode != 'cmp':
        table_attr.vtop_name = args.vtop_name

    design_db = DesignDB()

    if args.proc_mode == 'adv':
        table_attr.is_verbose = args.is_verbose
    elif args.proc_mode == 'cmp':
        args.rpt_fn = args.rpt_fn1
        if args.rpt_fn2 is not None:
            args.rpt_fn += args.rpt_fn2 if type(args.rpt_fn2) is list else [args.rpt_fn2]

        table_attr.is_verbose = args.is_verbose
        table_attr.is_cmp_pr = args.is_cmp_pr
        if args.is_cmp_t1:
            table_attr.cmp_type = 1
        elif args.is_cmp_t2:
            table_attr.cmp_type = 2
        else:
            table_attr.cmp_type = 3
            table_attr.cmp_base = args.cmp_base

    if table_attr.cmp_base >= len(args.rpt_fn):
        print("error: base design ID is out of range")
        exit(1)

    ## Main process

    design_db.virtual_top = (virtual_top := Design(top_node=table_attr.vtop_name))
    design_db.design_list = (design_list := load_area(args.rpt_fn, table_attr))

    if table_attr.proc_mode == 'adv' or table_attr.proc_mode == 'cmp':
        load_cfg(args.cfg_fn, design_db, table_attr)

    if table_attr.proc_mode != 'cmp':
        if len(design_list) > 1 and table_attr.trace_root != 'sub':
            table_attr.is_sub_sum = True    # for virtual top display

        for design in design_list:
            virtual_top.total_area += design.total_area
            virtual_top.comb_area += design.comb_area
            virtual_top.seq_area += design.seq_area
            virtual_top.bbox_area += design.bbox_area

            if design.max_lv >= virtual_top.max_lv:
                virtual_top.max_lv = design.max_lv

    if table_attr.proc_mode == 'norm' or table_attr.proc_mode == 'adv':
        show_hier_area(design_db, table_attr)
    elif table_attr.proc_mode == 'bbox':
        show_bbox_area(design_db, table_attr)
    else:
        pass
        # if table_attr.trace_root == 'sub':
        #     if args.proc_mode == 'adv':
        #         show_hier_area(root_list, design, table_attr)
        #     else:
        #         show_cmp_area(root_list, design_list, table_attr)
        # else:
        #     root_node = design.top_node
        #     if table_attr.trace_root == 'com':
        #         while True:
        #             if root_node.is_show:
        #                 break
        #             if len(root_node.scans) > 1:
        #                 break
        #             root_node = tuple(root_node.scans)[0]

        #     if args.proc_mode == 'adv':
        #         show_hier_area([root_node], design, table_attr)
        #     else:
        #         show_cmp_area([root_node], design_list, table_attr)

    if args.dump_fn is not None:
        with open(args.dump_fn, 'w') as f:
            scan_stack = [design.top_node]
            while len(scan_stack):
                node = scan_stack.pop()
                if len(node.scans) == 0:
                    path_name = "" if node.level < 2 else f"{node.dname}/"
                    path_name += node.bname
                    f.write(f"{path_name}\n")
                else:
                    scan_stack.extend(node.scans)
#}}}

if __name__ == '__main__':
    main()
