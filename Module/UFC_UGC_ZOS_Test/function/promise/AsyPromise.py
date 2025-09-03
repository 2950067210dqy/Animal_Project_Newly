import asyncio

class AsyncPromise:
    def __init__(self, coro=None):
        self._loop = asyncio.get_event_loop()
        self._future = asyncio.Future()
        if coro:
            asyncio.ensure_future(coro).add_done_callback(self._complete)

    def _complete(self, fut):
        if fut.cancelled():
            self._future.cancel()
        else:
            exc = fut.exception()
            if exc is not None:
                self._future.set_exception(exc)
            else:
                self._future.set_result(fut.result())

    async def _then(self, on_fulfilled=None, on_rejected=None):
        try:
            r = await self._future
            if on_fulfilled:
                return on_fulfilled(r)
            return r
        except Exception as e:
            if on_rejected:
                return on_rejected(e)
            raise

    def then(self, on_fulfilled=None, on_rejected=None):
        return AsyncPromise(self._wrap(self._future, on_fulfilled, on_rejected))

    async def _wrap(self, fut, on_fulfilled, on_rejected):
        try:
            res = await fut
            if on_fulfilled:
                return on_fulfilled(res)
            return res
        except Exception as e:
            if on_rejected:
                return on_rejected(e)
            raise

    def catch(self, on_rejected):
        return self.then(None, on_rejected)

def sleep_promise(ms):
    async def _cor():
        await asyncio.sleep(ms / 1000.0)
        return ms
    return AsyncPromise(_cor())