import unittest
from unittest.mock import AsyncMock

from app.services.his_sender import HisSender


class LiftOpenSignalTest(unittest.IsolatedAsyncioTestCase):
    async def test_lift_open_is_limited_to_three_sends(self):
        sender = HisSender(2, "127.0.0.1", 9090, "/car02_rxzy_msg", "std_msgs/String")
        sender._start_continuous_send = AsyncMock()

        await sender.send_lift_open("RX001")

        sender._start_continuous_send.assert_awaited_once_with(
            "lift-open", "RX001_lift-open", max_sends=3
        )


if __name__ == "__main__":
    unittest.main()
