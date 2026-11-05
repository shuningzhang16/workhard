# Intended for full Vivado 2025.2 with the official ZCU104 board definition.
# NOT yet executed in Vivado: local installation is Lab Edition only.
# References and selected values: vivado/README.md.
create_bd_design daq_bd

set ps [create_bd_cell -type ip -vlnv xilinx.com:ip:zynq_ultra_ps_e:3.5 ps]
apply_bd_automation -rule xilinx.com:bd_rule:zynq_ultra_ps_e \
    -config {apply_board_preset "1"} $ps
# DDR and MIO come from the official ZCU104 preset, not copied numeric values.
# HPM0_LPD controls DMA; HP0_FPD receives DMA writes to the PS memory subsystem.
set_property -dict [list \
    CONFIG.PSU__USE__M_AXI_GP0 {0} \
    CONFIG.PSU__USE__M_AXI_GP1 {0} \
    CONFIG.PSU__USE__M_AXI_GP2 {1} \
    CONFIG.PSU__USE__S_AXI_GP2 {1} \
    CONFIG.PSU__USE__IRQ0 {0} \
    CONFIG.PSU__FPGA_PL0_ENABLE {1} \
    CONFIG.PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ {100}] $ps

set stream [create_bd_cell -type module -reference daq_axi_lite stream]
set_property -dict [list CONFIG.FRAME_WORDS {7} CONFIG.FIFO_DEPTH {3}] $stream

set dma [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_dma:7.1 dma]
# Direct-register mode, S2MM only. 32-bit data path and aligned buffers; no DRE.
set_property -dict [list \
    CONFIG.c_include_sg {0} \
    CONFIG.c_micro_dma {0} \
    CONFIG.c_include_mm2s {0} \
    CONFIG.c_include_s2mm {1} \
    CONFIG.c_sg_include_stscntrl_strm {0} \
    CONFIG.c_s_axis_s2mm_tdata_width {32} \
    CONFIG.c_m_axi_s2mm_data_width {32} \
    CONFIG.c_include_s2mm_dre {0} \
    CONFIG.c_s2mm_burst_size {16} \
    CONFIG.c_addr_width {64} \
    CONFIG.c_prmry_is_aclk_async {0}] $dma

foreach name {control memory} {
    set sc [create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 $name]
    set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {1} CONFIG.NUM_CLKS {1}] $sc
}
set_property CONFIG.NUM_MI {2} [get_bd_cells control]
connect_bd_intf_net [get_bd_intf_pins stream/M_AXIS] [get_bd_intf_pins dma/S_AXIS_S2MM]
connect_bd_intf_net [get_bd_intf_pins ps/M_AXI_HPM0_LPD] [get_bd_intf_pins control/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins control/M00_AXI] [get_bd_intf_pins dma/S_AXI_LITE]
connect_bd_intf_net [get_bd_intf_pins control/M01_AXI] [get_bd_intf_pins stream/S_AXI]
connect_bd_intf_net [get_bd_intf_pins dma/M_AXI_S2MM] [get_bd_intf_pins memory/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins memory/M00_AXI] [get_bd_intf_pins ps/S_AXI_HP0_FPD]

set reset [create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 reset]
set_property -dict [list CONFIG.C_EXT_RESET_HIGH {0} CONFIG.C_AUX_RESET_HIGH {1}] $reset
set zero [create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 zero]
set one [create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 one]
set_property -dict [list CONFIG.CONST_WIDTH {1} CONFIG.CONST_VAL {0}] $zero
set_property -dict [list CONFIG.CONST_WIDTH {1} CONFIG.CONST_VAL {1}] $one
connect_bd_net [get_bd_pins zero/dout] [get_bd_pins reset/aux_reset_in] [get_bd_pins reset/mb_debug_sys_rst]
connect_bd_net [get_bd_pins one/dout] [get_bd_pins reset/dcm_locked]
connect_bd_net [get_bd_pins ps/pl_resetn0] [get_bd_pins reset/ext_reset_in]

# One PL clock domain. 100 MHz is a requested setting, not a timing result.
connect_bd_net [get_bd_pins ps/pl_clk0] \
    [get_bd_pins stream/aclk] [get_bd_pins dma/s_axi_lite_aclk] \
    [get_bd_pins dma/m_axi_s2mm_aclk] [get_bd_pins control/aclk] \
    [get_bd_pins memory/aclk] [get_bd_pins reset/slowest_sync_clk] \
    [get_bd_pins ps/maxihpm0_lpd_aclk] [get_bd_pins ps/saxihp0_fpd_aclk]
connect_bd_net [get_bd_pins reset/peripheral_aresetn] \
    [get_bd_pins dma/axi_resetn] [get_bd_pins stream/aresetn]
# Keep AXI-Lite alive during DMA reset. Only acquisition state/source/FIFO reset.
# Software observes STATUS.stream_reset, then STARTs only after it is released.
connect_bd_net [get_bd_pins dma/s2mm_prmry_reset_out_n] [get_bd_pins stream/stream_resetn]
connect_bd_net [get_bd_pins reset/interconnect_aresetn] \
    [get_bd_pins control/aresetn] [get_bd_pins memory/aresetn]

# Polling is intended. DMA interrupt output is deliberately not connected.
# Let Vivado derive reachable address segments; software addresses require the
# validated/generated hardware handoff, not constants from this draft script.
assign_bd_address
validate_bd_design
save_bd_design
