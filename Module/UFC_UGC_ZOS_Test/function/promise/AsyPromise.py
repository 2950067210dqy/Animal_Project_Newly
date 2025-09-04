
class AsyPromise:
    PENDING = 'pending'
    RESOLVED = 'resolved'
    REJECTED = 'rejected'

    def __init__(self, executor=None,**kwargs):
        self._state = AsyPromise.PENDING
        self._value = None
        self._reason = None
        self._on_fulfilled = []
        self._on_rejected = []
        if executor:
            try:
                executor(self.resolve, self.reject,**kwargs)
            except Exception as e:
                self.reject(e)

    def then(self, on_fulfilled=None, on_rejected=None):
        def _wrap_on_fulfilled(value):
            if on_fulfilled:
                return on_fulfilled(value)
            return value

        def _wrap_on_rejected(reason):
            if on_rejected:
                return on_rejected(reason)
            raise reason

        if self._state == AsyPromise.RESOLVED:
            return AsyPromise(lambda resolve, reject: resolve(_wrap_on_fulfilled(self._value)))
        if self._state == AsyPromise.REJECTED:
            return AsyPromise(lambda resolve, reject: reject(_wrap_on_rejected(self._reason)))

        nxt = AsyPromise()
        self._on_fulfilled.append(lambda v: self._propagate(nxt, _wrap_on_fulfilled, v))
        self._on_rejected.append(lambda e: self._propagate(nxt, _wrap_on_rejected, e))
        return nxt

    def catch(self, on_rejected):
        return self.then(None, on_rejected)

    def _propagate(self, nxt, fn, arg):
        try:
            res = fn(arg)
            if isinstance(res, AsyPromise):
                res.then(nxt.resolve, nxt.reject)
            else:
                nxt.resolve(res)
        except Exception as e:
            nxt.reject(e)

    def resolve(self, value=None):
        if self._state != AsyPromise.PENDING:
            return
        self._state = AsyPromise.RESOLVED
        self._value = value
        for cb in self._on_fulfilled:
            cb(value)

    def reject(self, reason=None):
        if self._state != AsyPromise.PENDING:
            return
        self._state = AsyPromise.REJECTED
        self._reason = reason
        for cb in self._on_rejected:
            cb(reason)
def async_task(resolve, reject):
    # 模拟异步
    import threading, time
    def work():
        time.sleep(1)
        if True:
            resolve("结果")
        else:
            reject("错误")
    threading.Thread(target=work).start()
def main1(result):
    print(result)
    p = AsyPromise(async_task).then(main1).catch(lambda e: print(f"{e}"))
    pass
if __name__ == '__main__':
    p = AsyPromise(async_task).then(main1).catch(lambda e: print(f"{e}"))
