import unittest
from unittest.mock import patch

from telegram_preflight import verify_destination


class TelegramPreflightTests(unittest.TestCase):
    @patch("telegram_preflight.telegram_call")
    def test_channel_requires_bot_admin_with_post_permission(self, call):
        call.side_effect = [
            {"id": 123, "username": "PitchIQPicks_bot"},
            {"id": -100123, "type": "channel"},
            {"status": "administrator", "can_post_messages": True},
        ]
        result = verify_destination("token", "@pitchiq_picks")
        self.assertEqual(result, {"bot_id": 123, "chat_type": "channel"})
        self.assertEqual([entry.args[1] for entry in call.call_args_list],
                         ["getMe", "getChat", "getChatMember"])

    @patch("telegram_preflight.telegram_call")
    def test_channel_rejects_bot_without_admin_rights(self, call):
        call.side_effect = [
            {"id": 123, "username": "PitchIQPicks_bot"},
            {"id": -100123, "type": "channel"},
            {"status": "member", "can_post_messages": False},
        ]
        with self.assertRaisesRegex(RuntimeError, "not an administrator"):
            verify_destination("token", "@pitchiq_picks")

    @patch("telegram_preflight.telegram_call")
    def test_channel_rejects_admin_without_post_permission(self, call):
        call.side_effect = [
            {"id": 123, "username": "PitchIQPicks_bot"},
            {"id": -100123, "type": "channel"},
            {"status": "administrator", "can_post_messages": False},
        ]
        with self.assertRaisesRegex(RuntimeError, "cannot post messages"):
            verify_destination("token", "@pitchiq_picks")

    @patch("telegram_preflight.telegram_call")
    def test_group_member_is_accepted(self, call):
        call.side_effect = [
            {"id": 123, "username": "PitchIQPicks_bot"},
            {"id": -123, "type": "supergroup"},
            {"status": "member"},
        ]
        self.assertEqual(verify_destination("token", "-123"),
                         {"bot_id": 123, "chat_type": "supergroup"})

    @patch("telegram_preflight.telegram_call")
    def test_private_chat_is_checked_without_group_membership_call(self, call):
        call.side_effect = [
            {"id": 123, "username": "PitchIQPicks_bot"},
            {"id": 456, "type": "private"},
        ]
        self.assertEqual(verify_destination("token", "456"),
                         {"bot_id": 123, "chat_type": "private"})
        self.assertEqual(call.call_count, 2)

    def test_missing_credentials_fail_closed(self):
        with self.assertRaisesRegex(RuntimeError, "token is missing"):
            verify_destination("", "@pitchiq_picks")
        with self.assertRaisesRegex(RuntimeError, "destination is missing"):
            verify_destination("token", "")


if __name__ == "__main__":
    unittest.main()
