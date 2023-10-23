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


class Pin:
    """Data pin container."""
    def __init__(self, ln:str=None, pin:str=None, cell:str=None):
        self._attr = {
            'ln': ln, 'pin': pin, 'cell': cell, 
            'phy': None, 'fo': 0, 'cap': 0.0, 
            'dtran': 0.0, 'tran': 0.0, 'derate': 0.0, 
            'delta': 0.0, 'incr': 0.0, 'path': 0.0,
        }

    def __getitem__(self, key):
        return self._attr[key]

    def __setitem__(self, key, value):
        self._attr[key] = value

    def __repr__(self):
        msg_list = [f"{key}: {val}" for key, val in self._attr.items()]
        msg = "; ".join(msg_list)
        return f"{msg}"

    @property
    def ln(self): return self._attr['ln']          # (str ) line number
    @property                                      
    def pin(self): return self._attr['pin']        # (str ) full_name of a pin
    @property                                      
    def cell(self): return self._attr['cell']      # (str ) cell type
    @property                                      
    def phy(self): return self._attr['phy']        # (str ) coordination
    @property                                      
    def fo(self): return self._attr['fo']          # (int ) Number of fanout
    @property                                      
    def cap(self): return self._attr['cap']        # (float) capacitance
    @property                                      
    def dtran(self): return self._attr['dtran']    # (float) delta transition
    @property                                      
    def tran(self): return self._attr['tran']      # (float) transition
    @property                                      
    def derate(self): return self._attr['derate']  # (float) path derate (OCV)
    @property                                      
    def delta(self): return self._attr['delta']    # (float) path delta (SI)
    @property                                      
    def incr(self): return self._attr['incr']      # (float) latency increment
    @property                                      
    def path(self): return self._attr['path']      # (float) path accumulated latency


@dataclass (slots=True)
class Path:
    """Basic path container."""
    stp: str = None    # startpoint
    sck: str = None    # startpoint clock
    sed: str = None    # startpoint clock edge type
    edp: str = None    # endpoint
    eck: str = None    # endpoint clock
    eed: str = None    # endpoint clock edge type
    group: str = None  # path group
    type: str = None   # delay type
    scen: str = None   # Scenario

    arr: float = 0.0   # data arrival time
    req: float = 0.0   # data required time
    slk: float = 0.0   # timing slack


@dataclass (slots=True)
class TimePath(Path):
    """
    A time path of a report from the command 'report_timing'.
    """
    spin: int = None  # index of the startpoint clock pin in path list
    sgpi: int = None  # index of the startpoint gclock pin in path list
    egpi: int = None  # index of the endpoint gclock pin in path list

    hcd: dict = field(default_factory=dict)  # highlighted cell delay

    idly_en: bool = False  # input delay active
    idly: float = 0.0      # input delay
    sev: float = 0.0       # startpoint clock edge value
    sslat: float = 0.0     # startpoint clock source latency
    slat: float = 0.0      # startpoint clock latency
    lpath: list = field(default_factory=list)  # launch path pin list

    odly_en: bool = False  # output delay active
    odly: float = 0.0      # output delay
    eev: float = 0.0       # endpoint clock edge value
    eslat: float = 0.0     # endpoint clock source latency
    elat: float = 0.0      # endpoint clock latency
    cpath: list = field(default_factory=list)  # capture path pin list

    max_dly_en: bool = False  # max delay active
    max_dly: float = 0.0      # max delay
    pmarg_en: bool = False    # path margin active
    pmarg: float = 0.0        # path margin

    unce: float = 0.0  # clock uncertainty
    crpr: float = 0.0  # CRPR
    lib: float = 0.0   # library time arc
    sdt: float = 0.0   # startpoint clock delta
    edt: float = 0.0   # endpoint clock delta
    ddt: float = 0.0   # data path delta


class TimeReport:
    """
    Timing report parser.

    Attributes
    ----------
    opt  : a set of the report options.
    path : a list of timing paths.
    """
    _path_re = re.compile(r"\s*\S+")
    _anno_sym = set(['H', '^', '*', '&', '$', '+', '@'])

    def __init__(self, cell_ckp:set=None, inst_ckp:set=None, 
                 ickp_re:dict=None, hcd:dict=None, ckt:list=None, 
                 ckm:list=None, ckm_nock:bool=False, dpc:str=None, 
                 pc:dict=None):
        """
        Arguments
        ---------
        cell_ckp : the cell clock pin names.
        inst_ckp : the instance clock pins of the clock path.
        ickp_re  : the regex to indicate the instance clock pins.
        hcd      : high-lighted cell delay.
        ckt      : the clock cell types.
        ckm      : user-defined clock module.
        ckm_nock : attr: ckm with non-clock-cells.
        dpc      : the specific group for the default path.
        pc       : the path classifications (by regex).
        """
        ### attribute
        self._cell_ckp = set() if cell_ckp is None else cell_ckp
        self._inst_ckp = set() if inst_ckp is None else inst_ckp
        self._ickp_re = [] if ickp_re is None else ickp_re
        self._hcd = {} if hcd is None else hcd
        self._ckt = [] if ckt is None else ckt
        self._ckm = [] if ckm is None else ckm
        self._ckm_nock = ckm_nock
        self._dpc = dpc
        self._pc = {} if pc is None else pc
        ### data
        self._head = list()  # timing path header
        self.opt = set()     # report option
        self.path = list()   # path list

    def parse_report(self, rpt_fp, prange:list=None):
        """
        Parse the timing report.

        Arguments
        ---------
        rpt_fp : the file path of the timing report.
        prange : the list of the parsing ranges in the timing report.
        """
        if prange is None:
            prange = [(0, None, 1)]  # (start_line, last_line, path_count)

        if os.path.splitext(rpt_fp)[1] == '.gz':
            fp = gzip.open(rpt_fp, mode='rt')
        else:
            fp = open(rpt_fp)

        fno = self._parse_option(fp, 0)
        for range_ in prange:
            p_st, p_ed, p_nu = range_[0]-1, range_[1], range_[2]
            while fno < p_st:
                line, fno = fp.readline(), fno+1
            pcnt = 0  # parsed path count
            while True:
                is_eof, fno = self._parse_path(fp, fno)
                if is_eof:
                    return
                elif p_ed is not None and fno >= p_ed:
                    break
                elif p_nu is not None and (pcnt:=pcnt+1) == p_nu:
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

        for fno, line in enumerate(fp, fno+1):
            if line.lstrip().startswith('Report'):
                break

        for fno, line in enumerate(fp, fno+1):
            tok = line.strip().split()
            if tok[0][0] == '*':
                break
            elif tok[0] in opt_dict:
                try:
                    if isinstance(value:=opt_dict[tok[0]], dict):
                        self.opt.add(value[tok[1]])
                    else:
                        self.opt.add(value)
                except KeyError:
                    pass

        if {'tran', 'delta'}.issubset(self.opt):
            self.opt.add('dtran')
        self.opt.add('incr')
        return fno

    def _parse_path(self, fp, fno: int) -> tuple:
        """
        Parse a timing path.

        Returns
        -------
        is_eof : a bool of the eof check.
        fno    : the read line count of the file.
        """
        path = TimePath()

        ## parse path prefix info
        is_start = False
        for fno, line in enumerate(fp, fno+1):
            if not (tok:=line.strip().split()):
                continue
            # print("[parse prefix]", tok)  # debug
            if is_start and tok[0][0] == '-':
                break
            elif tok[0] == 'Startpoint:':
                path.stp = tok[1]
                is_start = True
            elif tok[0] == 'Endpoint:':
                path.edp = tok[1]
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

        ## parse launch data path
        is_eof, fno = self._parse_lpath(fp, fno, path)
        if is_eof:
            return True, fno

        ## parse launch data path
        is_eof, fno = self._parse_cpath(fp, fno, path)
        if is_eof:
            return True, fno

        ## parse the slack
        for fno, line in enumerate(fp, fno+1):
            if not (tok:=line.strip().split()):
                continue
            elif tok[0] == 'slack':
                path.slk = float(tok[2])
                break
        else:
            return True, fno

        self.path.append(path)
        return False, fno

    def _parse_lpath(self, fp, fno: int, path: TimePath) -> tuple:
        """
        Parse the launch clock & data path.

        Returns
        -------
        is_eof : a bool of the eof check.
        fno    : the read line count of the file.
        """
        CKEG, CKLAT, DLAT = range(3)
        state, add_ckp, pv_pin = CKEG, False, Pin()

        line, fno = fp.readline(), fno+1
        if not line:
            return True, fno

        while line:
            if not (tok:=self._path_re.findall(line)):
                line, fno = fp.readline(), fno+1
                continue
            # print("[parse lpath]", tok)  # debug
            tag0, tag1 = tok[0].lstrip(), tok[1].lstrip()
            if tag1 == 'arrival':
                path.arr = float(tok[-1])
                if path.spin is None:
                    path.spin = 0
                    print(" [WARNING] Cannot detect the startpoint," + 
                          " use 1st cell pin default.\n")
                path.slat = path.lpath[path.spin].path - path.sev - path.idly
                path.ddt -= path.sdt
                return False, fno
            elif tag1 == 'external':
                path.idly_en = True
                path.idly = float(tok[-3])
                add_ckp = True
            elif state == CKEG and tag0 == 'clock':
                path.sck = tag1
                path.sed = tok[2].lstrip()[1:]
                if len(tok) == 4:
                    tok, fno = fp.readline().strip().split(), fno+1
                path.sev = float(tok[-2])
                state = CKLAT
            elif state == CKLAT and tag0 == 'clock':
                if len(tok) == 4:
                    tok, fno = fp.readline().strip().split(), fno+1
                path.sslat = float(tok[-2])
                state = DLAT
            else:
                pin = Pin(ln=str(fno))
                tok_len = len(tok)
                if (tok_len == 2) or \
                   (tok_len == 3 and tok[2].endswith('<-')) or \
                   (tok_len == 4 and tok[2].endswith('(gclock')):
                    tok2, fno = self._path_re.findall(fp.readline()), fno+1
                    st_col = 0  # active data start column
                else:
                    tok2 = tok
                    match (tag2:=tok[2].lstrip()):
                        case '<-'      : st_col = 3
                        case '(gclock' : st_col = 4
                        case _         : st_col = 2

                if tag1 == '(net)':
                    self._parse_pin(path.lpath[-1], tok2, st_col)
                else:
                    pin['pin'], pin['cell'] = tag0, tag1[1:-1]
                    self._parse_pin(pin, tok2, st_col)
                    path.ddt += pin.delta
                    if tok_len > 2 and tok[2].endswith('(gclock'):
                        path.spin = len(path.lpath)
                        path.sgpi = path.spin
                        path.sdt = path.ddt
                    elif add_ckp:
                        path.spin = len(path.lpath)
                        path.sdt = path.ddt
                        add_ckp = False
                    elif tag0.split('/')[-1] in self._cell_ckp:
                        path.spin = len(path.lpath)
                        path.sdt = path.ddt
                    elif tag0 in self._inst_ckp:
                        path.spin = len(path.lpath)
                        path.sdt = path.ddt
                    else:
                        for ickp_re in self._ickp_re:
                            if ickp_re.fullmatch(tag0):
                                path.spin = len(path.lpath)
                                path.sdt = path.ddt
                                break
                    path.lpath.append(pin)
                    if pv_pin.cell in (hcd_dict:=self._hcd):
                        pi = pv_pin.pin.split('/')[-1]
                        po = pin.pin.split('/')[-1]
                        pair = f"{pi}:{po}"
                        if pin.cell in self._hcd and \
                               pair in self._hcd[pin.cell]:
                            tag = self._hcd[pin.cell][pair]
                            path.hcd[tag] = pin.incr
                    pv_pin = pin
            line, fno = fp.readline(), fno+1
        return True, fno

    def _parse_cpath(self, fp, fno: int, path: TimePath) -> tuple:
        """
        Parse the capture clock path.

        Returns
        -------
        is_eof : a bool of the eof check.
        fno    : the read line count of the file.
        """
        lib_set = {'setup', 'hold', 'removal', 'recovery', 'gating'}
        CKEG, CKLAT, DLAT = range(3)
        state = CKEG

        line, fno = fp.readline(), fno+1
        if not line:
            return True, fno

        while line:
            if not (tok:=self._path_re.findall(line)):
                line, fno = fp.readline(), fno+1
                continue
            # print("[parse cpath]", tok)  # debug
            tag0, tag1 = tok[0].lstrip(), tok[1].lstrip()
            if tag1 == 'required':
                path.req = float(tok[-1])
                path.elat = (path.req - path.eev - path.crpr - path.pmarg 
                             - path.unce - path.odly - path.lib)
                return False, fno
            elif tag1 == 'reconvergence':
                path.crpr = float(tok[-2])
            elif tag1 == 'margin':
                path.pmarg_en = True
                path.pmarg = float(tok[-2])
            elif tag1 == 'uncertainty':
                path.unce = float(tok[-2])
            elif tag1 == 'external':
                path.odly_en = True
                path.odly = float(tok[-2])
            elif tag1 in lib_set:
                path.lib = float(tok[-2])
            elif tag0 == 'max_delay':
                path.max_dly = float(tok[-2])
                path.max_dly_en = True
            elif state == CKEG and tag0 == 'clock':
                path.eck = tag1
                path.eed = tok[2].lstrip()[1:]
                if len(tok) == 4:
                    tok, fno = fp.readline().strip().split(), fno+1
                path.eev = float(tok[-2])
                state = CKLAT
            elif state == CKLAT and tag0 == 'clock':
                if len(tok) == 4:
                    tok, fno = fp.readline().strip().split(), fno+1
                path.eslat = float(tok[-2])
                state = DLAT
            elif state == DLAT:
                pin = Pin(ln=str(fno))
                tok_len = len(tok)
                if (tok_len == 2) or \
                   (tok_len == 4 and tok[2].endswith('(gclock')):
                    tok2, fno = self._path_re.findall(fp.readline()), fno+1
                    st_col = 0  # active data start column
                else:
                    tok2 = tok
                    st_col = 4 if tok[2].endswith('(gclock') else 2

                if tag1 == '(net)':
                    self._parse_pin(path.cpath[-1], tok2, st_col)
                else:
                    pin['pin'], pin['cell'] = tag0, tag1[1:-1]
                    self._parse_pin(pin, tok2, st_col)
                    path.edt += pin.delta
                    if tok_len > 2 and tok[2].endswith('(gclock'):
                        path.egpi = len(path.cpath)
                    path.cpath.append(pin)
            line, fno = fp.readline(), fno+1
        return True, fno

    def _parse_pin(self, pin: Pin, tok: list, st_col: int):
        """
        Parse a data pin.

        Returns
        -------
        pin : class Pin.
        """
        cid = st_col
        cpos = sum([len(tok[i]) for i in range(cid+1)])
        try:
            ## fanout, cap, dtran, tran, derate, delta
            tid, tpos = 0, len(self._head[0])
            for attr in ['fo', 'cap', 'dtran', 'tran', 'derate', 'delta']:
                if attr in self.opt:
                    tpos += len(self._head[tid:=tid+1])
                    if tpos >= cpos:
                        if attr == 'fo':
                            pin[attr] = int(tok[cid])
                        else:
                            pin[attr] = float(tok[cid])
                        cpos += len(tok[cid:=cid+1])

            ## incr, path, location
            pin['incr'], cid = float(tok[cid]), cid+1
            if tok[cid][-1] in self._anno_sym:
                cid += 1
            pin['path'], cid = float(tok[cid]), cid+1
            if tok[cid][-1] == 'r' or tok[cid][-1] == 'f':
                cid += 1
            if 'phy' in self.opt:
                pos = tok[cid].lstrip()[1:-1]
                pin['phy'] = [int(x) for x in pos.split(',')]
        except IndexError:
            pass
        except ValueError:
            pass

    def clock_path_check(self, pid: int=0, is_dump: bool=False) -> tuple:
        """
        Clock path similarity check.

        Returns
        -------
        gcc_rslt : list[0:2] The gclock check result.
        scc_rslt : list[0:4] The clock network check result.
        ctc_rslt : list[0:2] The clock cell type check result.
        """
        path = self.path[pid]

        if path.sgpi is not None:
            sgpi = path.sgpi + 1
            sgpath = path.lpath[0:sgpi]
            spath = path.lpath[sgpi:path.spin+1]
        else:
            sgpath, spath = [], path.lpath[0:path.spin+1]

        if path.egpi is not None:
            egpi = path.egpi + 1
            egpath = path.cpath[0:egpi]
            epath = path.cpath[egpi:path.spin+1]
        else:
            egpath, epath = [], path.cpath

        ## gclock path match check
        gcc_rslt, fail_by_ckm, gclist = ['PASS', ''], True, []
        egset = set([epin.pin for epin in egpath])
        empty_pin = Pin(ln="", pin="", cell="")
        same_ckm_pin = Pin(ln="", pin="... same clock module ...", cell="")

        if sgpath and egpath:
            sglen, eglen, pvckm_re = len(sgpath), len(egpath), None
            spin, epin, si, ei = sgpath[0], egpath[0], 1, 1
            while True:
                if spin.pin == epin.pin:
                    gclist.append((spin, epin))
                    match (si==sglen, ei==eglen):
                        case (False, False):
                            spin, si = sgpath[si], si+1
                            epin, ei = egpath[ei], ei+1
                        case (False, True):
                            gcc_rslt[0], fail_by_ckm = 'FAIL', False
                            for i in range(si, sglen):
                                gclist.append((sgpath[i], empty_pin))
                            break
                        case (True, False):
                            gcc_rslt[0], fail_by_ckm = 'FAIL', False
                            for i in range(ei, eglen):
                                gclist.append((empty_pin, egpath[i]))
                            break
                        case (True, True):
                            break
                else:
                    gcc_rslt[0], sckm, eckm = 'FAIL', False, False
                    if pvckm_re is not None:
                        ckm_list2 = [pvckm_re] + self._ckm
                    else:
                        ckm_list2 = self._ckm

                    for ckm_re in ckm_list2:
                        sckm = True if ckm_re.fullmatch(spin.pin) else False
                        eckm = True if ckm_re.fullmatch(epin.pin) else False
                        if sckm and eckm:
                            pvckm_re = ckm_re
                            break
                    if not (all_ckm := sckm and eckm):
                        pvckm_re = None
                    fail_by_ckm &= all_ckm

                    dummy_pin = same_ckm_pin if all_ckm else empty_pin
                    if spin.pin in egset:
                        gclist.append((dummy_pin, epin))
                        epin, ei = egpath[ei], ei+1
                    else:
                        gclist.append((spin, dummy_pin))
                        spin, si = sgpath[si], si+1

            if gcc_rslt[0] == 'FAIL' and fail_by_ckm:
                gcc_rslt[1] = "(caused by user-defined clk modules)"
        else:
            gcc_rslt[0] = 'N/A'

        ## sclock path match check
        if spath and spath[-1].cell in {'inout', 'in'}:
            del spath[-1]

        scc_rslt = (-1, 'N/A', 'N/A')  # (split_level, lineNo_in_spath, lineNo_in_epath)
        if spath and epath:
            slen, elen = len(spath), len(epath)
            spin, epin, si, ei = spath[0], epath[0], 1, 1
            while True:
                if spin.pin != epin.pin:
                    break
                else:
                    scc_rslt = (scc_rslt[0]+1, spin.ln, epin.ln)
                    if si == slen or ei == elen:
                        break
                    else:
                        spin, epin, si, ei = spath[si], epath[ei], si+1, ei+1

        ## cell type check
        fail_by_ckm = self._ckm_nock
        ctc_pass, ctc_rslt = True, None
        gct_list, sct_list, ect_list = [], [], []

        if self._ckt:
            pvckm_re = None
            # gclock path cell type check
            for i in range(len(gclist)):
                sc_pass = ec_pass = False
                sname, ename = gclist[i][0].cell, gclist[i][1].cell
                for ckt_en, ckt_re in self._ckt:
                    if not sc_pass:
                        if sname == "":
                            sc_pass = True
                        elif ckt_re.fullmatch(sname):
                            sc_pass = ckt_en
                    if not ec_pass:
                        if ename == "":
                            ec_pass = True
                        elif ckt_re.fullmatch(ename):
                            ec_pass = ckt_en
                    if sc_pass and ec_pass:
                        break
                ctc_pass &= (cur_pass := sc_pass and ec_pass)

                sc_is_ckm, ec_is_ckm = sc_pass, ec_pass
                if not cur_pass and self._ckm_nock:
                    sname, ename = gclist[i][0].pin, gclist[i][1].pin
                    if pvckm_re is not None:
                        ckm_list2 = [pvckm_re] + self._ckm
                    else:
                        ckm_list2 = self._ckm

                    for ckm_re in ckm_list2:
                        sc_is_ckm |= (True if ckm_re.fullmatch(sname) 
                                      else False)
                        ec_is_ckm |= (True if ckm_re.fullmatch(ename) 
                                      else False)
                        if sc_is_ckm and ec_is_ckm:
                            pvckm_re = ckm_re
                            break

                    if not (all_ckm := sc_is_ckm and ec_is_ckm):
                        pvckm_re = None
                    fail_by_ckm &= all_ckm

                sc_result = '' if sc_pass else 'IG' if sc_is_ckm else 'FA'
                ec_result = '' if ec_pass else 'IG' if ec_is_ckm else 'FA'
                gct_list.append((sc_result, ec_result))

            # launch path cell type check
            for pin in spath:
                sc_pass = False
                for ckt_en, ckt_re in self._ckt:
                    if ckt_re.fullmatch(pin.cell):
                        sc_pass = ckt_en
                        break
                ctc_pass &= sc_pass

                sc_is_ckm = False
                if not sc_pass and self._ckm_nock:
                    if pvckm_re is not None:
                        ckm_list2 = [pvckm_re] + self._ckm
                    else:
                        ckm_list2 = self._ckm

                    for ckm_re in ckm_list2:
                        sc_is_ckm = (True if ckm_re.fullmatch(pin.pin) 
                                     else False)
                        if sc_is_ckm:
                            pvckm_re = ckm_re
                            break

                    if not sc_is_ckm:
                        pvckm_re = None
                    fail_by_ckm &= sc_is_ckm

                status = '' if sc_pass else 'IG' if sc_is_ckm else 'FA'
                sct_list.append((pin, status))

            # capture path cell type check
            for pin in epath:
                ec_pass = False
                for ckt_en, ckt_re in self._ckt:
                    if ckt_re.fullmatch(pin.cell):
                        ec_pass = ckt_en
                        break
                ctc_pass &= ec_pass

                ec_is_ckm = False
                if not ec_pass and self._ckm_nock:
                    if pvckm_re is not None:
                        ckm_list2 = [pvckm_re] + self._ckm
                    else:
                        ckm_list2 = self._ckm

                    for ckm_re in ckm_list2:
                        ec_is_ckm = (True if ckm_re.fullmatch(pin.pin) 
                                     else False)
                        if ec_is_ckm:
                            pvckm_re = ckm_re
                            break

                    if not ec_is_ckm:
                        pvckm_re = None
                    fail_by_ckm &= ec_is_ckm

                status = '' if ec_pass else 'IG' if ec_is_ckm else 'FA'
                ect_list.append((pin, status))

            ctc_rslt = ['PASS' if ctc_pass else 'FAIL']
            if not ctc_pass and fail_by_ckm:
                ctc_rslt.append("(caused by user-defined clk modules)")
            else:
                ctc_rslt.append("")
        else:
            ctc_rslt = ['N/A', '']
            gct_list = [('--', '--') for i in range(len(gclist))]

        ## dump gclock compare list
        if is_dump:
            gc_col_sz = {'ln': 0, 'pin': 0, 'cell': 0}
            sc_col_sz = {'ln': 0, 'pin': 0, 'cell': 0}
            ec_col_sz = {'ln': 0, 'pin': 0, 'cell': 0}

            for i in range(len(gclist)):
                for cid in ('ln', 'pin', 'cell'):
                    if (len_:=len(gclist[i][0][cid])) > gc_col_sz[cid]:
                        gc_col_sz[cid] = len_
                    if (len_:=len(gclist[i][1][cid])) > gc_col_sz[cid]:
                        gc_col_sz[cid] = len_

            for pin in spath:
                for cid in ('ln', 'pin', 'cell'):
                    if (len_:=len(pin[cid])) > sc_col_sz[cid]:
                        sc_col_sz[cid] = len_

            for pin in epath:
                for cid in ('ln', 'pin', 'cell'):
                    if (len_:=len(pin[cid])) > ec_col_sz[cid]:
                        ec_col_sz[cid] = len_

            for cid, sz in {'ln': 4, 'pin': 10, 'cell': 10}.items():
                gc_col_sz[cid] = (sz if gc_col_sz[cid] < sz else gc_col_sz[cid])
                sc_col_sz[cid] = (sz if sc_col_sz[cid] < sz else sc_col_sz[cid])
                ec_col_sz[cid] = (sz if ec_col_sz[cid] < sz else ec_col_sz[cid])

            with open(f"clock_check{pid}.dump", "w") as f:
                f.write("\n=== GClock Compare:\n")
                f.write("+-{}-+-{}-+-{}-+-{}----+-{}----+\n".format(
                            '-' * 4, 
                            '-' * 2,
                            '-' * gc_col_sz['ln'],
                            '-' * gc_col_sz['pin'],
                            '-' * gc_col_sz['cell']))
                f.write("| {} | {} | {} | {}    | {}    |\n".format(
                            'Type'.center(4), 
                            'CK'.ljust(2), 
                            'Line'.ljust(gc_col_sz['ln']), 
                            'Pin'.ljust(gc_col_sz['pin']),
                            'Cell'.ljust(gc_col_sz['cell'])))
                f.write("+-{}-+-{}-+-{}-+-{}----+-{}----+\n".format(
                            '-' * 4, 
                            '-' * 2,
                            '-' * gc_col_sz['ln'],
                            '-' * gc_col_sz['pin'],
                            '-' * gc_col_sz['cell']))
                for i in range(len(gclist)):
                    f.write("| {} | {} | {} | {}    | {}    |\n".format(
                                'L'.center(4),
                                gct_list[i][0].rjust(2),
                                gclist[i][0].ln.rjust(gc_col_sz['ln']),
                                gclist[i][0].pin.ljust(gc_col_sz['pin']),
                                gclist[i][0].cell.ljust(gc_col_sz['cell'])))
                    f.write("| {} | {} | {} | {}    | {}    |\n".format(
                                'C'.center(4),
                                gct_list[i][1].rjust(2),
                                gclist[i][1].ln.rjust(gc_col_sz['ln']),
                                gclist[i][1].pin.ljust(gc_col_sz['pin']),
                                gclist[i][1].cell.ljust(gc_col_sz['cell'])))
                    f.write("+-{}-+-{}-+-{}-+-{}----+-{}----+\n".format(
                                '-' * 4, 
                                '-' * 2,
                                '-' * gc_col_sz['ln'],
                                '-' * gc_col_sz['pin'],
                                '-' * gc_col_sz['cell']))
                f.write("\n")

                scan_list = []
                if sct_list:
                    scan_list.append(('Launch', sct_list, sc_col_sz))
                if ect_list:
                    scan_list.append(('Capture', ect_list, ec_col_sz))

                for ctype, cell_list, col_sz in scan_list:
                    f.write(f"=== Non-CK type cell ({ctype} source):\n")
                    f.write("+-{}-+-{}-+-{}----+-{}----+\n".format(
                                '-' * 2,
                                '-' * col_sz['ln'],
                                '-' * col_sz['pin'],
                                '-' * col_sz['cell']))
                    f.write("| {} | {} | {}    | {}    |\n".format(
                                'CK'.ljust(2), 
                                'Line'.ljust(col_sz['ln']), 
                                'Pin'.ljust(col_sz['pin']),
                                'Cell'.ljust(col_sz['cell'])))
                    f.write("+-{}-+-{}-+-{}----+-{}----+\n".format(
                                '-' * 2,
                                '-' * col_sz['ln'],
                                '-' * col_sz['pin'],
                                '-' * col_sz['cell']))
                    for pin, ctc_status in cell_list:
                        f.write("| {} | {} | {}    | {}    |\n".format(
                                    ctc_status.rjust(2),
                                    pin.ln.rjust(col_sz['ln']),
                                    pin.pin.ljust(col_sz['pin']),
                                    pin.cell.ljust(col_sz['cell'])))
                    f.write("+-{}-+-{}-+-{}----+-{}----+\n".format(
                                '-' * 2,
                                '-' * col_sz['ln'],
                                '-' * col_sz['pin'],
                                '-' * col_sz['cell']))
                    f.write("\n")

        scc_rslt = (scc_rslt[0]+1, *scc_rslt[1:])
        return gcc_rslt, scc_rslt, ctc_rslt

    def get_path_segment(self, pid: int=0) -> dict:
        """
        Get the path segment information.

        Returns
        -------
        A dictionary include 6 classified lists:

          slat_list : the launch clock latency list.
          elat_list : the capture clock latency list.
          dlat_list : the data latency list.
          sdt_list  : the launch clock delta list.
          edt_list  : the capture clock delta list.
          ddt_list  : the data delta list.
        """
        path = self.path[pid]
        slat_list, sdt_list = [], []
        elat_list, edt_list = [], []
        dlat_list, ddt_list = [], []

        lat_sum, dt_sum = 0, 0
        tag, is_1st, is_clk = None, True, True
        for cid, cell in enumerate(path.lpath):
            if tag is None:
                new_tag = self._dpc
                for key, ps_re in self._pc.items():
                    if (m:=ps_re.fullmatch(cell.pin)):
                        new_tag = key
                        break
                tag = new_tag
                if is_1st:
                    is_1st = False
                    lat_sum, dt_sum = cell.incr, cell.delta
                elif new_tag is not None:
                    if is_clk:
                        slat_list.append(['TP', lat_sum])
                        sdt_list.append(['TP', dt_sum])
                    else:
                        dlat_list.append(['TP', lat_sum])
                        ddt_list.append(['TP', dt_sum])
                    lat_sum, dt_sum = cell.incr, cell.delta
                else:
                    lat_sum += cell.incr
                    dt_sum += cell.delta
            elif self._pc[tag].fullmatch(cell.pin) is None:
                new_tag = self._dpc
                for key, ps_re in self._pc.items():
                    if (m:=ps_re.fullmatch(cell.pin)):
                        new_tag = key
                        break
                if new_tag != tag:
                    if is_clk:
                        slat_list.append([tag, lat_sum])
                        sdt_list.append([tag, dt_sum])
                    else:
                        dlat_list.append([tag, lat_sum])
                        ddt_list.append([tag, dt_sum])
                    tag, lat_sum, dt_sum = new_tag, cell.incr, cell.delta
                else:
                    lat_sum += cell.incr
                    dt_sum += cell.delta
            else:
                lat_sum += cell.incr
                dt_sum += cell.delta

            key = 'TP' if tag == None else tag
            if cid == path.spin:
                slat_list.append([key, lat_sum])
                sdt_list.append([key, dt_sum])
                tag, is_1st, is_clk = None, True, False 
                lat_sum, dt_sum = 0, 0

        dlat_list.append([key, lat_sum])
        ddt_list.append([key, dt_sum])

        lat_sum, dt_sum = 0, 0
        tag, is_1st = None, True
        for cell in path.cpath:
            if tag is None:
                new_tag = self._dpc
                for key, ps_re in self._pc.items():
                    if (m:=ps_re.fullmatch(cell.pin)):
                        new_tag = key
                        break
                tag = new_tag
                if is_1st:
                    is_1st = False
                    lat_sum, dt_sum = cell.incr, cell.delta
                elif new_tag is not None:
                    elat_list.append(['TP', lat_sum])
                    edt_list.append(['TP', dt_sum])
                    lat_sum, dt_sum = cell.incr, cell.delta
                else:
                    lat_sum += cell.incr
                    dt_sum += cell.delta
            elif self._pc[tag].fullmatch(cell.pin) is None:
                new_tag = self._dpc
                for key, ps_re in self._pc.items():
                    if (m:=ps_re.fullmatch(cell.pin)):
                        new_tag = key
                        break
                if new_tag != tag:
                    elat_list.append([tag, lat_sum])
                    edt_list.append([tag, dt_sum])
                    tag, lat_sum, dt_sum = new_tag, cell.incr, cell.delta
                else:
                    lat_sum += cell.incr
                    dt_sum += cell.delta
            else:
                lat_sum += cell.incr
                dt_sum += cell.delta

        key = 'TP' if tag == None else tag
        elat_list.append([key, lat_sum])
        edt_list.append([key, dt_sum])

        return {'slat': slat_list, 'sdt': sdt_list,
                'elat': elat_list, 'edt': edt_list,
                'dlat': dlat_list, 'ddt': ddt_list}


