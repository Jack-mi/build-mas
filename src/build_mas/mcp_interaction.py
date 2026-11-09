"""Protocol-era confirmation and one bounded private login attempt per server."""

import asyncio
import json
import time

from mcp.types import ElicitRequest, ElicitRequestFormParams, ElicitRequestURLParams, ElicitResult, InputRequiredResult

from .contracts import Budget
from .errors import BuildMasError
from .store import identifier


def capabilities(ctx, allow_apply):
    try:
        client = ctx.request_context.session.client_capabilities
        elicitation = client.elicitation if client else None
        mode = lambda name: getattr(elicitation, name, None) is not None if client else None
        meta = ctx.request_context.meta
        has_progress = getattr(meta, "progress_token", None) is not None
    except (ValueError, AttributeError):
        mode = lambda _name: None
        has_progress = None
    return {"apply_exposed": allow_apply, "form_elicitation": mode("form"), "url_elicitation": mode("url"), "progress": has_progress, "protocol_version": ctx.protocol_version, "human_approval_verified": False}


def modern(ctx):
    return bool(ctx.protocol_version and ctx.protocol_version >= "2026-07-28")


def continuation(ctx, expected):
    if not ctx.request_state:
        if ctx.input_responses:
            raise BuildMasError("invalid_review_state", "Answers require an authenticated request state")
        return None
    try:
        state = json.loads(ctx.request_state)
        if state != expected or set(ctx.input_responses or {}) != {"confirm"}:
            raise ValueError
        return ElicitResult.model_validate(ctx.input_responses["confirm"])
    except (ValueError, TypeError, KeyError):
        raise BuildMasError("invalid_review_state", "Confirmation is stale or belongs to another page/request") from None


def question(params, state):
    # The SDK seals this plaintext and authenticates the client echo at the wire boundary.
    return InputRequiredResult(input_requests={"confirm": ElicitRequest(params=params)}, request_state=json.dumps(state, sort_keys=True))


def proposal_question(record, page, form):
    state = {"request": record["id"], "review": record["review_id"], "hash": record["proposal_hash"], "revision": record["spec_revision"], "snapshot": record["snapshot"], "offset": record["offset"], "expires": record["expires_at"]}
    message = f"Review exact proposal {record['proposal_id']} at offset {record['offset']}. "
    message += "Accept this page to continue; no files are applied yet.\n" if page["next_offset"] is not None else "Approve this exact proposal? This permits its declared live SDK check in isolation before applying files.\n"
    return ElicitRequestFormParams(message=message + page["content"], requested_schema=form.model_json_schema()), state


class LoginInteraction:
    def __init__(self, service):
        self.service = service
        self.pending = None

    async def close(self):
        pending, self.pending = self.pending, None
        if pending is not None:
            if pending["expiry_task"] is not asyncio.current_task():
                pending["expiry_task"].cancel()
            if pending.get("waiting") and pending.get("worker") is not asyncio.current_task():
                pending["worker"].cancel()
                try:
                    await pending["worker"]
                except asyncio.CancelledError:
                    pass
                return
            try:
                await pending["runtime"].cancel_login(pending["attempt"])
            finally:
                pending["lock"].__exit__(None, None, None)

    async def login(self, ctx, *, device=False):
        if capabilities(ctx, False)["url_elicitation"] is False:
            raise BuildMasError("login_channel_unavailable", "This client cannot present user-only URL authentication")
        if not modern(ctx):
            async def authorize(instruction):
                message = "Sign in outside chat; never send credentials to the agent."
                if device:
                    message += " Enter this user-only code: " + instruction["user_code"]
                try:
                    answer = await ctx.elicit_url(message, instruction.get("auth_url") or instruction["verification_url"], identifier("login"))
                except Exception as exc:
                    raise BuildMasError("login_channel_unavailable", "Client cannot display secure URL authentication") from exc
                if getattr(answer.action, "value", answer.action) != "accept":
                    raise BuildMasError("permission_denied", "User did not accept authentication")
            with self.service.store.lock("builder_login"):
                async with self.service.runtime(identifier("login"), Budget(timeout_seconds=300)) as runtime:
                    return await runtime.login(device=device, authorize=authorize)
        if self.pending is None:
            if ctx.request_state or ctx.input_responses:
                raise BuildMasError("login_expired", "Login attempt ended or server restarted; start a new login")
            lock = self.service.store.lock("builder_login")
            lock.__enter__()
            runtime = self.service.runtime(identifier("login"), Budget(timeout_seconds=300))
            try:
                attempt = await runtime.start_login(device=device)
            except BaseException:
                lock.__exit__(None, None, None)
                raise
            remaining = max(0, attempt.get("expires", time.monotonic() + 300) - time.monotonic())
            pending = {"id": identifier("login"), "device": device, "runtime": runtime, "attempt": attempt, "lock": lock, "expires": time.time() + remaining}
            async def expire():
                await asyncio.sleep(remaining)
                if self.pending is pending:
                    await self.close()
            pending["expiry_task"] = asyncio.create_task(expire())
            self.pending = pending
        pending = self.pending
        if device != pending["device"]:
            raise BuildMasError("login_pending", "Another login attempt owns the private runtime")
        state = {"login_id": pending["id"], "device": device, "expires": pending["expires"]}
        answer = continuation(ctx, state)
        if answer is None:
            if pending.get("waiting"):
                raise BuildMasError("login_pending", "An accepted login is already waiting for its user")
            instruction = pending["attempt"]["instruction"]
            message = "Sign in outside model context. Never send credentials to the agent."
            if device:
                message += " Enter this user-only code: " + instruction["user_code"]
            return question(ElicitRequestURLParams(message=message, url=instruction.get("auth_url") or instruction["verification_url"], elicitation_id=pending["id"]), state)
        if answer.action != "accept":
            await self.close()
            raise BuildMasError("permission_denied", "User did not accept authentication")
        if pending.get("waiting"):
            raise BuildMasError("login_pending", "An accepted login is already waiting for its user")
        pending["waiting"] = True
        pending["worker"] = asyncio.current_task()
        pending["expiry_task"].cancel()
        try:
            return await pending["runtime"].finish_login(pending["attempt"])
        finally:
            self.pending = None
            pending["lock"].__exit__(None, None, None)


async def apply(service, request, ctx, form, *, review_owner=None):
    record = service.public_apply(request.model_dump(), review_owner=review_owner)
    cached = service.public_apply_result(record)
    if cached:
        return cached
    try:
        if capabilities(ctx, True)["form_elicitation"] is False:
            raise BuildMasError("approval_channel_unavailable", "Client has no supported human form confirmation; target unchanged")
        while True:
            record = service.store.read("apply_requests", record["id"])
            if record["phase"] != "reviewing":
                return service.public_apply_result(record)
            page = service.review_page(record)
            params, state = proposal_question(record, page, form)
            if modern(ctx):
                answer = continuation(ctx, state)
                if answer is None:
                    return question(params, state)
                accepted = answer.action == "accept" and (answer.content or {}).get("approve") is True
            else:
                try:
                    answer = await ctx.elicit(params.message, form)
                except Exception as exc:
                    raise BuildMasError("approval_channel_unavailable", "Client cannot present human confirmation; target unchanged") from exc
                accepted = getattr(answer.action, "value", answer.action) == "accept" and answer.data is not None and answer.data.approve is True
            record = service.finish_public_review(record, accepted=accepted, next_offset=page["next_offset"])
            if not accepted:
                return service.public_apply_result(record)
            if record["phase"] == "executing":
                return await service.apply({**record["approved"], "idempotency_key": record["key"]}, admitted_run_id=record["run_id"])
            if modern(ctx):
                page = service.review_page(record)
                return question(*proposal_question(record, page, form))
    except BuildMasError as exc:
        service.fail_public_apply(record, exc)
        run = service.store.read("runs", record["run_id"])
        return {**run.get("result", {}), "run_id": record["run_id"], "status": "approval_required" if exc.code == "approval_channel_unavailable" else "failed", "error": exc.as_dict()}
    except asyncio.CancelledError:
        service.fail_public_apply(record, BuildMasError("operation_cancelled", "Review cancelled; target unchanged"))
        raise
