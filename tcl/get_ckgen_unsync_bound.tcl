
# User Define:
#   - USER_CKGEN_UNSYNC_FILTER          (format: [list "ref_name=~..." "ref_name=~..." ...])
#   - USER_CKGEN_UNSYNC_EXCLUDE_PIN     (format: [list <pin1> <pin2> ...])
#   - USER_CKGEN_BOUND_FILTER           (format: [list "ref_name=~..." "ref_name=~..." ...])
#   - USER_CKGEN_BOUND_EXCLUDE_CELL     (format: [list <cell1> <cell2> ...])
#   - USER_CKBUF_UNSYNC_EXCLUDE_PIN     (format: [list <pin1> <pin2> ...])
#   - USER_CLKPO_UNSYNC_EXCLUDE_PORT    (format: [list <port1> <port2> ...])
#   - USER_SYNC_POINT                   (format: [list <point1> <point2> ...]) 
#   - USER_UNSYNC_POINT                 (format: [list <group_name1> [list point11, point12, ...] <group_name2> [list point21, point22, ...] ...])

proc get_unsync_name {prefix unsync_hier_name} {
    set match_sts [regexp {.*\/i_ckgen\w*\/(.*)} $unsync_hier_name -> unsync_hier_tail]
    if {[info exists unsync_hier_tail]} {
        regsub {\/u0}    $unsync_hier_tail {} unsync_hier_tail
        regsub {\/i_div} $unsync_hier_tail {} unsync_hier_tail
    } else {
        set unsync_hier_tail $unsync_hier_name
    }
    regsub -all {\/} $unsync_hier_tail {_} unsync_hier_tail
    regsub -all {\[} $unsync_hier_tail {_} unsync_hier_tail
    regsub -all {\]} $unsync_hier_tail {_} unsync_hier_tail

    return "${prefix}_${unsync_hier_tail}"
}

if {[info exists OUT_DIR]} {
    set OUT_DIR "./"
}

set rpt_sync   $OUT_DIR/ckgen_sync.cts
set rpt_unsync $OUT_DIR/ckgen_unsync.cts
set rpt_bound  $OUT_DIR/ckgen_bound.cts

echo "" > $rpt_unsync
echo "" > $rpt_bound

set solved_points {}


# ==============================================================================
# --- Generate ckgen unsync list
# ==============================================================================

redirect -tee -app $rpt_unsync {
    echo ""
    echo "\# ============================================= "
    echo "\#  Generate ckgen unsync list ..."
    echo "\# ============================================= "
    echo ""
}

redirect -app $rpt_unsync {

    # default list:
    #   clock gater type2
    #   ckdivn3atl*
    #   ckgen_mux*_type3*, ckgen_mux*_type2*
    #   div*_no_scan*

    set unsync_genclk_chks {}

    set unsync_hiers {}
    append_to_collection unsync_hiers [get_cells -quiet * -hier -filter "ref_name=~dsync_ignore*"]
    append_to_collection unsync_hiers [get_cells -quiet * -hier -filter "ref_name=~gck_etn_type2*"]
    append_to_collection unsync_hiers [get_cells -quiet * -hier -filter "ref_name=~ckdivn3atl* and ref_name!~ckdivn3atl*_mb*"]
    append_to_collection unsync_hiers [get_cells -quiet * -hier -filter "ref_name=~ckgen_mux*_type3* and ref_name!~*_mb*"]
    append_to_collection unsync_hiers [get_cells -quiet * -hier -filter "ref_name=~ckgen_mux*_type2* and ref_name!~*_mb*"]
    append_to_collection unsync_hiers [get_cells -quiet * -hier -filter "ref_name=~div*_no_scan*"]

    # append user defined filter condition
    if {[info exists USER_CKGEN_UNSYNC_FILTER]} {
        foreach filter_des $USER_CKGEN_UNSYNC_FILTER {
            append_to_col unsync_hiers [get_cells -quiet * -hier -filter "$filter_des"]
        }
    }

    # create user defined exclude list
    if {[info exists USER_CKGEN_UNSYNC_EXCLUDE_PIN]} {
        set USER_CKGEN_UNSYNC_EXCLUDE_PIN [get_pins -quiet $USER_CKGEN_UNSYNC_EXCLUDE_PIN]
    } else {
        set USER_CKGEN_UNSYNC_EXCLUDE_PIN {}
    }

    foreach_in_collection unsync_hier $unsync_hiers {
        set unsync_hier_name [get_object_name $unsync_hier]
        if {[regexp {.*\/i_ckgen\w*\/(.*)} $unsync_hier_name] == 0} {
            continue
        }
        set unsync_name [get_unsync_name "unsync" $unsync_hier_name]

        set unsync_cells [get_cells -quiet * -hier -filter "full_name=~$unsync_hier_name/* and is_sequential==true and is_integrated_clock_gating_cell==false"]
        set unsync_pins  [get_pins -quiet -of_obj $unsync_cells -filter "is_clock_pin==true"]
        append_to_collection unsync_genclk_chks [filter_col $unsync_pins "full_name=~*clk1_reg* or full_name=~*clk2_reg* or full_name=~*clkd90_pos_reg* or full_name=~*clkd90_neg_reg*"]

        #set unsync_pins [get_pins ${unsync_hier_name}/*_reg*/CK]

        if {[sizeof_collection $unsync_pins] > 0} {
            echo ""
            echo "\#I> $unsync_hier_name"
            echo ""

            # check exclude pin
            set exclude_pins [remove_from_col -intersect $USER_CKGEN_UNSYNC_EXCLUDE_PIN $unsync_pins]
            if {[sizeof_col $exclude_pins] > 0} {
                foreach_in_col exclude_pin $exclude_pins {
                    echo "\# (exclude) [get_object_name $exclude_pin]"
                }
                echo ""
                set unsync_pins        [remove_from_col $unsync_pins        $exclude_pins]
                set unsync_genclk_chks [remove_from_col $unsync_genclk_chks $exclude_pins]
            }

            echo "create_clock_skew_group -name $unsync_name -objects \[get_pins \[list \\"
            foreach_in_collection unsync_pin $unsync_pins {
                echo "    [get_object_name $unsync_pin] \\"
                append_to_col -unique solved_points $unsync_pin
            }
            echo "\]\]"
        } else {
            echo ""
            echo "\#I>(no_unsync) $unsync_hier_name no unsync pin."
        }
    }

}

redirect -tee -app $rpt_unsync {

    if {[sizeof_collection $unsync_genclk_chks] > 0} {
        echo ""
        echo "\# ================= "
        echo "\#  If pin is on generated clock path, remove it from unsync list:"

        foreach_in_collection unsync_genclk_chk $unsync_genclk_chks {
            echo "\# [get_object_name $unsync_genclk_chk]"
        }
    }

}

echo ""
echo "\# ============================================= "
echo "\#  Generate ckgen unsync done. "
echo ""


# ==============================================================================
# --- Generate ckgen bound list
# ==============================================================================

redirect -tee -app $rpt_bound {

    echo ""
    echo "\# ============================================= "
    echo "\#  Generate ckgen bound list ..."
    echo "\# ============================================= "
    echo ""

    # default list:
    #   ckdivn3atl*
    #   ckgen_mux*
    #   div*_no_scan*

    set bnd_hiers {}
    append_to_collection bnd_hiers [get_cells -quiet * -hier -filter "ref_name=~ckdivn3atl* and (ref_name!~ckdivn3atl*_mb* and ref_name!~*DW* and ref_name!~*DP*)"]
    append_to_collection bnd_hiers [get_cells -quiet * -hier -filter "ref_name=~ckgen_mux* and (ref_name!~*_mb* and ref_name!~*DW* and ref_name!~*DP*)"]
    append_to_collection bnd_hiers [get_cells -quiet * -hier -filter "ref_name=~div*_no_scan*"]

    # append user defined filter condition
    if {[info exists USER_CKGEN_BOUND_FILTER]} {
        foreach filter_des $USER_CKGEN_BOUND_FILTER {
            append_to_col bnd_hiers [get_cells -quiet * -hier -filter "$filter_des"]
        }
    }

    # create user defined exclude list
    if {[info exists USER_CKGEN_BOUND_EXCLUDE_CELL]} {
        set USER_CKGEN_BOUND_EXCLUDE_CELL [get_cells -quiet $USER_CKGEN_BOUND_EXCLUDE_CELL]
    } else {
        set USER_CKGEN_BOUND_EXCLUDE_CELL {}
    }

    echo ""
    echo "\# ================= "
    echo "\#  create_bound list: "

    if {[sizeof_collection $bnd_hiers] > 0} {
        foreach_in_collection bnd_hier $bnd_hiers {
            set bnd_hier_name [get_object_name $bnd_hier]
            if {[regexp {.*\/i_ckgen\w*\/(.*)} $bnd_hier_name] == 0} {
                continue
            }
            set bnd_name [get_unsync_name "bnd" $bnd_hier_name]

            # check exclude cell
            set bound_cells   [get_cells -quiet * -hier -filter "full_name=~$bnd_hier_name/* and is_hierarchical==false"]
            set exclude_cells [remove_from_col $USER_CKGEN_BOUND_EXCLUDE_CELL $bound_cells]

            if {[sizeof_col $exclude_cells] > 0} {
                foreach_in_col exclude_cell $exclude_cells {
                    echo "\# (exclude) [get_object_name $exclude_cell]"
                }

                echo "create_bound -name $bnd_name \[get_cells \[list \\"
                foreach_in_col bound_cell [remove_from_col $bound_cells $exclude_cells] {
                    echo "    [get_object_name $bound_cell] \\"
                }
                echo "\]\]"
            } else {
                echo "create_bound -name $bnd_name \[get_cells \[list $bnd_hier_name\]\]"
            }
        }
    } else {
        echo "\#I> no create_bound"
    }

}

echo ""
echo "\# ============================================= "
echo "\#  Generate ckgen bound done. "
echo ""

redirect -tee -app $rpt_unsync {
    echo ""
    echo "\# ================= "
    echo "\#  ckgen unsync report: $rpt_unsync"
    echo ""
}

redirect -tee -app $rpt_bound {
    echo ""
    echo "\# ================= "
    echo "\#  ckgen bound report: $rpt_bound"
    echo ""
}


# ==============================================================================
# --- Generate clock buffer unsync list
# ==============================================================================

if {![info exists CKBUF_DEFAULT_UNSYNC]} {
    set CKBUF_DEFAULT_UNSYNC "true"
}

if {$CKBUF_DEFAULT_UNSYNC} {
    set rpt_path $rpt_unsync
    set rpt_type "unsync"
} else {
    set rpt_path $rpt_sync
    set rpt_type "sync"
}

# create user defined exclude list
if {[info exists USER_CKBUF_UNSYNC_EXCLUDE_PIN]} {
    set USER_CKBUF_UNSYNC_EXCLUDE_PIN [get_pins -quiet $USER_CKBUF_UNSYNC_EXCLUDE_PIN]
} else {
    set USER_CKBUF_UNSYNC_EXCLUDE_PIN {}
}

redirect -tee -app $rpt_path {
    echo ""
    echo "# ============================================= "
    echo "#  Generate clock buffer $rpt_type list ..."
    echo "# ============================================= "
    echo ""
}

redirect -app $rpt_path {

    foreach_in_col clk [filter_col [all_clocks] "defined(sources)"] {
        set clk_source [get_attr -quiet $clk sources]
        if {[get_attr -quiet $clk_source object_class] == "pin"} {
            set clk_cell        [get_cells -quiet -of_obj $clk_source]
            set clk_name        [get_object_name $clk]
            set clk_source_name [get_object_name $clk_source]

            if {[get_attr -quiet $clk is_generated]} {
                echo "# (ignore) generated clock ($clk_name)"
                echo ""
            } elseif {[get_attr -quiet $clk_source pin_direction] == "in"} {
                echo "# (ignore) create clock at the input pin"
                echo "#          -- clock name: $clk_name"
                echo "#          -- clock root: $clk_source_name"
                echo ""
            } elseif {[sizeof_col [filter_col $clk_cell "is_hierarchical==true"]] > 0} {
                echo "# (ignore) create clock at the hierarchical cell pin"
                echo "#          -- clock name: $clk_name"
                echo "#          -- clock root: $clk_source_name"
                echo ""
            } elseif {[sizeof_col [filter_col $clk_cell "is_pad_cell==true"]] > 0} {
                echo "# (ignore) create clock at the PAD pin"
                echo "#          -- clock name: $clk_name"
                echo "#          -- clock root: $clk_source_name"
                echo ""
            } elseif {[sizeof_col [filter_col $clk_cell "is_black_box==true"]] > 0} {
                echo "# (ignore) create clock at the MACRO pin"
                echo "#          -- clock name: $clk_name"
                echo "#          -- clock root: $clk_source_name"
                echo ""
            } elseif {[sizeof_col [filter_col $clk_cell "is_sequential==true && is_integrated_clock_gating_cell==false"]] > 0} {
                echo "# (ignore) create clock at the is_sequential cell pin"
                echo "#          -- clock name: $clk_name"
                echo "#          -- clock root: $clk_source_name"
                echo ""
            } elseif {[sizeof_col [get_pins -of_obj $clk_cell -filter "pin_direction==in"]] > 1} {
                echo "# (ignore) create clock at the cell with multi inputs"
                echo "#          -- clock name: $clk_name"
                echo "#          -- clock root: $clk_source_name"
                echo ""
            } else {
                set unsync_pin  [get_pins -of_obj $clk_cell -filter "pin_direction==in"]
                set exclude_pin [remove_from_col -intersect $unsync_pin $USER_CKBUF_UNSYNC_EXCLUDE_PIN]

                if {[sizeof_col $exclude_pin] > 0} {
                    echo "# (exclude) $clk_name: [get_object_name $exclude_pin]"
                } else {
                    set unsync_pin_name [get_object_name $unsync_pin]
                    echo "set_clock_balance_points -consider_for_balancing true -balance_points \[get_pins $unsync_pin_name\]"
                    if {$CKBUF_DEFAULT_UNSYNC} {
                        set group_name [get_unsync_name "unsync_cb" $clk_name]
                        echo "create_clock_skew_group -name $group_name -object \[get_pins $unsync_pin_name\]"
                    }
                    append_to_col -unique solved_points $unsync_pin
                }
                echo ""
            }
        }
    }

}

echo ""
echo "\# ============================================= "
echo "\#  Generate clock buffer $rpt_type done. "
echo ""


# ==============================================================================
# --- Generate clock output unsync list
# ==============================================================================

if {![info exists CLKPO_DEFAULT_UNSYNC]} {
    set CLKPO_DEFAULT_UNSYNC "true"
}

if {$CLKPO_DEFAULT_UNSYNC} {
    set rpt_path $rpt_unsync
    set rpt_type "unsync"
} else {
    set rpt_path $rpt_sync
    set rpt_type "sync"
}

set CLKPO_DEFAULT_EXCLUDE [get_ports [list \
    *debug* \
]]

# create user defined exclude list
if {[info exists USER_CLKPO_UNSYNC_EXCLUDE_PORT]} {
    set USER_CLKPO_UNSYNC_EXCLUDE_PORT [get_ports -quiet $USER_CLKPO_UNSYNC_EXCLUDE_PORT]
} else {
    set USER_CLKPO_UNSYNC_EXCLUDE_PORT {}
}

redirect -tee -app $rpt_path {
    echo ""
    echo "# ============================================= "
    echo "#  Generate clock output $rpt_type list ..."
    echo "# ============================================= "
    echo ""
}

redirect -app $rpt_path {
    
    set unsync_ports {} 
    foreach_in_col clk_source [get_attr -quiet [all_clocks] sources] {
        append_to_col -unique unsync_ports [get_ports -quiet [all_fanout -from $clk_source -endpoints_only -flat]]
    }
    set unsync_ports [remove_from_col $unsync_ports $CLKPO_DEFAULT_EXCLUDE]

    foreach_in_col unsync_port $unsync_ports {
        set exclude_port [remove_from_col -intersect $unsync_port $USER_CLKPO_UNSYNC_EXCLUDE_PORT]

        if {[sizeof_col $exclude_port] > 0} {
            echo "# (exclude) [get_object_name $exclude_port]"
            echo ""
        } else {
            set unsync_port_name [get_object_name $unsync_port]
            echo "set_clock_balance_points -consider_for_balancing true -balance_points \[get_ports $unsync_port_name\]"
            if {$CLKPO_DEFAULT_UNSYNC} {
                set group_name [get_unsync_name "unsync_po" $unsync_port_name]
                echo "create_clock_skew_group -name $group_name -object \[get_ports $unsync_port_name\]"
            }
            append_to_col -unique solved_points $unsync_port
        }
    }
}

echo ""
echo "\# ============================================= "
echo "\#  Generate clock output $rpt_type done. "
echo ""


# ==============================================================================
# --- Generate user sync list
# ==============================================================================

if {[info exists USER_SYNC_POINT]} {
    set sync_pins  [get_pins  -quiet $USER_SYNC_POINT]
    set sync_ports [get_ports -quiet $USER_SYNC_POINT]

    redirect -tee -app $rpt_sync {
        echo ""
        echo "# ============================================= "
        echo "#  Generate user sync list ..."
        echo "# ============================================= "
        echo ""
    }

    redirect -app $rpt_sync {

        set conflict_points [remove_from_col -intersect $solved_points [add_to_col $sync_pins $sync_ports]]
        if {[sizeof_col $conflict_points] > 0} {
            foreach_in_col conflict_point $conflict_points {
                echo "# (conflict) [get_object_name $conflict_point]"
            }
            echo ""
        }
        set sync_pins  [remove_from_col $sync_pins  $conflict_points]
        set sync_ports [remove_from_col $sync_ports $conflict_points]
        
        foreach_in_col sync_pin $sync_pins {
            set sync_pin_name [get_object_name $sync_pin]
            echo "set_clock_balance_points -consider_for_balancing true -balance_points \[get_pins $sync_pin_name\]"
        }
        foreach_in_col sync_port $sync_ports {
            set sync_port_name [get_object_name $sync_port]
            echo "set_clock_balance_points -consider_for_balancing true -balance_points \[get_ports $sync_port_name\]"
        }
        echo ""
        append_to_col -unique solved_points [add_to_col $sync_pins $sync_ports]

    }

    echo ""
    echo "\# ============================================= "
    echo "\#  Generate user sync done. "
    echo ""
}

# ==============================================================================
# --- Generate user unsync list
# ==============================================================================

if {[info exists USER_UNSYNC_POINT]} {
    set unsync_pin_groups  [dict create]
    set unsync_port_groups [dict create]

    dict for {group_name group_list} $USER_UNSYNC_POINT {
        set unsync_pins  [get_pins  -quiet $group_list]
        set unsync_ports [get_ports -quiet $group_list]

        set conflict_points [remove_from_col -intersect $solved_points [add_to_col $unsync_pins $unsync_ports]]
        if {[sizeof_col $conflict_points] > 0} {
            foreach_in_col conflict_point $conflict_points {
                echo "# (conflict) $group_name: [get_object_name $conflict_point]"
            }
            echo ""
        }
        set unsync_pins  [remove_from_col $unsync_pins  $conflict_points]
        set unsync_ports [remove_from_col $unsync_ports $conflict_points]

        if {[sizeof_col $unsync_pins] > 0} {
            dict set unsync_pin_groups $group_name $unsync_pins
        }
        if {[sizeof_col $unsync_ports] > 0} {
            dict set unsync_port_groups $group_name $unsync_ports
        }
    }

    redirect -tee -app $rpt_unsync {
        echo ""
        echo "# ============================================= "
        echo "#  Generate user unsync list ..."
        echo "# ============================================= "
        echo ""
    }

    redirect -app $rpt_unsync {

        dict for {group_name unsync_pins} $unsync_pin_groups {
            foreach_in_col unsync_pin $unsync_pins {
                set unsync_pin_name [get_object_name $unsync_pin]
                echo "set_clock_balance_points -consider_for_balancing true -balance_points \[get_pins $unsync_pin_name\]"
            }

            echo "create_clock_skew_group -name user_unsync_pin_${group_name} -objects \[get_pins \[list \\"
            foreach_in_collection unsync_pin $unsync_pins {
                echo "    [get_object_name $unsync_pin] \\"
            }
            echo "\]\]"
        }

        dict for {group_name unsync_ports} $unsync_port_groups {
            foreach_in_col unsync_port $unsync_ports {
                set unsync_port_name [get_object_name $unsync_port]
                echo "set_clock_balance_points -consider_for_balancing true -balance_points \[get_ports $unsync_port_name\]"
            }

            echo "create_clock_skew_group -name user_unsync_port_${group_name} -objects \[get_ports \[list \\"
            foreach_in_collection unsync_port $unsync_ports {
                echo "    [get_object_name $unsync_port] \\"
            }
            echo "\]\]"
        }

    }

    echo ""
    echo "\# ============================================= "
    echo "\#  Generate user unsync done. "
    echo ""
}

