#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: {license}
#
# Path Group Reorder for the Violation Summary Report
#
# Copyright (C) 2025 Yeh, Hsin-Hsien <yhh76227@gmail.com>
#
import argparse 
import importlib
import re
import sys
from pathlib import Path

DEFAULT_GROUP = {}
USER_GROUP = {}

##############################################################################
### Function

def load_cfg(cfg_fn: str):
    """Load Tool Config"""  #{{{
    global DEFAULT_GROUP, USER_GROUP

    cfg_mod = Path(cfg_fn).stem
    sys.path.insert(0, '')
    try:
        config = importlib.import_module(cfg_mod)
    except ModuleNotFoundError:
        print(f"ModuleNotFoundError: Please create '{cfg_mod}' module in current directory")
        exit(1)

    if 'DEFAULT_GROUP' in dir(config):
        DEFAULT_GROUP = config.DEFAULT_GROUP
    if 'USER_GROUP' in dir(config):
        USER_GROUP = config.USER_GROUP

    # print(DEFAULT_GROUP)
    # print(USER_GROUP)
#}}}

def group_reorder(rpt_fp: str, out_fp: str):
    """Group Reorder"""  #{{{
    global DEFAULT_GROUP, USER_GROUP
    IDLE, PROC = list(range(2))

    for line in open(rpt_fp):
        line = line.rstrip()
        print(line)
#}}}

##############################################################################
### Main

def create_argparse() -> argparse.ArgumentParser:
    """Create Argument Parser"""  #{{{
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawTextHelpFormatter,
        description="Path Group Reorder for the Violation Summary Report")

    parser.add_argument('cfg_fp', help="config file path") 
    parser.add_argument('rpt_fp', help="report file path") 
    parser.add_argument('out_fp', help="output file path") 

    return parser
#}}}

def main():
    """Main Function"""  #{{{
    parser = create_argparse()
    args = parser.parse_args()

    load_cfg(args.cfg_fp)
    group_reorder(args.rpt_fp, args.out_fp)
#}}}

if __name__ == '__main__':
    main()
