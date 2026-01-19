
proc report_boundary_timing { args } {
#{{{
    parse_proc_arguments -args $args argsp
    set gpmax "get_timing_path -quiet -delay max -pba ex"
    set gpmin "get_timing_path -quiet -delay min -pba ex"

    if {![catch [current_design]]} {
        set is_dmsa "true"
        load_distributed_design
    } else {
        set is_dmsa "false"
    }

    lassign {{} {} 0} pin_list_max pin_list_min path_id

    foreach inst $argsp(-inst) {
        foreach {dir dir_tag} {"in" "I" "out" "O"} {
            dict for {pin clk_list} [_get_through_point $is_dmsa $dir $inst] {
                foreach {pin_list gpath} [list $pin_list_max $gpmax $pin_list_min $gpmin] {
                    set path_active "false"
                    foreach clk $clk_list {
                        set path [eval $gpath -from $clk -th $pin]
                        if {[sizeof_col $path]} {
                            set path_active "true"
                            lappend pin_list [_get_pin_info $path_id $pin $dir_tag $path]
                        }
                    }
                    if {!$path_active} {
                        set path [eval $gpath -th $pin]
                        if {[sizeof_col $path]} {
                            lappend pin_list [_get_pin_info $path_id $pin $dir_tag $path]
                        } else {
                            lappend pin_list [_get_pin_info $path_id $pin $dir_tag {}]
                        }
                    }
                    incr path_id
                }
            }
        }
    }

    lappend table_header [dict create \
        pin "PinName" \
        arr "Arrival" \
        slk "Slack" \
        clk "Dir:StartClk:EndClk" \
        pt  "Startpoint:Endpoint" \
    ]

    #if [info exist argsp(-rptfp)] {
    #    set rptfid [open $argsp(-rptfp) "w"]
    #} else {
    #    set rptfid stdout
    #}
    #_print_table $rptfid $table_header $pin_list
#}}}
}

define_proc_attributes report_ip_boundary_timing -info "Report IP boundary tuiming" \
    -define_args { \
        {-inst "Instance list"                         list     string required}
        {-out  "File path for report dump"             filepath string required}
        {-json "File path for data dump (JSON format)" filepath string optional}
    }

proc _get_through_point { is_dmsa dir inst } {
#{{{
    if {$is_dmsa} {
        echo "set inst $inst" >  $sh_launch_dir/flat.tmp
        echo "set dir  $dir"  >> $sh_launch_dir/flat.tmp
        set previous_session [current_session]
        current_session [index_col [current_session] 0]
        remote_execute {
            source $sh_launch_dir/flat.tmp
            file delete -force $sh_launch_dir/flat.tmp
            foreach_in_col pin [get_pins $inst/* -f "pin_direction == $dir"] {
                set clk_coll [get_attr -q $pin launch_clocks]
                if [sizeof_col $clk_coll] {
                    echo "dict set point_info [get_obj $pin] {[get_obj $clk_coll]}" >> $sh_launch_dir/flat.tmp
                } else {
                    echo "dict set point_info [get_obj $pin] {}" >> $sh_launch_dir/flat.tmp
                }
            }
        }
        current_session $previous_session
        source $sh_launch_dir/flat.tmp
        file delete -force $sh_launch_dir/flat.tmp
    } else {
        foreach_in_col pin [get_pins $inst/* -f "pin_direction == $dir"] {
            set clk_coll [get_attr -q $pin launch_clocks]
            if [sizeof_col $clk_coll] {
                dict set point_info [get_obj $pin] [get_obj $clk_coll]
            } else {
                dict set point_info [get_obj $pin] {}
            }
        }
    }

    return $point_info
#}}}
}

proc _get_pin_info { path_id pin dir_tag path_coll } {
#{{{
    set pin_info [dict create \
        pid $path_id \
        pin $pin \
        dir $dir_tag \
    ]

    if {[sizeof_col $path_coll]} {
        dict set pin_info arr  [get_attr -q $path_coll arrival]
        dict set pin_info slk  [get_attr -q $path_coll slack]
        dict set pin_info ptcs [get_attr -q $path_coll startpoint_clock]
        dict set pin_info ptce [get_attr -q $path_coll endpoint_clock]
        dict set pin_info pts  [get_attr -q $path_coll startpoint]
        dict set pin_info pte  [get_attr -q $path_coll endpoint]
    } else {
        dict set pin_info arr  "NA"
    }

    return $pin_info
#}}}
}

proc _print_table { fid table_header pin_list } {
#{{{
    ### Get table content
    foreach pin_info $pin_list {
        lappend table_content [dict create \
            pin [dict get $pin_info pin] \
            arr [dict get $pin_info arr] \
            slk [dict get $pin_info slk] \
            clk "" \
        ]
    }

    ### Get column length
    array set col_len [list pin 0 arr 0 clk 0 pt 0 ]



    foreach row_data [concat $header $table] {
        dict for {key value} $row_data {
            if {$key == "pid"} {
                continue
            } elseif {$key == "ptcs" || $key == "ptce"} {
                set key "ptc"
            } elseif {$key == "pts" || $key == "pte"} {
                set key "pt"
            }
            set new_len [string length $value]
            if {$new_len > $col_len($key)} {
                set col_len($key) $new_len
            }
        }
    }

    ### Create table dividers
    lassign {"=" "+"} div1 div2
    foreach key [array names col_len] {
        append div1 [string repeat "=" [expr $col_len($key) + 3]]
        append div2 [string repeat "=" [expr $col_len($key) + 2]] "+"
    }

    ### Print table header
    puts $fid $div1
    foreach row_data $header {
        set row_str "|"
        dict for {key value} $row_data {
            if {$key != "pid"} {
                append row_str [format " %${col_len($key)}s |" $value]
            }
        }
        puts $fid $row_str
    }

    ### Print table content
    set prv_pid -1
    foreach row_data $table {
        lassign {"|" "|"} row_str1 row_str2
        dict for {key value} $row_data {
            if {$key == "pid"} {
                if {$value == $prv_pid} {
                    puts $fid $div2
                } else {
                    puts $fid $div1
                }
                set prv_pid $value
            } elseif {$key == "ptcs"} {
                append row_str1 [format " %${col_len(ptc)}s |" $value]
            } elseif {$key == "ptce"} {
                append row_str2 [format " %${col_len(ptc)}s |" $value]
            } elseif {$key == "pts"} {
                append row_str1 [format " %${col_len(pt)}s |" $value]
            } elseif {$key == "pte"} {
                append row_str2 [format " %${col_len(pt)}s |" $value]
            } else {
                append row_str1 [format " %${col_len($key)}s |" $value]
                append row_str2 [format " %${col_len($key)}s |" ""]
            }
        }
        puts $fid $row_str1
        puts $fid $row_str2
    }
    puts $fid $div1
#}}}
}

#proc _print_table { fid header table } {
##{{{
#    ### Get column length
#    array set col_len {
#        pin 0 dir 0 freq 0 arr 0 slk 0 ptc 0 pt 0
#    }
#    foreach row_data [concat $header $table] {
#        dict for {key value} $row_data {
#            if {$key == "pid"} {
#                continue
#            } elseif {$key == "ptcs" || $key == "ptce"} {
#                set key "ptc"
#            } elseif {$key == "pts" || $key == "pte"} {
#                set key "pt"
#            }
#            set new_len [string length $value]
#            if {$new_len > $col_len($key)} {
#                set col_len($key) $new_len
#            }
#        }
#    }

#    ### Create table dividers
#    lassign {"=" "+"} div1 div2
#    foreach key [array names col_len] {
#        append div1 [string repeat "=" [expr $col_len($key) + 3]]
#        append div2 [string repeat "=" [expr $col_len($key) + 2]] "+"
#    }

#    ### Print table header
#    puts $fid $div1
#    foreach row_data $header {
#        set row_str "|"
#        dict for {key value} $row_data {
#            if {$key != "pid"} {
#                append row_str [format " %${col_len($key)}s |" $value]
#            }
#        }
#        puts $fid $row_str
#    }

#    ### Print table content
#    set prv_pid -1
#    foreach row_data $table {
#        lassign {"|" "|"} row_str1 row_str2
#        dict for {key value} $row_data {
#            if {$key == "pid"} {
#                if {$value == $prv_pid} {
#                    puts $fid $div2
#                } else {
#                    puts $fid $div1
#                }
#                set prv_pid $value
#            } elseif {$key == "ptcs"} {
#                append row_str1 [format " %${col_len(ptc)}s |" $value]
#            } elseif {$key == "ptce"} {
#                append row_str2 [format " %${col_len(ptc)}s |" $value]
#            } elseif {$key == "pts"} {
#                append row_str1 [format " %${col_len(pt)}s |" $value]
#            } elseif {$key == "pte"} {
#                append row_str2 [format " %${col_len(pt)}s |" $value]
#            } else {
#                append row_str1 [format " %${col_len($key)}s |" $value]
#                append row_str2 [format " %${col_len($key)}s |" ""]
#            }
#        }
#        puts $fid $row_str1
#        puts $fid $row_str2
#    }
#    puts $fid $div1
##}}}
#}
