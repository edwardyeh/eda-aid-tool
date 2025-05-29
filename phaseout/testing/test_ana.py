#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: {license}
#
# {one line description}
#
# Copyright (C) 2024 Yeh, Hsin-Hsien <yhh76227@gmail.com>
#
# {comment}
#

XLSX_FILE = ""

WORKSHEET = [
    {
        "table": "table2", 
        "hard_bin_column": "C",
        "x_coordinate_column": "E",
        "y_coordinate_column": "F",
        "data_row": (4, 8),
        "data_column": ("G", "H"),
        "pass_hard_bin_id": (1,), 
        "diagram_type": "cdf",
    },
{},
]

##############################################################################
### Main Function

import openpyxl as xl
