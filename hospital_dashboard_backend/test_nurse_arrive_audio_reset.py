import unittest
from unittest.mock import patch

from app.core.config import settings
from app.services.ros_listener import RosListener


class NurseArriveAudioResetTest(unittest.IsolatedAsyncioTestCase):
    async def test_each_new_prescription_plays_delivered_audio_once(self):
        listener = RosListener(
            2, "127.0.0.1", 9090, "/car02_pub", "/car02_rxzy_msg", "his_sub"
        )
        played = []

        async def record_play(audio_id):
            played.append(audio_id)
            return True

        with (
            patch("app.services.audio_service.play_audio_async", new=record_play),
            patch("app.services.ros_listener.record_event"),
        ):
            await listener.handle_audio_broadcast("nurse_arrive", "RX001", None)
            await listener.handle_audio_broadcast("nurse_arrive", "RX001", None)
            await listener.handle_audio_broadcast("nurse_arrive", "RX002", None)
            await listener.handle_audio_broadcast("nurse_arrive", "RX002", None)

        self.assertEqual(
            played,
            [settings.audio_id_delivered, settings.audio_id_delivered],
        )
        self.assertEqual(listener.audio_state["current_prescription_code"], "RX002")
        self.assertTrue(listener.audio_state["nurse_arrive_audio_triggered"])


if __name__ == "__main__":
    unittest.main()
