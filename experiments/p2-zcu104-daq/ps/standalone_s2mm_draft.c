/* Integration draft only. Not included in host tests; not compiled against BSP.
 * Uses the unmodified local AMD driver API; no base address or DDR allocation.
 */
#include "standalone_s2mm_draft.h"
#include "xil_cache.h"
#include "xstatus.h"

static int reset_epoch(void *context, unsigned poll_limit)
{
    standalone_s2mm_context *c = context;
    if (c == NULL || c->dma == NULL || c->cpu_buffer == NULL ||
        c->allocation_bytes < S2MM_PACKET_BYTES || !c->dma->Initialized ||
        !c->dma->HasS2Mm || c->dma->HasMm2S || XAxiDma_HasSg(c->dma) ||
        c->dma->MicroDmaMode || c->dma->RxBdRing[0].DataWidth != 4 ||
        c->dma->RxBdRing[0].HasDRE || (c->dma_address & 3U) != 0)
        return -1;
    XAxiDma_Reset(c->dma);
    for (unsigned i = 0; i < poll_limit; ++i) {
        if (XAxiDma_ResetIsDone(c->dma)) {
            c->last_status = XAxiDma_ReadReg(c->dma->RegBase + XAXIDMA_RX_OFFSET,
                                           XAXIDMA_SR_OFFSET);
            if (!(c->last_status & XAXIDMA_HALTED_MASK) ||
                (c->last_status & (XAXIDMA_ERR_ALL_MASK | XAXIDMA_IRQ_ERROR_MASK)))
                return -1;
            XAxiDma_IntrDisable(c->dma, XAXIDMA_IRQ_ALL_MASK, XAXIDMA_DEVICE_TO_DMA);
            return 0;
        }
    }
    return -1;                    /* Do not touch or release the receive buffer. */
}

static void for_device(void *context)
{
    standalone_s2mm_context *c = context;
    Xil_DCacheFlushRange((UINTPTR)c->cpu_buffer, c->allocation_bytes);
}

static void for_cpu(void *context)
{
    standalone_s2mm_context *c = context;
    Xil_DCacheInvalidateRange((UINTPTR)c->cpu_buffer, c->allocation_bytes);
}

static int submit(void *context, size_t bytes)
{
    standalone_s2mm_context *c = context;
    c->last_status = XAxiDma_ReadReg(c->dma->RegBase + XAXIDMA_RX_OFFSET,
                                   XAXIDMA_SR_OFFSET);
    c->last_submit_result = XST_FAILURE;
    if (bytes != S2MM_PACKET_BYTES ||
        (c->last_status & (XAXIDMA_ERR_ALL_MASK | XAXIDMA_IRQ_ERROR_MASK)))
        return -1;
    /* Clear only old completion, not error evidence. SimpleTransfer writes the
     * destination (and MSB as needed), RS, then LENGTH last to start this packet. */
    XAxiDma_IntrAckIrq(c->dma, XAXIDMA_IRQ_IOC_MASK, XAXIDMA_DEVICE_TO_DMA);
    c->last_submit_result = XAxiDma_SimpleTransfer(c->dma, c->dma_address,
                                                 (u32)bytes, XAXIDMA_DEVICE_TO_DMA);
    return c->last_submit_result == XST_SUCCESS ? 0 : -1;
}

static s2mm_event poll_once(void *context)
{
    standalone_s2mm_context *c = context;
    UINTPTR base = c->dma->RegBase + XAXIDMA_RX_OFFSET;
    c->last_status = XAxiDma_ReadReg(base, XAXIDMA_SR_OFFSET);
    s2mm_event event = {.raw_status = c->last_status};
    event.error = (c->last_status & (XAXIDMA_ERR_ALL_MASK | XAXIDMA_IRQ_ERROR_MASK)) != 0;
    event.done = (c->last_status & XAXIDMA_IRQ_IOC_MASK) != 0 &&
                 (c->last_status & XAXIDMA_IDLE_MASK) != 0;
    if (event.done && !event.error)
        event.actual_bytes = XAxiDma_ReadReg(base, XAXIDMA_BUFFLEN_OFFSET);
    return event;                 /* Payload cache operations belong to for_cpu. */
}

const s2mm_ops standalone_s2mm_ops = {reset_epoch, for_device, for_cpu, submit, poll_once};
