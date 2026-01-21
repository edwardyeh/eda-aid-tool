set timing_report_unconstrained_paths true

### === Private Function

### user procedure list (user_help_des)  {{{
set USER_HELP_DES [dict create]
echo "Information: Type 'user_help_des' to show user procedure list."

proc user_help_des { args } {
    global USER_HELP_DES
    parse_proc_arguments -args $args argsp

    set gid_len [string length [dict size $USER_HELP_DES]]

    echo ""
    ## only show group title
    if {[info exists argsp(-only_group)]} {
        set gid 0
        foreach {gname proc_list} $USER_HELP_DES {
            echo [format "=== (%${gid_len}d %s" $gid $gname]
            incr gid
        }
        echo ""
        return
    }

    ## get column length
    set gid     0
    set col_len 0
    foreach {gname proc_list} $USER_HELP_DES {
        if {[info exists argsp(-group)] && $argsp(-group) != $gid} { continue }
        foreach {fname comment} $proc_list {
            set newlen [string length $fname]
            if {$newlen > $col_len} { set col_len $newlen }
        }
        incr gid
    }

    ## show the procedure list
    set gid 0
    foreach {gname proc_list} $USER_HELP_DES {
        if {[info exists argsp(-group)] && $argsp(-group) != $gid} { continue }
        echo [format "=== (%${gid_len}d) %s\n" $gid $gname]
        foreach {fname comment} $proc_list {
            echo [format "  %-${col_len}s   %s" $fname $comment]
        }
        echo ""
        incr gid
    }
    echo ""
}

define_proc_attributes user_help_des -info "Show the user procedure list" \
    -define_args { \
        {-only_group "Only show group titles"                              ""  boolean optional}
        {-group      "Only show the user procedures of the specific group" gid int     optional}
    }
#}}}

### === Common Function

### explore design pads (explore_design_pads)  {{{
dict append USER_HELP_DES "Common Function" { explore_design_pads "Explore design PADs" }

proc explore_design_pads { args } {
    parse_proc_arguments -args $args argsp

    set PART_REGEXP "^(chip_top\\w+)/.+$"

    if {[info exists argsp(-top)]} {
        set PAD_FILTER "is_hierarchical==false && full_name=~chip_top*/i_ip*/u_*"
    } else {
        set PAD_FILTER "is_hierarchical==false && full_name=~i_ip*/u_*"
    }

    set PART_PAD_DICT [dict create]
    foreach_in_col port [get_ports * -quiet -filter "direction==inout"] {
        set pad_cell [get_cells -of [get_pins -of [get_nets -seg -of $port]] -filter $PAD_FILTER] 

        if {[sizeof_col $pad_cell] > 0} {
            if {[info exists argsp(-top)]} {
                regexp $PART_REGEXP [get_object_name $pad_cell] -> part_name
            } else {
                set part_name "(none)"
            }
            set port_name [get_object_name $port]
            dict set PART_PAD_DICT $part_name $port_name $pad_cell
        }
    }

    if {[info exists argsp(-print)]} {
        echo ""
        foreach part_name [lsort [dict keys $PART_PAD_DICT]] {
            set pad_dict [dict get $PART_PAD_DICT $part_name]
            echo "====== $part_name"
            echo [format "%-20s %-20s %-60s" "Port" "PadType" "Instance"]
            echo [string repeat "=" [expr 20 + 20 + 60]]
            foreach port_name [lsort [dict key $pad_dict]] {
                set pad_cell [dict get $pad_dict $port_name]
                echo [format "%-20s %-20s %-60s" \
                        $port_name \
                        [get_attr $pad_cell ref_name] \
                        [get_object_name $pad_cell] \
                     ]
            }
            echo "\n"
        }
    } else {
        return $PART_PAD_DICT
    }
}

define_proc_attributes explore_design_pads -info "Explore design PADs" \
    -define_args { \
        {-top   "Explore design from top" "" boolean optional}
        {-print "Show the result"         "" boolean optional}
    }
#}}}

### explore design module (explore_design_module)  {{{
dict append USER_HELP_DES "Common Function" { explore_design_module "Explore design module" }

proc explore_design_module { args } {
    parse_proc_arguments -args $args argsp

    set PART_REGEXP "^(chip_top\\w+)/.+$"
    set PART_FILTER "chip_top*"
    set MOD_FILTER  "chip_top*/i_chip_core*/i_core*/i_*"

    # format: {<regexp pattern> ... }
    if {[info exists argsp(-waive)]} {
        set waive_list $argsp(-waive)
    } else {
        set waive_list []
    }

    set mod_coll [get_cells -quiet $MOD_FILTER]

    set PART_MOD_DICT [dict create]
    foreach_in_col mod_cell $mod_coll {
        set mod_name [get_object_name $mod_cell]

        set is_waive 0
        foreach waive_pat $waive_list {
            if {[regexp "$waive_pat" $mod_name]} {
                set is_waive 1
                break
            }
        }

        if {!$is_waive} {
            if {[info exists argsp(-top)]} {
                regexp "$PART_REGEXP" $mod_name -> part_name
            } else {
                set part_name "(none)"
            }

            if {[dict exists $PART_MOD_DICT $part_name]} {
                set tmp_coll [dict get $PART_MOD_DICT $part_name]
                dict set PART_MOD_DICT $part_name [add_to_col $tmp_coll $mod_cell]
            } else {
                dict set PART_MOD_DICT $part_name $mod_cell
            }
        }
    }

    if {[info exists argsp(-print)]} {
        echo ""
        dict for {part_name mod_coll} $PART_MOD_DICT {
            echo "====== $part_name"
            echo [format "%-60s %-20s" "Instance" "Design"]
            echo [string repeat "=" [expr 60 + 20]]
            foreach_in_col mod_cell $mod_coll {
                echo [format "%-60s %-20s" [get_object_name $mod_cell] [get_attr $mod_cell ref_name]]
            }
            echo "\n"
        }
    } else {
        return $PART_MOD_DICT
    }
}

define_proc_attributes explore_design_module -info "Explore design module" \
    -define_args { \
        {-top   "Explore from top"          ""   boolean optional}
        {-waive "Waive constraint (regexp)" list list    optional}
        {-print "Show the result"           ""   boolean optional}
    }
#}}}

### explore design io (explore_design_io)  {{{
dict append USER_HELP_DES "Common Function" { explore_design_io "Explore design IO" }

proc explore_design_io { args } {
    parse_proc_arguments -args $args argsp

    set PART_REGEXP "^(chip_top\\w+)/.+$"
    set PART_FILTER "chip_top*"

    # format: { \
    #   group1 {tag11 regexp11 tag12 regexp12 ... } \
    #   group2 {tag21 regexp21 tag22 regexp22 ... } \
    #   ...
    # }
    if {[info exists argsp(-group)]} {
        set group_dict $argsp(-group)
    } else {
        set group_dict {}
    }

    set waive_coll {}
    if {[info exists argsp(-top)]} {
        if {[info exists argsp(-waive)]} {
            set waive_coll [get_pins -quiet $argsp(-waive)]
        }

        set io_dict [dict create]
        foreach_in_col part_cell [get_cells $PART_FILTER] {
            set pin_coll [remove_from_col [get_pins -of $part_cell] $waive_coll]
            dict set io_dict [get_object_name $part_cell] $pin_coll 
        }
    } else {
        if {[info exists argsp(-waive)]} {
            set waive_coll [get_ports -quiet $argsp(-waive)]
        }
        set port_coll [remove_from_col [get_ports * -filter "direction!=inout"] $waive_coll]
        set io_dict   [dict create "(none)" $port_coll]
    }

    set IO_GROUP_DICT [dict create]

    dict for {part_name io_coll} $io_dict {
        set part_dict [dict create "(none)" {}]

        foreach io_name [get_object_name $io_coll] {
            set gname "(none)"
            dict for {gname_tmp tag_dict} $group_dict {
                dict for {tname pat} $tag_dict {
                    if {[regexp $pat $io_name]} {
                        set gname $gname_tmp
                        dict lappend part_dict $gname $tname $io_name
                        break
                    }
                }

                if {$gname != "(none)"} {
                    break
                }
            }

            if {$gname == "(none)"} {
                dict lappend part_dict "(none)" $io_name
            }
        }

        dict set IO_GROUP_DICT $part_name $part_dict
    }

    if {[info exists argsp(-print)]} {
        echo ""
        dict for {part_name part_dict} $IO_GROUP_DICT {
            echo "====== IOGroup: $part_name"
            echo ""
            foreach gname [dict key $part_dict] {
                if {$gname != "(none)"} {
                    echo "### $gname"
                    foreach tname [dict key [dict get $part_dict $gname]] {
                        echo $tname
                    }
                    echo ""
                } else {
                    echo "### (none)"
                    foreach io_name [dict get $part_dict "(none)"] {
                        echo $io_name
                    }
                    echo ""
                }
            }
            echo ""
        }
    } else {
        return $IO_GROUP_DICT
    }
}

define_proc_attributes explore_design_io -info "Explore design IO" \
    -define_args { \
        {-top   "Explore from top"          ""         boolean optional}
        {-waive "Waive pin/port list"       waive_list list    optional}
        {-group "Group constraint (regexp)" group_dict list    optional}
        {-print "Show the result"           ""         boolean optional}
    }
#}}}

### create group bound (create_group_bound)  {{{
dict append USER_HELP_DES "Common Function" { create_group_bound "Create group bound" }

proc create_group_bound { args } {
    parse_proc_arguments -args $args argsp
}

define_proc_attributes create_group_bound -info "Create group bound" \
    -define_args { \
        { group_dict  "Group dictionary"                                 group_dict list    required}
        {-top         "Explore from top"                                 ""         boolean optional}
        {-part_filter "Custom filter to get the partition cell (regexp)" expression string  optional}
        {-print "Show the result (default: log type)"                    type       one_of_string \
            { optional value_help {values {"log" "prc"}} }}
    }
#}}}

### === Top

### === Partition

