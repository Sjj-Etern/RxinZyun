import unittest
import asyncio
from unittest.mock import patch

from app.core.config import settings
from app.services.ros_listener import RosListener


class PickupDoneAudioDelayTest(unittest.IsolatedAsyncioTestCase):
    async def test_all_completed_waits_before_playing_audio(self):
        listener = RosListener(
            1, "127.0.0.1", 9090, "/car01_pub", "/rxzy_msg", "his_sub"
        )

        events = []

        async def record_sleep(seconds):
            events.append(("sleep", seconds))

        async def record_play(audio_id):
            events.append(("play", audio_id))
            return True

        with (
            patch.object(settings, "audio_pickup_done_delay", 5),
            patch("app.services.ros_listener.asyncio.sleep", new=record_sleep),
            patch("app.services.audio_service.play_audio_async", new=record_play),
        ):
            await listener.handle_audio_broadcast("all_completed", "RX001", None)

        self.assertEqual(
            events,
            [("sleep", 5), ("play", settings.audio_id_pickup_done)],
        )
        self.assertTrue(listener.audio_state["car_already_arrive_triggered"])

    async def test_duplicate_all_completed_does_not_schedule_duplicate_audio(self):
        listener = RosListener(
            1, "127.0.0.1", 9090, "/car01_pub", "/rxzy_msg", "his_sub"
        )
        delay_started = asyncio.Event()
        release_delay = asyncio.Event()
        played = []

        async def controlled_sleep(_seconds):
            delay_started.set()
            await release_delay.wait()

        async def record_play(audio_id):
            played.append(audio_id)
            return True

        with (
            patch.object(settings, "audio_pickup_done_delay", 5),
            patch("app.services.ros_listener.asyncio.sleep", new=controlled_sleep),
            patch("app.services.audio_service.play_audio_async", new=record_play),
        ):
            first = asyncio.create_task(
                listener.handle_audio_broadcast("all_completed", "RX001", None)
            )
            await delay_started.wait()
            await listener.handle_audio_broadcast("all_completed", "RX001", None)
            release_delay.set()
            await first

        self.assertEqual(played, [settings.audio_id_pickup_done])


if __name__ == "__main__":
    unittest.main()
