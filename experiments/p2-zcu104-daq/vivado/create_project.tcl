# Run with full Vivado, from the experiment directory.
# This entry creates a project/BD and generated wrapper; it does not synthesize,
# implement, export a bitstream, connect to hardware, or program a board.
set script_dir [file dirname [file normalize [info script]]]
set project_root [file dirname $script_dir]
set build_dir [file join $project_root build vivado_zcu104]

# AMD XilinxBoardStore 2025.2: boards/Xilinx/zcu104/1.1/board.xml.
create_project daq_zcu104 $build_dir -part xczu7ev-ffvc1156-2-e
set_property board_part xilinx.com:zcu104:part0:1.1 [current_project]
set_property target_language Verilog [current_project]
add_files [list \
    [file join $project_root rtl axis_pattern_source.v] \
    [file join $project_root rtl axis_sync_fifo.v] \
    [file join $project_root rtl daq_stream_top.v] \
    [file join $project_root rtl daq_axi_lite.v]]
update_compile_order -fileset sources_1
source [file join $script_dir create_bd.tcl]

set bd_file [get_files */daq_bd.bd]
generate_target all $bd_file
set wrapper_files [make_wrapper -files $bd_file -top]
add_files -norecurse $wrapper_files
set_property top daq_bd_wrapper [current_fileset]
update_compile_order -fileset sources_1
write_bd_tcl [file join $build_dir daq_bd_export.tcl]
source [file join $script_dir export_addresses.tcl]
puts "Project and BD created. Synthesis, timing, BSP and hardware validation remain separate steps."
