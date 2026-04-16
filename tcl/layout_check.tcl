
############################################################
##
# @file    layout_check.tcl
# @package LayoutCheck
# @brief   PrimeTime-based Layout Check Procedure
# @ahthor  Edward Yeh
# @version 0.0.1
#
############################################################

namespace eval ::LayoutCheck {
    ##
    # @details Data structure:
    #          {GroupName1 {FunctionName1 Description1 FunctionName2 Description2 ...}
    #           GroupName2 {FunctionName1 Description1 FunctionName2 Description2 ...} ...}   
    variable help_message [dict create]

    ############################################################
    ##   General Function
    ############################################################

    ##
    # @brief Help message
    proc help {args} {
        variable help_message
        parse_proc_arguments -args $args arg

        # --- Get proc column length
        set proc_col_len 0
        dict for {group_name proc_list} $help_message {
            foreach {proc_name message} {
                set current_len [string size $proc_name]
                set proc_col_len [expr {max($proc_col_len, $current_len)}]
            }
        }

        # --- Print help message by selected mode
        set group_num [dict size $help_message]

        if {[info exists argsp(-interactive)]} {
            _print_group_list

            set cmd ""
            while {$cmd ne "q"} {
                puts -nonewline "Select group ('q' to exit, 'l' to show list): "
                flush stdout
                gets stdin cmd

                if {$cmd eq "q"} {
                    return
                } elseif {$cmd eq "l" || $cmd >= $group_num} {
                    _print_group_list
                } else {
                    _print_proc_message $cmd $proc_col_len
                }
            }
        } else {
            for {set i 0} {$i < $group_num} {incr i} {
                _print_proc_message $i $proc_col_len
            }
        }
    }

    define_proc_attributes help -info "Show the user procedure list" \
        -define_args { \
            {-interactive "Interactive mode" "" boolean optional}
        }

    proc _print_group_list {} {
        variable help_message
        set gid_col_len [string length [dict size $help_message]]
        set gid 0

        puts ""
        foreach group_name [dict keys $help_message] {
            puts [format "=== (%${gid_col_len}d) %s" $gid $group_name]
            incr gid
        }
        puts ""
    }

    proc _print_proc_message {gid proc_col_len} {
        variable help_message
        set group_name [lindex [dict keys $help_message] $gid]

        puts ""
        puts [format "=== (%d) %s" $gid $group_name]

        foreach {proc_name proc_message} [dict get $help_message $group_name] {
            puts [format "  %-${proc_col_len}s   %s" $proc_name $proc_message]
        }

        if {$proc_name ne ""} {puts ""}
    }

    ############################################################
    ##   Floorplan Check
    ############################################################

    set proc_message {highlight_cell_group "Highlight cells to check group bound"}
    dict append help_message "Floorplan Check" $proc_message

    ##
    # @brief Highlight cells to check group bound
    proc highlight_cell_group {args} {
        parse_proc_arguments -args $args arg

        if {[info exists argsp(-pallete)]} {
            set PALLETE $argsp(-pallete)
        } else {
            set PALLETE [list yellow orange red green blue purple light_orange \
                              light_red light_green light_blue light_purple]
        }

        if {[llength $argsp(cell_groups)] > [llength $PALLETE]} {
            puts "Warning: The number of cell groups is large than the size of the pallete, the color will repeat."
        }

        gui_change_highlight -remove -all_colors

        # --- Get max group name length to set column width
        set gname_strlen 0
        foreach cell_group $argsp(cell_groups) {
            set new_strlen [string length [lindex $cell_group 0]]
            set gname_strlen [expr {max($gname_strlen, $new_strlen)}]
        }

        # --- Highlight cells on layout view
        set pal_id 0
        set pal_size [llength $PALLETE]

        puts ""
        foreach cell_group $argsp(cell_groups) {
            set group_name [lindex cell_group 0]
            set cell_coll  [get_cells -quiet -of [lindex $cell_group 1] -filter "is_hierarchical==false"]
            set sel_color  [lindex $PALLETE $pal_id]

            if {[sizeof_col $cell_coll] > 0} {
                switch $argsp(-type) {
                    "macro" {
                        set cell_coll [filter $cell_coll "is_black_box==true"]
                    }
                    "seq" {
                        set cell_coll [filter $cell_coll "is_sequential==true"]
                    }
                    "dff" {
                        set cell_coll [filter $cell_coll "is_sequential==true && is_black_box==false"]
                    }
                    "comb" {
                        set cell_coll [filter $cell_coll "is_combinational==true"]
                    }
                }

                set comb_cnt [sizeof_col [filter $cell_coll "is_combinational==true"]]
                set seq_cnt  [sizeof_col [filter $cell_coll "is_sequential==true && is_black_box==false"]]
                set ma_cnt   [sizeof_col [filter $cell_coll "is_black_box==true"]]

                gui_change_highlight -color [lindex $PALLETE $pal_id] -coll $cell_coll

            } else {
                lassign {0 0 0} comb_cnt seq_cnt ma_cnt
            }

            echo [format "=== (%-12s) %${gname_strlen}s (COMB/SEQ/MACRO count: %d/%d/%d)" \
                    $sel_color $group_name $comb_cnt $seq_cnt $ma_cnt]

            set pal_id [expr {($pal_id + 1) % $pal_size}]
        }
        puts ""
    }

    define_proc_attributes highlight_cell_group -info [lindex $proc_message 1] \
        -define_args { \
            {-type        "Cell type (default is 'all'): \n \
                                all   - all types of cells \n \
                                macro - only black box cells \n \
                                seq   - only sequential cells (with black box) \n \
                                dff   - only sequential cells (without black box) \n \
                                comb  - only combinational cells" \
                cell_type one_of_string \
                { optional value_help {values {"all" "macro" "seq" "dff" "comb"}} {default "all"} }}
            {-pallete     "Custom pallete" pallete_list string optional}
            { cell_groups "Cell groups"    group_list   string required}
        }

    ############################################################
    ##   Procedure Export
    ############################################################
    foreach proc_list [dict values $help_message] {
        foreach {proc_name proc_message} $proc_list {
            namespace export $proc_name
        }
    }

    namespace export help highlight_cell_group
    namespace ensemble create
}
