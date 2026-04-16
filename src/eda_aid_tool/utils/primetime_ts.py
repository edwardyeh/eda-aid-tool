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
import math
import os
import re
import sys
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from enum import IntEnum


@dataclass
class Pin:
    """Data pin container."""
    ln:     int     = None              # line number
    name:   str     = None              # pin name
    cell:   str     = None              # cell type
    dir:    str     = None              # pin direction
    type:   str     = None              # pin type
    phy:    str     = None              # physical coordination
    drv:    Decimal = Decimal('-1.0')   # cell driving
    fo:     int     = None              # fanout
    cap:    Decimal = Decimal('0.0')    # capacitance
    dtran:  Decimal = Decimal('0.0')    # delta transition
    tran:   Decimal = Decimal('0.0')    # transition
    derate: Decimal = Decimal('0.0')    # derate
    delta:  Decimal = Decimal('0.0')    # delta
    incr:   Decimal = Decimal('0.0')    # latency increment
    arr:    Decimal = Decimal('0.0')    # arrival time


@dataclass
class Path:
    """Basic path container."""
    ln:    int     = None            # startpoint line number
    stp:   str     = None            # startpoint
    sck:   str     = None            # startpoint clock
    sed:   str     = None            # startpoint clock edge type
    edp:   str     = None            # endpoint
    eck:   str     = None            # endpoint clock
    eed:   str     = None            # endpoint clock edge type
    group: str     = None            # path group
    type:  str     = None            # delay type
    scen:  str     = None            # Scenario
    arr:   Decimal = Decimal('0.0')  # data arrival time
    req:   Decimal = Decimal('0.0')  # data required time
    slk:   Decimal = Decimal('0.0')  # timing slack


@dataclass
class TimePath(Path):
    """
    A time path of a report from the command 'report_timing'.
    """
    comp: str         = None                          # crpr common point
    thp:  list[Pin]   = field(default_factory=list)   # through pin list
    hcd:  list[tuple] = field(default_factory=list)   # highlight cell delay

    sedv: Decimal = Decimal('0.0')  # startpoint clock edge value
    eedv: Decimal = Decimal('0.0')  # endpoint clock edge value
    llat: Decimal = Decimal('0.0')  # launch clock latency
    clat: Decimal = Decimal('0.0')  # capture clock latency
    crpr: Decimal = Decimal('0.0')  # crpr
    skew: Decimal = Decimal('0.0')  # clock skew
    lpg:  bool    = True            # startpoint clock is propagated
    cpg:  bool    = True            # endpoint clock is propagated

    edly_en: bool    = False            # exception delay active
    edly:    Decimal = Decimal('0.0')   # exception delay (max delay)
    idly_en: bool    = False            # input delay active
    idly:    Decimal = Decimal('0.0')   # input delay
    odly_en: bool    = False            # output delay active
    odly:    Decimal = Decimal('0.0')   # output delay
    unce:    Decimal = Decimal('0.0')   # clock uncertainty
    pmag_en: bool    = False            # path margin active
    pmag:    Decimal = Decimal('0.0')   # path margin
    lib:     Decimal = None             # library time arc
    dlat:    Decimal = Decimal('0.0')   # data latency

    lpath:   list[Pin] = field(default_factory=list)    # launch clock path pin list
    cpath:   list[Pin] = field(default_factory=list)    # capture clock path pin list
    dpath:   list[Pin] = field(default_factory=list)    # data path pin list
    llat_sc: Decimal   = Decimal('0.0')                 # launch clock source latency
    clat_sc: Decimal   = Decimal('0.0')                 # capture clock source latency

    cpid:     int     = None            # crpr point index in launch clock path
    llat_com: Decimal = Decimal('0.0')  # common latency of launch clock path
    clat_com: Decimal = Decimal('0.0')  # common latency of capture clock path

    ldt:  Decimal = Decimal('0.0')  # launch clock path delta
    cdt:  Decimal = Decimal('0.0')  # capture clock path delta
    ddt:  Decimal = Decimal('0.0')  # data path delta

    llvl:  int = 0  # launch clock path level
    clvl:  int = 0  # capture clock path level
    dlvl:  int = 0  # data path level
    cclvl: int = 0  # common clock path level

    llat_seg: list[tuple] = field(default_factory=list) # launch clock path latency  (segment)
    clat_seg: list[tuple] = field(default_factory=list) # capture clock path latency (segment)
    dlat_seg: list[tuple] = field(default_factory=list) # data path latency          (segment)
    ldt_seg:  list[tuple] = field(default_factory=list) # launch clock path delta    (segment)
    cdt_seg:  list[tuple] = field(default_factory=list) # capture clock path delta   (segment)
    ddt_seg:  list[tuple] = field(default_factory=list) # data path delta            (segment)


class TimeReport:
    """
    Timing report parser.

    Attributes
    ----------
    opt  : a set of the report options.
    path : a list of timing paths.
    """
    _path_re = re.compile(r'\s*\S+')
    _anno_sym = set(['H', '^', '*', '&', '$', '+', '@'])

    def __init__(self, cpkg:dict=None, cpin:dict=None,  
                 pc:dict=None, dpc:str=None, hcd:dict=None, 
                 cc:dict=None, dc:dict=None):
        """
        Arguments
        ---------
        cpkg : the cell package.
        cpin : the cell pin names.
        pc   : the path classifications by the regular expression.
        dpc  : the specific group for the default path.
        hcd  : highlight cell delay.
        cc   : the cell classify by the regular expression.
        dc   : the driving classify by regular pattern
        """
        ### attribute
        self._cpkg = {} if cpkg is None else cpkg
        self._cpin = set() if cpin is None else cpin
        self._pc = {} if pc is None else pc
        self._dpc = dpc
        self._hcd = {} if hcd is None else hcd
        self._cc = {} if cc is None else cc
        self._dc = {} if dc is None else dc
        ### data
        self._head = list()  # timing path header
        self.opt = set()     # report option
        self.path = list()   # path list

    def parse_report(self, rpt_fp, prange: list, is_debug: bool=False):
        """
        Parse the timing report.

        Arguments
        ---------
        rpt_fp : the file path of the timing report.
        prange : the list of the parsing ranges in the timing report.
        """
        if os.path.splitext(rpt_fp)[1] == '.gz':
            fp = gzip.open(rpt_fp, mode='rt')
        else:
            fp = open(rpt_fp)

        fno = self._parse_option(fp, 0)
        for pno, range_ in enumerate(prange, start=1):
            p_st, p_ed, p_nu = range_[0]-1, range_[1], range_[2]
            while fno < p_st:
                line, fno = fp.readline(), fno+1
            pcnt = 0  # parsed path count
            while True:
                if is_debug:
                    print('\n=== Parse Path {}:'.format(pno))
                is_eof, fno = self._parse_path(fp, fno, is_debug)
                if is_eof:
                    fp.close()
                    return
                elif p_ed is not None and fno >= p_ed:
                    break
                elif p_nu is not None and (pcnt := pcnt+1) == p_nu:
                    break
        fp.close()

    def _parse_option(self, fp, fno: int) -> int:
        """Return the read line count of the file."""
        opt_dict = {
            '-path_type': {'full': 'pf',
                           'full_clock': 'pfc',
                           'full_clock_expanded': 'pfce'},
            '-input_pins': 'input',
            '-nets': 'fo',
            '-transition_time': 'tran',
            '-capacitance': 'cap',
            '-show_delta': 'delta',
            '-crosstalk_delta': 'delta',
            '-derate': 'derate'
        }

        while (line := fp.readline()):
            fno += 1
            if line.lstrip().startswith('Report'):
                break

        while (line := fp.readline()):
            fno += 1
            tok = line.strip().split()
            if tok[0][0] == '*':
                break
            elif tok[0] in opt_dict:
                try:
                    if isinstance(value := opt_dict[tok[0]], dict):
                        self.opt.add(value[tok[1]])
                    else:
                        self.opt.add(value)
                except KeyError:
                    pass

        if {'tran', 'delta'}.issubset(self.opt):
            self.opt.add('dtran')
        self.opt.add('incr')
        return fno

    def _parse_path(self, fp, fno: int, is_debug: bool=False) -> tuple:
        """
        Parse a timing path.

        Returns
        -------
        is_eof : a bool of the eof check.
        fno    : the read line count of the file.
        """
        path = TimePath()

        ### parse path prefix info
        is_start = False
        while (line := fp.readline()):
            fno += 1
            if not (tok := line.strip().split()):
                continue
            if is_start and tok[0][0] == '-':
                break
            elif tok[0] == 'Startpoint:':
                path.ln = fno
                path.stp = tok[1]
                if tok[-1][-1] != ')':
                    tok, fno = fp.readline().strip().split(), fno + 1
                    sed_tmp = tok[0][1:]
                else:
                    sed_tmp = tok[2][1:]
                path.sck = tok[-1][:-1]
                if sed_tmp == 'rising':
                    path.sed = 'rise'
                elif sed_tmp == 'falling':
                    path.sed = 'fall'
                is_start = True
            elif tok[0] == 'Endpoint:':
                path.edp = tok[1]
                if tok[-1][-1] != ')':
                    tok, fno = fp.readline().strip().split(), fno + 1
                    eed_tmp = tok[0][1:]
                else:
                    eed_tmp = tok[2][1:]
                if eed_tmp != 'internal':
                    path.eck = tok[-1][:-1]
                if eed_tmp == 'rising':
                    path.eed = 'rise'
                elif eed_tmp == 'falling':
                    path.eed = 'fall'
            elif tok[0] == 'Last':
                path.comp = tok[3]
            elif tok[0] == 'Scenario:':
                path.scen = tok[1] 
            elif tok[0] == 'Verbose':
                path.scen = tok[3][1:-1] + ' (remote)'
            elif len(tok) > 1 and tok[1] == 'Group:':
                path.group = tok[2]
            elif len(tok) > 1 and tok[1] == 'Type:':
                path.type = tok[2]
            elif tok[0] == 'Point':
                self._head = self._path_re.findall(line)
        else:
            return True, fno

        ### parse launch path
        is_eof, fno = self._parse_lpath(fp, fno, path, is_debug)
        if is_eof:
            return True, fno

        if path.dpath[0].cell not in ('in', 'inout') and not path.idly_en:
            path.lpath.append(copy.deepcopy(path.dpath[0]))

        ### parse capture path
        is_eof, fno = self._parse_cpath(fp, fno, path, is_debug)
        if is_eof:
            return True, fno

        ### parse the slack
        for fno, line in enumerate(fp, fno+1):
            if not (tok := line.strip().split()):
                continue
            elif tok[0] == 'slack':
                path.slk = Decimal(tok[-1])
                break
            elif len(tok) >= 3 and tok[2][:-1] == 'unconstrained':
                path.req = math.inf
                path.slk = math.inf
                break
        else:
            return True, fno

        ### update path pin type
        self._update_pin_type(path.lpath)
        self._update_pin_type(path.dpath)
        self._update_pin_type(path.cpath)

        ### get data path latency / delta sum / path level
        path.dlat = path.dpath[-1].arr - path.dpath[0].arr
        for pin in path.dpath:
            path.ddt += pin.delta
            if pin.dir == 'out' and pin.type == 'leaf':
                path.dlvl += 1
        path.ddt -= path.dpath[0].delta

        ### get launch clock path latency / delta sum / path level
        if len(path.lpath):
            path.llat = path.lpath[-1].arr - path.sedv
            if path.cpid is not None:
                path.llat_com = path.lpath[path.cpid].arr - path.sedv
            for pin in path.lpath:
                path.ldt += pin.delta
                if pin.dir == 'out' and pin.type == 'leaf':
                    path.llvl += 1
                    if path.comp is not None and pin.name == path.comp:
                        path.cclvl = path.llvl
            path.llvl -= path.cclvl
        else:
            path.llat = path.llat_sc - path.sedv
            path.llat_sc = Decimal('0.0')

        ### get capture clock path latency / delta sum / path level
        if path.req == math.inf:
            path.clat = math.inf
            path.clat_sc = Decimal('0.0')
        elif len(path.cpath):
            if 'pf' in self.opt:
                path.clat = path.clat_sc
                path.clat_sc = Decimal('0.0')
            else:
                path.clat = path.cpath[-1].arr - path.eedv
            if path.cpid is not None:
                path.clat_com = path.cpath[path.cpid].arr - path.eedv
            for pin in path.cpath:
                path.cdt += pin.delta
                if pin.dir == 'out' and pin.type == 'leaf':
                    path.clvl += 1
            path.clvl -= path.cclvl
        else:
           #path.clat = path.clat_sc - path.eedv
            path.clat = path.clat_sc
            path.clat_sc = Decimal('0.0')

        ### get clock skew
        if path.req != math.inf:
            path.skew = path.llat - path.clat - path.crpr

        ### get path segment info
        if len(self._pc):
            self._get_path_segment(path, 'd')
            self._get_path_segment(path, 'l')
            self._get_path_segment(path, 'c')

        ### append new path to path list
        self.path.append(path)
        return False, fno

    def _parse_lpath(self, fp, fno: int, path: TimePath, is_debug: bool=False) -> tuple:
        """
        Parse the launch clock & data path.

        Returns
        -------
        is_eof : a bool of the eof check.
        fno    : the read line count of the file.
        """
        CKEG, SCLAT, LLAT, DLAT = range(4)
        state = CKEG
        stp_toks = path.stp.split('/')
        pv_pin, pv_pin_toks = Pin(), []

        while (line := fp.readline()):
            fno += 1
            if not (tok := self._path_re.findall(line)):
                continue
            if is_debug:
                print('ln_tok:'.ljust(9), fno, tok)

            tag0, tag1 = tok[0].lstrip(), tok[1].lstrip()
            if state == CKEG and tag0 == 'clock':
                tag3 = tok[3].lstrip()
                if tag1 == 'source':
                    path.llat_sc = Decimal(tok[-2])
                    state = LLAT
                elif tag3 == '(propagated)' or tag3 == 'latency)':
                    if len(tok) == 4:
                        tok, fno = fp.readline().strip().split(), fno + 1
                    path.llat_sc = Decimal(tok[-2])
                    state = LLAT
                else:
                    path.sck = tag1
                    path.sed = tok[2].lstrip()[1:]
                    if len(tok) == 4:
                        tok, fno = fp.readline().strip().split(), fno + 1
                    path.sedv = Decimal(tok[-2])
                    state = SCLAT
            elif state == SCLAT and tag0 == 'clock':
                if len(tok) == 4:
                    tok, fno = fp.readline().strip().split(), fno + 1
                path.llat_sc = Decimal(tok[-2])
                state = LLAT 
            elif tag1 == 'arrival':
                path.arr = Decimal(tok[-1])
                if is_debug:
                    print('arrival:'.ljust(9), path.dpath, '\n')
                self._get_last_pin_dir(path.dpath)
                return False, fno
            elif tag0 == 'input':
                path.idly_en = True
                path.idly = Decimal(tok[-3])
                if state == DLAT:
                    path.lpath, path.dpath = path.dpath, path.lpath
                state = DLAT
            else:
                # no startpoint clock propagate
                if state in (CKEG, SCLAT):
                    path.lpg = False
                    state = LLAT

                # ignore the redundant clock network delay info
                if tag0 == 'clock':  
                    continue

                pin = Pin(ln=fno)
                pin_toks = tag0.split('/')
                if is_debug:
                    print('pin_tok:'.ljust(9), pin_toks)

                # concat the separated info descriptions
                tok_len = len(tok)
                if (tok_len == 2) or \
                   (tok_len == 3 and tok[2].endswith('<-')) or \
                   (tok_len == 4 and tok[2].endswith('(gclock')):
                    seek_pos = fp.tell()
                    tok2, fno = self._path_re.findall(fp.readline()), fno+1
                    start_col = 0  # active data start column
                else:
                    tok2 = tok
                    match (tok[2].lstrip()):
                        case '<-'      : start_col = 3
                        case '(gclock' : start_col = 4
                        case _         : start_col = 2

                # get through pin
                if tok_len >= 3 and (tok[2].lstrip()) == '<-':
                    path.thp.append(tag0)

                # parsing pin info
                if tag1 == '(net)':
                    if tok2 != tok and tok2[1].lstrip()[0] == '(':
                        fp.seek(seek_pos)
                        fno -= 1
                        continue

                    # record fanout and cap to the last pin
                    if state == DLAT:
                        if is_debug:
                            print('dnet:'.ljust(9), path.dpath[-1])
                        self._parse_pin(path.dpath[-1], tok2, start_col)
                    else:
                        if is_debug:
                            print('lnet:'.ljust(9), path.lpath[-1])
                        self._parse_pin(path.lpath[-1], tok2, start_col)
                else:
                    pin.name, pin.cell = tag0, tag1[1:-1]
                    if is_debug:
                        print('pin_info:'.ljust(9), pin.name, pin.cell)

                    if 'r' in self._dc and (m := self._dc['r'].fullmatch(pin.cell)):
                        if len(m.groups()) and (drv := m.groups()[0]) in self._dc:
                            pin.drv = self._dc[drv]
                    self._parse_pin(pin, tok2, start_col)

                    if state == LLAT:
                        if pin.cell in ('in', 'inout') and pin_toks == stp_toks:
                            path.dpath.append(pin)
                            state = DLAT
                        elif pin_toks[:-1] == stp_toks:
                            path.dpath.append(pin)
                            state = DLAT
                        else:
                           #if tag0 == path.comp:
                           #    path.cpid = len(path.lpath)
                            path.lpath.append(pin)
                    else:
                        path.dpath.append(pin)

                    # get highlight time arc
                    if pv_pin.cell in self._hcd:
                        pair = f'{pv_pin_toks[-1]}:{pin_toks[-1]}'
                        if pin.cell in self._hcd and pair in self._hcd[pin.cell]:
                            tag = self._hcd[pin.cell][pair]
                            path.hcd.append((tag, pin.incr))

                    pv_pin.dir = self._get_prev_pin_dir(pv_pin_toks, pin_toks)
                    pv_pin = pin
                    pv_pin_toks = pin_toks

            if is_debug:
                if state == DLAT:
                    path_msg = path.dpath[-1] if len(path.dpath) > 0 else tuple()
                    print('dpath:'.ljust(9), path_msg, '\n')
                else:
                    path_msg = path.lpath[-1] if len(path.lpath) > 0 else tuple()
                    print('lpath:'.ljust(9), path_msg, '\n')

        return True, fno

    def _parse_cpath(self, fp, fno: int, path: TimePath, is_debug: bool=False) -> tuple:
        """
        Parse the capture clock path.

        Returns
        -------
        is_eof : a bool of the eof check.
        fno    : the read line count of the file.
        """
        lib_set = {'setup', 'hold', 'removal', 'recovery', 'gating'}
        CKEG, SCLAT, CLAT = range(3)
        state = CKEG
        pv_pin, pv_pin_toks = Pin(), []

        while (line := fp.readline()):
            fno += 1
            if line.lstrip().startswith('---'):
                return False, fno
            if not (tok := self._path_re.findall(line)):
                continue
            if is_debug:
                print('ln_tok:'.ljust(9), fno, tok)

            tag0, tag1 = tok[0].lstrip(), tok[1].lstrip()
            if state == CKEG and tag0 == 'clock':
                path.eck = tag1
                path.eed = tok[2].lstrip()[1:]
                if len(tok) == 4:
                    tok, fno = fp.readline().strip().split(), fno+1
                path.eedv = Decimal(tok[-2])
                state = SCLAT
            elif state == SCLAT and tag0 == 'clock' and tag1 == 'reconvergence':
                if len(tok) == 4:
                    tok, fno = fp.readline().strip().split(), fno+1
                path.clat_sc = Decimal(tok[-2])
                state = CLAT
            elif tag1 == 'required':
                path.req = Decimal(tok[-1])
                if is_debug:
                    print('required:'.ljust(9), path.cpath, '\n')
                if len(path.cpath) > 0:
                    path.cpath[-1].dir = 'in'
                else:
                    path.cpg = False
                return False, fno
            elif tag1 == 'reconvergence':
                path.crpr = Decimal(tok[-2])
            elif tag1 == 'margin':
                path.pmag_en = True
                path.pmag = (-1 if path.type == 'max' else 1) * Decimal(tok[-2])
            elif tag1 == 'uncertainty':
                path.unce = (-1 if path.type == 'max' else 1) * Decimal(tok[-2])
            elif tag1 == 'external':
                path.odly_en = True
                path.odly = (-1 if path.type == 'max' else 1) * Decimal(tok[-2])
            elif tag1 in lib_set:
                path.lib = (-1 if path.type == 'max' else 1) * Decimal(tok[-2])
            elif tag0 == 'max_delay':
                path.edly_en = True
                path.edly = Decimal(tok[-2])
                path.eedv = path.edly
                state = SCLAT
            else:
                # no endpoint clock propagate
                if state in (CKEG, SCLAT):
                    path.cpg = False
                    state = CLAT

                pin = Pin(ln=fno)
                pin_toks = tag0.split('/')
                if is_debug:
                    print('pin_tok:'.ljust(9), pin_toks)

                # concat the separated info descriptions
                tok_len = len(tok)
                if (tok_len == 2) or \
                   (tok_len == 4 and tok[2].endswith('(gclock')):
                    seek_pos = fp.tell()
                    tok2, fno = self._path_re.findall(fp.readline()), fno+1
                    start_col = 0  # active data start column
                else:
                    tok2 = tok
                    start_col = 4 if tok[2].endswith('(gclock') else 2

                # parsing pin info
                if tag1 == '(net)':
                    if tok2 != tok and tok2[1].lstrip()[0] == '(':
                        fp.seek(seek_pos)
                        fno -= 1
                        continue

                    # record fanout and cap to the last pin
                    if is_debug:
                        print('cnet:'.ljust(9), path.cpath[-1])
                    self._parse_pin(path.cpath[-1], tok2, start_col)
                else:
                    pin.name, pin.cell = tag0, tag1[1:-1]
                    if is_debug:
                        print('pin_info:'.ljust(9), pin.name, pin.cell)

                    if 'r' in self._dc and (m := self._dc['r'].fullmatch(pin.cell)):
                        if len(m.groups()) and (drv := m.groups()[0]) in self._dc:
                            pin.drv = self._dc[drv]
                    self._parse_pin(pin, tok2, start_col)

                    if tag0 == path.comp:
                        path.cpid = len(path.cpath)
                    path.cpath.append(pin)

                    pv_pin.dir = self._get_prev_pin_dir(pv_pin_toks, pin_toks)
                    pv_pin = pin
                    pv_pin_toks = pin_toks

            if is_debug:
                path_msg = path.cpath[-1] if len(path.cpath) > 0 else tuple()
                print('cpath:'.ljust(9), path_msg, '\n')

        return True, fno

    def _parse_pin(self, pin: Pin, tok: list, cid: int):
        """
        Parse a data pin.

        Arguments
        ---------
        pin : pin object.
        tok : pin info toks.
        cid : start column id.

        Returns
        -------
        pin : pin object.
        """
        cpos = sum([len(tok[i]) for i in range(cid+1)])
        try:
            ## fanout, cap, dtran, tran, derate, delta
            tid, tpos = 0, len(self._head[0])
            for attr in ['fo', 'cap', 'dtran', 'tran', 'derate', 'delta']:
                if attr in self.opt:
                    tpos += len(self._head[tid := tid+1])
                    if tpos >= cpos:
                        if attr == 'fo':
                            pin.__dict__[attr] = int(tok[cid])
                        else:
                            pin.__dict__[attr] = Decimal(tok[cid])
                        cpos += len(tok[cid := cid+1])

            ## incr, arr, location
            pin.incr, cid = Decimal(tok[cid]), cid+1
            if tok[cid][-1] in self._anno_sym:
                cid += 1

            if tok[cid][-1] == 'r' or tok[cid][-1] == 'f':
                pin.arr, pin.incr = pin.incr, Decimal('0.0')
            else:
                pin.arr, cid = Decimal(tok[cid]), cid+1

            if tok[cid][-1] == 'r' or tok[cid][-1] == 'f':
                cid += 1

            if 'phy' in self.opt:
                pos = tok[cid].lstrip()[1:-1]
                pin.phy = [int(x) for x in pos.split(',')]
        except IndexError:
            pass
        except ValueError:
            pass
        except Exception as e:
            func_name = sys._getframe().f_code.co_name
            print(f'\nOops!  Unknown exception occur. ({func_name})')
            print(type(e), '\n')
            breakpoint()

    def _get_prev_pin_dir(self, pv_pin_toks: list, pin_toks: list) -> str:
        """Get previous pin direction."""
        if (plen := len(pv_pin_toks)):
            clen = len(pin_toks)
            if plen < clen and pv_pin_toks[:-1] == pin_toks[:plen-1]:
                return 'in'
            elif plen > clen and pv_pin_toks[:clen-1] == pin_toks[:-1]:  
                return 'out'
            elif pv_pin_toks[:-1] == pin_toks[:-1]:
                return 'in'
            else:
                return 'out'
        else:
            return None

    def _get_last_pin_dir(self, path: list[Pin]):
        """Get last pin direction."""
        ppin_dir = path[-2].dir
        plen = len(ppin_toks := path[-2].name.split('/'))
        clen = len(cpin_toks := path[-1].name.split('/'))
        if ppin_dir == 'in' and ppin_toks[:-1] == cpin_toks[:-1]:
            path[-1].dir = 'out'
        elif (ppin_dir == 'out' and plen > clen and ppin_toks[:clen-1] == cpin_toks[:-1]):
            path[-1].dir = 'out'
        else:
            path[-1].dir = 'in'

    def _update_pin_type(self, path: list[Pin]):
        """
        Update pin type.

        Types
        -----
        start : path start pin
        end   : path end pin
        leaf  : leaf cell pin
        hier  : hierarchical module pin
        """
        if (plen := len(path)) == 0:
            return
        i = 0
        while i <= plen - 2:
            i2 = i + 1
            if path[i].dir == 'in' and path[i2].dir == 'out':
                path[i].type = path[i2].type = 'leaf'
                i += 2
            else:
                path[i].type = 'hier'
                i += 1
        path[0].type = 'start'
        path[-1].type = 'end'
        return

    def _get_path_segment(self, timing_path: TimePath, path_type: str):
        """
        Get the path segment information.

        Attributes
        ----------
        timing_path : timing path object
        path_type   : path type (d: dpath / l: lpath / c: cpath)
        """
        lat_list = timing_path.__dict__[f'{path_type}lat_seg']
        dt_list = timing_path.__dict__[f'{path_type}dt_seg']
        pre_tag, pre_inst = ['' for i in range(2)]
        lat_sum, dt_sum = [Decimal('0.0') for i in range(2)]
        com_done, com_lat = False, Decimal('0.0')
        is_clk = True if path_type in ('l', 'c') else False

        for pin in timing_path.__dict__[f'{path_type}path'][1:]:
            if pin.name == pre_inst:
                continue
            pre_inst = pin.name

            for tag, pat in self._pc.items():
                if pat.fullmatch(pin.name):
                    break
            else:
                tag = self._dpc

            if is_clk and not com_done:
                com_lat += pin.incr

            if pre_tag == '':
                pre_tag = tag
                lat_sum = pin.incr 
                dt_sum = pin.delta
            elif is_clk and not com_done and (pin.name == timing_path.comp):
                lat_list.append([f'{tag}(c)', (lat_sum + pin.incr)])
                dt_list.append([f'{tag}(c)', (dt_sum + pin.delta)])
                pre_tag, com_done = '', True
            elif tag != pre_tag:
                lat_list.append([pre_tag, lat_sum])
                dt_list.append([pre_tag, dt_sum])
                pre_tag, lat_sum, dt_sum = tag, pin.incr, pin.delta
            else:
                lat_sum += pin.incr 
                dt_sum += pin.delta

        if lat_sum != Decimal('0.0'):
            lat_list.append([pre_tag, lat_sum])
            dt_list.append([pre_tag, dt_sum])


