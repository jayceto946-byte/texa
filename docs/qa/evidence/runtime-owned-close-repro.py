"""Offline fault injection: no models, network, or product data."""
import asyncio

from backend.services.owned_stream import OwnedStreamingResponse


class Producer:
    def __init__(self):
        self.close_calls = 0

    def __iter__(self):
        return iter(())

    def close(self):
        self.close_calls += 1


async def main():
    normal = Producer()
    response = OwnedStreamingResponse(normal)
    await response.aclose()
    await response.aclose()
    assert normal.close_calls == 1
    print('PASS normal repeated close: producer.close called once')

    failed = Producer()
    def fail_fence():
        raise OSError('injected task checkpoint write failure')

    response = OwnedStreamingResponse(failed, on_close=fail_fence)
    try:
        await response.aclose()
    except OSError as exc:
        print(f'Observed first close exception: {exc}')
    else:
        raise AssertionError('injected failure must be raised')
    await response.aclose()
    assert response.closed is True and failed.close_calls == 0
    print('REPRODUCED R1: producer.close calls=0 after two aclose calls; response.closed=True')


asyncio.run(main())
