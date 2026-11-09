"""Request-local, best-effort stage notifications over the existing service events."""

import asyncio
import time
from contextlib import asynccontextmanager
from contextlib import suppress

STAGES = {
    "operation_started": "Request admitted", "discovery_completed": "Workspace inspected",
    "architecture_started": "Designing architecture", "construction_started": "Building candidate",
    "verification_started": "Checking candidate", "application_started": "Applying approved candidate",
    "repair_started": "Repairing failed check", "original_turn_reconciled": "Reconciling original turn",
    "operation_finished": "Operation finished",
}


@asynccontextmanager
async def progress(service, ctx):
    loop = asyncio.get_running_loop()
    queue = asyncio.Queue(maxsize=32)
    counter = 0
    last = 0.0

    def receive(kind, *, run_id, **fields):
        nonlocal last
        if kind not in STAGES and time.monotonic() - last < 2:
            return
        if kind not in STAGES and kind != "runtime_event":
            return
        last = time.monotonic()
        def enqueue():
            if queue.full():
                queue.get_nowait()
            queue.put_nowait((fields.get("stage_sequence", 0), f"{run_id}: {STAGES.get(kind, 'Codex turn active')}"))
        loop.call_soon_threadsafe(enqueue)

    async def send():
        nonlocal counter
        while True:
            item = await queue.get()
            if item is None:
                return
            sequence, message = item
            counter = max(counter + 1, sequence)
            try:
                await asyncio.wait_for(ctx.report_progress(counter, message=message), timeout=1)
            except Exception:
                pass

    sender = asyncio.create_task(send())
    with service.observe(receive):
        try:
            yield
        finally:
            await asyncio.sleep(0)
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(None)
            try:
                await asyncio.wait_for(sender, timeout=2)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                sender.cancel()
                with suppress(asyncio.CancelledError):
                    await sender
