#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-only
#
# Copyright (C) 2025 Yeh, Hsin-Hsien <yhh76227@gmail.com>
#
"""
LEF Parser for the Layout Check
"""
import collections
import gzip
import re
import sys
from pathlib import Path


class LEFParser:
    """
    DEF parser for the layout check.
    """
    def __init__(self, lef_files: list):
        self.lef_files = []
        for path in lef_files:
            lef_file = Path(path)
            if not lef_file.exists():
                raise OSError(f"Cannot find the LEF file ({lef_file}).")
            self.lef_files.append(lef_file)
        self.blk_list = []

    def parse_lef(self):
        """
        Parse the LEF file.
        """
        ST_IDLE, ST_MACRO, ST_OBS, ST_LAYER = range(4)

        for lef_file in self.lef_files:
            if lef_file.suffix == ".gz":
                fp = gzip.open(lef_file, mode="rt")
            else:
                fp = open(lef_file)

        state, desc = ST_IDLE, ""
        while (line := fp.readline()) != "":
            line = line.split('#')[0].strip()
            if line == "":
                continue
            if line.startswith("END"):
                desc = ""
                continue
            if (desc := ' '.join([desc, line]))[-1:] != ';':
                continue

            desc_list = desc.split()
            if desc_list[0] == "MACRO":
                macro = {"name": desc_list[1]}
            ### BOOKMARK ###

            elif desc_list[0] == "UNITS":
                self.def_dict["unit"] = {
                    "unit": desc_list[2],
                    "percision": int(desc_list[3])
                }
            elif desc_list[0] == "DIEAREA":
                self._parse_diearea(desc)
            elif desc_list[0] == "NONDEFAULTRULES":
                self._parse_ndr(fp)
            elif desc_list[0] == "COMPONENTS":
                self._parse_components(fp, req_dict["comp"])
            elif desc_list[0] == "SPECIALNETS":
                pass
            elif desc_list[0] == "NETS":
                self._parse_net(fp, req_dict["net"])
            desc = ""
        fp.close()

    def _parse_diearea(self, desc: str):
        """Parsing die area."""
        # Get the corner coorderination list
        diearea = {"coor": [], "cw": None, "t": [], "b": [], "l": [], "r": []}

        coor_list = diearea["coor"]
        for data in re.findall(r"\(\s*([-]*\d+)\s+([-]*\d+)\s*\)", desc):
            coor_list.append((int(data[0]), int(data[1])))

        # Get the winding order of the die area
        acc = 0
        for i in range(size:=len(coor_list)):
            i2 = (i + 1) % size
            acc += coor_list[i][0] * coor_list[i2][1] - \
                   coor_list[i2][0] * coor_list[i][1]

        prv_x, prv_y = coor_list[0]
        if acc < 0:
            diearea["cw"] = True
            # Get the boundary list
            for cur_x, cur_y in coor_list[1:]:
                if cur_x == prv_x:
                    if cur_y > prv_y:
                        diearea["l"].append((prv_x, cur_x, prv_y, cur_y))
                    else:
                        diearea["r"].append((cur_x, prv_x, cur_y, prv_y))
                else:
                    if cur_x > prv_x:
                        diearea["t"].append((prv_x, cur_x, prv_y, cur_y))
                    else:
                        diearea["b"].append((cur_x, prv_x, cur_y, prv_y))
                prv_x, prv_y = cur_x, cur_y
        else:
            diearea["cw"] = False
            # Get the boundary list
            for cur_x, cur_y in coor_list[1:]:
                if cur_x == prv_x:
                    if cur_y > prv_y:
                        diearea["r"].append((prv_x, cur_x, prv_y, cur_y))
                    else:                                
                        diearea["l"].append((cur_x, prv_x, cur_y, prv_y))
                else:
                    if cur_x > prv_x:
                        diearea["b"].append((prv_x, cur_x, prv_y, cur_y))
                    else:                                
                        diearea["t"].append((cur_x, prv_x, cur_y, prv_y))
                prv_x, prv_y = cur_x, cur_y

        self.def_dict["diearea"] = diearea

    def _parse_ndr(self, def_fp):
        """Parse non-default-rules."""
        ndr_dict = collections.defaultdict(dict)

        desc = ""
        while (line := def_fp.readline()) != "":
            line = line.split('#')[0].strip()
            if line == "":
                continue
            if line == "END NONDEFAULTRULES":
                break
            if (desc := ' '.join([desc, line]))[-1:] != ';':
                continue

            cmd_stack = []
            for tok in desc.split():
                if tok in {'+', ';'}:
                    if cmd_stack[0] == '-':
                        ndr = ndr_dict[cmd_stack[1]]
                        ndr["style"] = "SOFT"
                    elif cmd_stack[0] == "HARDSPACING":
                        ndr["style"] = "HARD"
                    elif cmd_stack[0] == "LAYER":
                        layer = ndr.setdefault(cmd_stack[1], {})
                        for i in range(2, len(cmd_stack), 2):
                            layer[cmd_stack[i].lower()] = int(cmd_stack[i+1])
                    cmd_stack = []
                else:
                    cmd_stack.append(tok)
            desc = ""

        self.def_dict["ndr"] = ndr_dict

    def _parse_components(self, def_fp, req_comp: set):
        """Parse components."""
        comp_dict = collections.defaultdict(dict)
        req_num = -1 if req_comp is None else len(req_comp)
        
        desc = ""
        while (line := def_fp.readline()) != "":
            line = line.split('#')[0].strip()
            if line == "":
                continue
            if line == "END COMPONENTS":
                break
            if req_num == 0:
                continue
            if (desc := ' '.join([desc, line]))[-1:] != ';':
                continue

            cmd_stack = []
            for tok in desc.split():
                if tok in {'+', ';'}:
                    if cmd_stack[0] == '-':
                        if req_num >= 0 and cmd_stack[1] not in req_comp:
                            break
                        req_num -= 1
                        comp = comp_dict[cmd_stack[1]]
                        comp["ref"] = cmd_stack[2]
                    elif cmd_stack[0] in {"FIXED", "COVER", "PLACED"}:
                        comp["sts"] = cmd_stack[0]
                        comp["pt"] = cmd_stack[2:4]
                        comp["ori"] = cmd_stack[5]
                    elif cmd_stack[0] == "UNPLACED":
                        comp["sts"] = cmd_stack[0]
                    cmd_stack = []
                else:
                    cmd_stack.append(tok)
            desc = ""

        self.def_dict["comp"] = comp_dict

    def _parse_net(self, def_fp, req_net: set):
        """Parse components."""
        ROUTE_STATUS = {"COVER", "FIXED", "ROUTED", "NOSHIELD", "NEW"}
        ROUTE_ORIENT = {"N", "S", "W", "E", "FN", "FS", "FW", "FE"}
        net_dict = collections.defaultdict(dict)
        req_num = -1 if req_net is None else len(req_net)
        
        desc = "" 
        while (line := def_fp.readline()) != "":
            line = line.split('#')[0].strip()
            if line == "":
                continue
            if line == "END NETS":
                break
            if req_num == 0:
                continue
            if (desc := ' '.join((desc, line)))[-1:] != ';':
                continue

            cmd_stack = []
            for tok in desc.split():
                if tok in {'+', ';'}:
                    if cmd_stack[0] == '-':
                        if req_num >= 0 and cmd_stack[1] not in req_comp:
                            break
                        req_num -= 1
                        net = net_dict[cmd_stack[1]]
                        pin = net.setdefault("pin", [])
                        for data in re.findall(r"\(\s*(\S+)\s+(\S+)\s*\)", 
                                               ' '.join(cmd_stack)):
                            if data[0] == "PIN":
                                pin.append(("port", data[1]))
                            else:
                                pin.append(("pin", '/'.join(data)))
                    elif cmd_stack[0] == "SHIELDNET":
                        net["shield"] = cmd_stack[1]
                    elif cmd_stack[0] == "NONDEFAULTRULE":
                        net["ndr"] = cmd_stack[1]
                    elif cmd_stack[0] in ROUTE_STATUS:
                        net["status"] = cmd_stack[0]
                        route_list = net.setdefault("route", [])
                        cmd_len, i = len(cmd_stack), 0
                        while i < cmd_len:
                            if cmd_stack[i] in ROUTE_STATUS:
                                route_list.append(route:={})
                                route["layer"], i = cmd_stack[i+1], (i + 2)
                                if cmd_stack[i] == "TAPER":
                                    route["taper"], i = "default", (i + 1)
                                elif cmd_stack[i] == "TAPERRULE":
                                    route["taper"], i = cmd_stack[i+1], (i + 2)
                                segment_list = route.setdefault("segment", [])
                                pt1x = int(cmd_stack[i+1])
                                pt1y = int(cmd_stack[i+2])
                                if cmd_stack[i+3] == ')':
                                    pt1e, i = 0, (i + 4)
                                else:
                                    pt1e, i = cmd_stack[i+3], (i + 5)
                            elif cmd_stack[i] == '(':
                                pt2x = pt1x if cmd_stack[i+1] == '*' else int(cmd_stack[i+1])
                                pt2y = pt1y if cmd_stack[i+2] == '*' else int(cmd_stack[i+2])
                                if cmd_stack[i+3] == ')':
                                    pt2e, i = 0, (i + 4)
                                else:
                                    pt2e, i = cmd_stack[i+3], (i + 5)
                                if pt1x == pt2x and pt1y != pt2y:
                                    if pt1y > pt2y:
                                        pt1y += pt1e
                                        pt2y -= pt2e
                                        coor = [pt1x, pt2x, pt2y, pt1y]
                                    else:
                                        pt1y -= pt1e
                                        pt2y += pt2e
                                        coor = [pt1x, pt2x, pt1y, pt2y]
                                    segment_list.append({"type": "rv", "coor": coor})
                                elif pt1x != pt2x and pt1y == pt2y:
                                    if pt1x > pt2x:
                                        pt1x += pt1e
                                        pt2x -= pt2e
                                        coor = [pt2x, pt1x, pt1y, pt2y]
                                    else:
                                        pt1x -= pt1e
                                        pt2x += pt2e
                                        coor = [pt1x, pt2x, pt1y, pt2y]
                                    segment_list.append({"type": "rh", "coor": coor})
                                else:
                                    coor_x = [pt2x, pt1x] if pt1x > pt2x else [pt1x, pt2x]
                                    coor_y = [pt2y, pt1y] if pt1y > pt2y else [pt1y, pt2y]
                                    segment_list.append({"type": "rd", "coor": coor_x + coor_y})
                            else:
                                segment = {
                                    "type": "vi", 
                                    "coor": [pt1x, pt1y], 
                                    "name": cmd_stack[i]
                                }
                                if (i := i + 1) < cmd_len and cmd_stack[i] in ROUTE_ORIENT:
                                    segment["orient"], i = cmd_stack[i], (i + 1)
                                segment_list.append(segment)
                    elif cmd_stack[0] == "USE":
                        net["style"] = cmd_stack[1]
                    cmd_stack = []
                else:
                    cmd_stack.append(tok)
            desc = ""

        self.def_dict["net"] = net_dict


def debug_print(def_dict):
    print("\n=== [Debug] ===\n")
    for key, value in def_dict.items():
        if key in {"diearea", "comp"}:
            print(f"=== {key}:")
            for key2, value2 in value.items():
                print(f"------ {key2}: {value2}")
        elif key == "ndr":
            print(f"=== {key}:")
            for key2, value2 in value.items():
                print(f"------ {key2}:")
                for key3, value3 in value2.items():
                    print(f"--------- {key3}: {value3}")
        elif key == "net":
            print(f"=== {key}:")
            for key2, value2 in value.items():
                print(f"------ {key2}: ")
                for key3, value3 in value2.items():
                    if key3 == "pin":
                        print(f"--------- {key3}:")
                        for data in value3:
                            print(f"----------- {data}")
                    elif key3 == "route":
                        for route in value3:
                            print(f"----------- {route}")
                    else:
                        print(f"--------- {key3}: {value3}")
        else:
            print(f"=== {key}: {value}")
    print()


if __name__ == "__main__":
    # for debug
    parser = DEFParser(sys.argv[1])
    parser.parse_def({
        "comp": {"U_INV_0", "U_CLK_BUF_5"},
        "net":  None
    })
    debug_print(parser.def_dict)


