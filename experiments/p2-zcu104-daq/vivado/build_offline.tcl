# Full Vivado 2025.2 only. Prepared entry; not executed in this environment yet.
# Usage: vivado -mode batch -source build_offline.tcl -tclargs NEW_PROJECT_DIR ?JOBS?
# Keep launcher logs/current directory separate and new as well.
# No reset_run, deletion, forced overwrite, bitstream, or hardware commands.
# Vendor internal temporary-file cleanup is not controlled by this script.
set entry_dir [file dirname [file normalize [info script]]]
if {$argc < 1 || $argc > 2} {
    error "Expected a new project directory and optional positive job count."
}
set build_dir [file normalize [lindex $argv 0]]
set jobs 2
if {$argc == 2} {
    set jobs [lindex $argv 1]
}
if {![string is integer -strict $jobs] || $jobs < 1} {
    error "JOBS must be a positive integer."
}
if {[file exists $build_dir]} {
    error "Output already exists: $build_dir. Choose a new directory."
}
source [file join $entry_dir create_project.tcl]

set report_dir [file join $build_dir reports]
file mkdir $report_dir
set version_file [open [file join $report_dir tool_version.txt] {WRONLY CREAT EXCL}]
puts $version_file [version]
close $version_file

# wait_on_runs alone does not establish success: preserve the actual run state.
proc wait_for_completion {run_name report_dir} {
    wait_on_runs $run_name
    set run [get_runs $run_name]
    set status [get_property STATUS $run]
    set progress [get_property PROGRESS $run]
    set f [open [file join $report_dir [format "%s_status.txt" $run_name]] {WRONLY CREAT EXCL}]
    puts $f "STATUS=$status\nPROGRESS=$progress"
    close $f
    if {$progress ne "100%" || ![string match "*Complete*" $status]} {
        error "$run_name did not complete: $status ($progress); all output retained."
    }
}

launch_runs synth_1 -jobs $jobs
wait_for_completion synth_1 $report_dir
open_run synth_1
report_utilization -file [file join $report_dir synth_utilization.rpt]
report_timing_summary -delay_type min_max -report_unconstrained \
    -check_timing_verbose -file [file join $report_dir synth_timing.rpt]
close_design

launch_runs impl_1 -to_step route_design -jobs $jobs
wait_for_completion impl_1 $report_dir
open_run impl_1
report_route_status -file [file join $report_dir route_status.rpt]
report_utilization -file [file join $report_dir route_utilization.rpt]
report_clocks -file [file join $report_dir clocks.rpt]
report_timing_summary -delay_type min_max -report_unconstrained \
    -check_timing_verbose -warn_on_violation -file [file join $report_dir route_timing.rpt]
report_drc -file [file join $report_dir route_drc.rpt]
write_checkpoint [file join $build_dir daq_routed.dcp]
write_hw_platform -fixed [file join $build_dir daq_zcu104.xsa]
puts "Offline build completed. Review timing, unconstrained paths and DRC reports."
puts "XSA export is not a timing-pass verdict, BSP compilation, bitstream or board validation."
