set timing_report_unconstrained_paths true

proc report_ip_boundary_timing { args } {
#{{{
    parse_proc_arguments -args $args argsp
    set gpmax "get_timing_path -delay max -pba ex -slack_less inf"
    set gpmin "get_timing_path -delay min -pba ex -slack_less inf"

    if {$::SCENARIO_MODE == "DMSA"} {
        set is_dmsa "true"
        if {![catch [current_design]]} {
            echo "## REPORT_IP_BOUND: DMSA load distributed design"
            load_distributed_design
        }
    } else {
        set is_dmsa "false"
    }

    if [info exists argsp(-out)] {
        if [file exists $argsp(-out)] {
            set date [clock format [clock seconds] -format "%y%m%d_%H%M"]
            file rename -force $argsp(-out) "${argsp(-out)}.bak_${date}"
        }
        file mkdir $argsp(-out)
    }

    set pin_list_max {}
    set pin_list_min {}

    foreach inst $argsp(-inst) {
        foreach {dir dir_tag} {"in" "I" "out" "O"} {
            set point_info [_get_through_point $is_dmsa $dir $inst]
            set total_pins [dict size $point_info]
            set pcol_len   [string length $total_pins]
            set pin_id     1

            dict for {pin clk_info} $point_info {
                lassign $clk_info is_clk clk_list
                echo [format "=== \[%${pcol_len}d/%${pcol_len}d\] %s:%s" $pin_id $total_pins $dir_tag $pin]
                echo "## REPORT_IP_BOUND: pin      = $pin"
                echo "## REPORT_IP_BOUND: is_clock = $is_clk"
                echo "## REPORT_IP_BOUND: clk_list = $clk_list"
                if {0 && $pin != "chip_top1/i_usb20phy/DATAIN0\[0\]"} { continue }   ;# only for debug

                set path_id 1
                set path_active "false"
                foreach clk $clk_list {
                    #echo "## REPORT_IP_BOUND: Get path cmd (lv1): \[$gpmax -from \[get_clocks * -f \"full_name==$clk\"\] -th $pin\]"
                    set path [eval $gpmax -from [get_clocks * -f "full_name==$clk"] -th $pin]
                    if [sizeof_col $path] {
                        set path_active "true"
                        lappend pin_list_max [_get_pin_info $pin_id $path_id $pin $dir_tag $is_clk $path]
                        if [info exists argsp(-out)] {
                            echo [format "\n=== \[%d/%d\] %s:%s\n" $pin_id $path_id $dir_tag $pin] >> ${argsp(-out)}/timing_path_max.rpt
                            report_timing $path >> ${argsp(-out)}/timing_path_max.rpt
                        }
                        incr path_id
                    }
                }
                if {!$path_active} {
                    #echo "## REPORT_IP_BOUND: Get path cmd (lv2): \[$gpmax -th $pin\]"
                    set path [eval $gpmax -th $pin]
                    if [sizeof_col $path] {
                        lappend pin_list_max [_get_pin_info $pin_id $path_id $pin $dir_tag $is_clk $path]
                        if [info exists argsp(-out)] {
                            echo [format "\n=== \[%d/%d\] %s:%s\n" $pin_id $path_id $dir_tag $pin] >> ${argsp(-out)}/timing_path_max.rpt
                            report_timing $path >> ${argsp(-out)}/timing_path_max.rpt
                        }
                    } else {
                        lappend pin_list_max [_get_pin_info $pin_id $path_id $pin $dir_tag $is_clk {}]
                    }
                }

                set path_id 1
                set path_active "false"
                foreach clk $clk_list {
                    #echo "## REPORT_IP_BOUND: Get path cmd (lv1): \[$gpmin -from \[get_clocks * -f \"full_name==$clk\"\] -th $pin]"
                    set path [eval $gpmin -from [get_clocks * -f "full_name==$clk"] -th $pin]
                    if [sizeof_col $path] {
                        set path_active "true"
                        lappend pin_list_min [_get_pin_info $pin_id $path_id $pin $dir_tag $is_clk $path]
                        if [info exists argsp(-out)] {
                            echo [format "\n=== \[%d/%d\] %s:%s\n" $pin_id $path_id $dir_tag $pin] >> ${argsp(-out)}/timing_path_min.rpt
                            report_timing $path >> ${argsp(-out)}/timing_path_min.rpt
                        }
                        incr path_id
                    }
                }
                if {!$path_active} {
                    #echo "## REPORT_IP_BOUND: Get path cmd (lv1): \[$gpmin -th $pin\]"
                    set path [eval $gpmin -th $pin]
                    if [sizeof_col $path] {
                        lappend pin_list_min [_get_pin_info $pin_id $path_id $pin $dir_tag $is_clk $path]
                        if [info exists argsp(-out)] {
                            echo [format "\n=== \[%d/%d\] %s:%s\n" $pin_id $path_id $dir_tag $pin] >> ${argsp(-out)}/timing_path_min.rpt
                            report_timing $path >> ${argsp(-out)}/timing_path_min.rpt
                        }
                    } else {
                        lappend pin_list_min [_get_pin_info $pin_id $path_id $pin $dir_tag $is_clk {}]
                    }
                }

                incr pin_id
            }
        }
    }

    echo "## MAX PIN LIST:"
    foreach pin_info $pin_list_max {
        echo [dict values $pin_info]
    }
    echo "## MIN PIN LIST:"
    foreach pin_info $pin_list_min {
        echo [dict values $pin_info]
    }

    if [info exists argsp(-ignore)] {
        set ignore_path_list $argsp(-ignore)
    } else {
        set ignore_path_list {}
    }

    lappend table_header [dict create \
        pid  "PID"                 \
        pin  "PinName"             \
        dlat "Latency"             \
        slk  "Slack"               \
        clk  "Dir:StartClk:EndClk" \
        pt   "Startpoint:Endpoint" \
    ]

    if [info exist argsp(-out)] {
        set outfid [open "${argsp(-out)}/ip_boundary_timing_max.sum" "w"]
    } else {
        set outfid stdout
    }
    puts $outfid "\n### MAX PIN LIST:\n"
    _print_table $outfid $table_header $pin_list_max $ignore_path_list
    if [info exist argsp(-out)] { close $outfid }

    if [info exist argsp(-out)] {
        set outfid [open "${argsp(-out)}/ip_boundary_timing_min.sum" "w"]
    } else {
        set outfid stdout
    }
    puts $outfid "\n### MIN PIN LIST:\n"
    _print_table $outfid $table_header $pin_list_min $ignore_path_list
    if [info exist argsp(-out)] { close $outfid }
#}}}
}

define_proc_attributes report_ip_boundary_timing -info "Report IP boundary tuiming" \
    -define_args { \
        {-inst   "Instance list"                                     list      string  required}
        {-ignore "Ignore path list"                                  list      string  optional}
        {-out    "Output report directory"                           directory string  optional}
        {-json   "Data dump for the 3rd party process (JSON format)" ""        boolean optional}
    }

proc _get_through_point { is_dmsa dir inst } {
#{{{
    if {$is_dmsa} {
        echo "set inst $inst" >  $::sh_launch_dir/flat.tmp
        echo "set dir  $dir"  >> $::sh_launch_dir/flat.tmp
        set prev_scen [current_scenario]
        current_scenario [index_col [current_scenario] 0]
        remote_execute {
            source $::sh_launch_dir/flat.tmp
            file delete -force $::sh_launch_dir/flat.tmp
            foreach_in_col pin [get_pins $inst/* -f "pin_direction == $dir"] {
                set clk_coll [get_attr -q $pin launch_clocks]
                #echo "## DEBUG: pin      = [get_obj $pin]"
                #echo "## DEBUG: clk_coll = [get_obj $clk_coll]"
                if [sizeof_col $clk_coll] {
                    if [get_attr $pin is_clock_network] {
                        set is_clk "true"
                    } else {
                        set is_clk "false"
                    }
                    echo "dict set point_info [get_obj $pin] {$is_clk {[get_obj $clk_coll]}}" >> $::sh_launch_dir/flat.tmp
                } else {
                    echo "dict set point_info [get_obj $pin] {false {}}" >> $::sh_launch_dir/flat.tmp
                }
            }
        }
        current_scenario $prev_scen
        source $::sh_launch_dir/flat.tmp
        file delete -force $::sh_launch_dir/flat.tmp
    } else {
        foreach_in_col pin [get_pins $inst/* -f "pin_direction == $dir"] {
            set clk_coll [get_attr -q $pin launch_clocks]
            if [sizeof_col $clk_coll] {
                if [get_attr $pin is_clock_network] {
                    set is_clk "true"
                } else {
                    set is_clk "false"
                }
                dict set point_info [get_obj $pin] [list $is_clk [get_obj $clk_coll]]
            } else {
                dict set point_info [get_obj $pin] {false {}}
            }
        }
    }

    return $point_info
#}}}
}

proc _get_pin_info { pin_id path_id pin dir_tag is_clk path_coll } {
#{{{
    set pin_info [dict create \
        pid  $pin_id  \
        ppid $path_id \
        pin  $pin     \
        dir  $dir_tag \
        clk  $is_clk  \
    ]

    if {[sizeof_col $path_coll]} {
        set itag ""
        set otag ""
        set dlat [get_attr -q $path_coll arrival]
        if [sizeof_col [filter $path_coll "defined(startpoint_input_delay_value)"]] {
            set itag "(i)"
            set dlat [expr $dlat - [get_attr $path_coll startpoint_input_delay_value]]
        }
        if [sizeof_col [filter $path_coll "defined(endpoint_output_delay_value)"]] {
            set otag "(i)"
        }

        dict set pin_info dlat $dlat
        dict set pin_info slk  [get_attr -q $path_coll slack]
        dict set pin_info ptcs "[get_attr -q $path_coll startpoint_clock.full_name]${itag}"
        dict set pin_info ptce "[get_attr -q $path_coll endpoint_clock.full_name]${otag}"
        dict set pin_info pts  [get_attr -q $path_coll startpoint.full_name]
        dict set pin_info pte  [get_attr -q $path_coll endpoint.full_name]
    } else {
        dict set pin_info dlat "NA"
    }

    return $pin_info
#}}}
}

proc _print_table { fid table_header pin_list ignore_path_list } {
#{{{
    ### Get table content
    foreach pin_info $pin_list {
        set pin  [dict get $pin_info pin]
        set dir  [dict get $pin_info dir]
        set dlat [dict get $pin_info dlat]

        if [dict get $pin_info clk] {
            set pin_type "C"
        } else {
            set pin_type "D"
        }

        if {$dlat == "NA"} {
            set clk "[dict get $pin_info dir]:${pin_type}:NA:NA"
        } else {
            set clk "[dict get $pin_info dir]:${pin_type}:[dict get $pin_info ptcs]:[dict get $pin_info ptce]"
        }
        set path "$pin:$clk"

        set is_ignore "false"
        for {set i 0} {$i < [llength $ignore_path_list]} {incr i} {
            if {$path == [lindex $ignore_path_list $i]} {
                set ignore_path_list [lreplace $ignore_path_list $i $i]
                set is_ignore "true"
                break
            }
        }
        if {$is_ignore} { continue }

        if {$dlat == "NA"} {
            lappend table_content [dict create \
                pid  "[dict get $pin_info pid]/[dict get $pin_info ppid]" \
                pin  $pin \
                dlat "NA" \
                slk  "NA" \
                clk  $clk \
                pt   "NA:NA" \
            ]
        } else {
            lappend table_content [dict create \
                pid  "[dict get $pin_info pid]/[dict get $pin_info ppid]" \
                pin  $pin \
                dlat [format "%8.4f" $dlat] \
                slk  [format "%8.4f" [dict get $pin_info slk]] \
                clk  $clk \
                pt   "[dict get $pin_info pts]:[dict get $pin_info pte]" \
            ]
        }
    }

    ### Get column length
    array set col_len [list pid 0 pin 0 clk 0 pt 0]
    foreach row_data [concat $table_header $table_content] {
        set pid_len [string length [dict get $row_data pid]]
        if {$pid_len > $col_len(pid)} { set col_len(pid) $pid_len }
        set pin_len [string length [dict get $row_data pin]]
        if {$pin_len > $col_len(pin)} { set col_len(pin) $pin_len }
        set clk_len [string length [dict get $row_data clk]]
        if {$clk_len > $col_len(clk)} { set col_len(clk) $clk_len }
        set pt_len  [string length [dict get $row_data pt]]
        if {$pt_len  > $col_len(pt) } { set col_len(pt)  $pt_len  }
    }

    ### Create table dividers
    set row_len [expr \
        $col_len(pid) \
        + $col_len(pin) + 2 \
        + 8 + 2 \
        + 8 + 2 \
        + $col_len(clk) + 2 \
        + $col_len(pt) + 2 \
    ]
    set div  [string repeat "=" $row_len]
    set fstr "%-${col_len(pid)}s  %-${col_len(pin)}s  %8s  %8s  %-${col_len(clk)}s  %-${col_len(pt)}s"

    ### Print table header
    puts $fid ""
    foreach row_data $table_header {
        puts $fid [format $fstr \
            [dict get $row_data pid ] \
            [dict get $row_data pin ] \
            [dict get $row_data dlat] \
            [dict get $row_data slk ] \
            [dict get $row_data clk ] \
            [dict get $row_data pt  ] \
        ]
    }
    puts $fid $div

    ### Print table content
    foreach row_data $table_content {
        puts $fid [format $fstr \
            [dict get $row_data pid ] \
            [dict get $row_data pin ] \
            [dict get $row_data dlat] \
            [dict get $row_data slk ] \
            [dict get $row_data clk ] \
            [dict get $row_data pt  ] \
        ]
    }
    puts $fid ""
#}}}
}

