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
import datetime
import gzip
import re
import sys
from pathlib import Path


class LEFParser:
    """
    DEF parser for the layout check.
    """
    def __init__(self, lef_files: list, is_proc_time_show: bool=False):
        self.lef_files = []
        for path in lef_files:
            lef_file = Path(path)
            if not lef_file.exists():
                raise OSError(f"Cannot find the LEF file ({lef_file}).")
            self.lef_files.append(lef_file)
        self.blk_dict = {}
        self.proc_time = {}
        self.is_proc_time_show = is_proc_time_show

    def parse_lef(self):
        """
        Parse the LEF file.
        """
        ST_IDLE, ST_MACRO, ST_OBS = range(3)

        for lef_file in self.lef_files:
            if lef_file.suffix == ".gz":
                fp = gzip.open(lef_file, mode="rt")
            else:
                fp = open(lef_file)

        self._proc_time_rec("START")

        state = ST_IDLE
        while (line := fp.readline()) != "":
            line = line.split('#')[0].strip()
            if line == "":
                continue
            if line.startswith("END"):
                continue

            desc_list = line.split()
            if state == ST_IDLE: 
                if desc_list[0] == "MACRO":
                    macro = self.blk_dict.setdefault(desc_list[1], {
                        "type": None,
                        "cw": None,
                        "t": [], "b": [], "l": [], "r": []
                    })
                    state = ST_MACRO
                    self._proc_time_rec(f"MACRO: {desc_list[1]}")
            elif state == ST_MACRO:
                if desc_list[0] == "OBS":
                    state = ST_OBS
                    self._proc_time_rec("OBS")
            elif state == ST_OBS:
                if desc_list[0] == "LAYER" and desc_list[1].lower() == "overlap":
                    self._parse_layer(fp, macro)
                    state = ST_IDLE
                    self._proc_time_rec("LAYER")
        fp.close()

    def _parse_layer(self, lef_fp, macro: dict):
        """Parsing layer."""
        desc_toks = [] 
        while (line := lef_fp.readline()) != "":
            line = line.split('#')[0].strip()
            if line == "":
                continue
            if line == "END OBS":
                return

            desc_toks.extend(line.split())
            if desc_toks[-1] != ';':
                continue

            # Get the corner coorderination list
            macro["type"], coor_list = desc_toks[0], []
            for i in range(1, len(desc_toks)-1, 2):
                coor_list.append((int(desc_toks[i]), int(desc_toks[i+1])))

            # Get the winding order of the die area
            acc = 0
            for i in range(size:=len(coor_list)):
                i2 = (i + 1) % size
                acc += coor_list[i][0] * coor_list[i2][1] - \
                       coor_list[i2][0] * coor_list[i][1]

            prv_x, prv_y = coor_list[0]
            if acc < 0:
                macro["cw"] = True
                # Get the boundary list
                for cur_x, cur_y in coor_list[1:]:
                    if cur_x == prv_x:
                        if cur_y > prv_y:
                            macro["l"].append((prv_x, cur_x, prv_y, cur_y))
                        else:
                            macro["r"].append((cur_x, prv_x, cur_y, prv_y))
                    else:
                        if cur_x > prv_x:
                            macro["t"].append((prv_x, cur_x, prv_y, cur_y))
                        else:
                            macro["b"].append((cur_x, prv_x, cur_y, prv_y))
                    prv_x, prv_y = cur_x, cur_y
            else:
                macro["cw"] = False
                # Get the boundary list
                for cur_x, cur_y in coor_list[1:]:
                    if cur_x == prv_x:
                        if cur_y > prv_y:
                            macro["r"].append((prv_x, cur_x, prv_y, cur_y))
                        else:                                
                            macro["l"].append((cur_x, prv_x, cur_y, prv_y))
                    else:
                        if cur_x > prv_x:
                            macro["b"].append((prv_x, cur_x, prv_y, cur_y))
                        else:                                
                            macro["t"].append((cur_x, prv_x, cur_y, prv_y))
                    prv_x, prv_y = cur_x, cur_y
            return

    def _proc_time_rec(self, tag: str):
        now_time = datetime.datetime.now()
        if self.is_proc_time_show and len(self.proc_time):
            prev_time = list(self.proc_time.values())[0]
            print(f"[Process Time] {tag:20s}: {now_time - prev_time}")
        self.proc_time[tag] = now_time


def debug_print(blk_dict: dict):
    print("\n=== [Debug] ===\n")
    for key, data in blk_dict.items():
        print("== Name: {}".format(key))
        print("---- TYPE:  {}".format(data["type"]))
        print("---- CW:    {}".format(data["cw"]))
        print("---- TOP:   {}".format(data["t"]))
        print("---- BOT:   {}".format(data["b"]))
        print("---- LEFT:  {}".format(data["l"]))
        print("---- RIGHT: {}".format(data["r"]))


if __name__ == "__main__":
    # for debug
    parser = LEFParser(["/mnt/DATA_DISK/Workspace/10_Project/01_SW/00_Python/eda_aid_tool/sample_phy/sample.lef"], 
                       is_proc_time_show=True)
    start_time = datetime.datetime.now()
    parser.parse_lef()
    end_time = datetime.datetime.now()
    debug_print(parser.blk_dict)
    print()
    print(f"[Total Process Time]: {end_time - start_time}")
    print()


