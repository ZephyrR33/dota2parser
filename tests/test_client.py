import io
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from dota2parser import APIError, DotaClient, InputError, resolve_numeric_id


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.client = DotaClient(min_interval=0)

    def test_identifiers(self):
        for value in [123456, "123456", "76561197960389184",
                      "https://steamcommunity.com/profiles/76561197960389184/",
                      "https://www.dotabuff.com/players/123456/matches",
                      "opendota.com/players/123456"]:
            with self.subTest(value=value):
                self.assertEqual(self.client.resolve_player(value), 123456)

    def test_invalid_identifiers(self):
        for value in [0, -1, True, "76561197960265728", "https://evil.com/players/123",
                      "https://opendota.com.evil.com/players/123", "https://steamcommunity.com/id/name"]:
            with self.subTest(value=value), self.assertRaises(InputError):
                self.client.resolve_player(value)

    def test_vanity(self):
        self.client.steam_api_key = "test"
        with patch.object(self.client, "_request", return_value={"response": {"success": 1, "steamid": "76561197960389184"}}):
            self.assertEqual(self.client.resolve_player("https://steamcommunity.com/id/name"), 123456)

    def test_pagination_and_outcome(self):
        pages = [[{"match_id": 3, "player_slot": 128, "radiant_win": False}],
                 [{"match_id": 2, "player_slot": 0, "radiant_win": False}], []]
        with patch.object(self.client, "_request", side_effect=pages) as request:
            result = self.client.get_matches(123, limit=3)
        self.assertEqual([r["won"] for r in result], [True, False])
        self.assertEqual(request.call_args_list[1].args[1]["offset"], 1)

    def test_repeated_page_stops(self):
        with patch.object(self.client, "_request", return_value=[{"match_id": 1}] ) as request:
            self.assertEqual(len(self.client.get_matches(123, limit=10)), 1)
            self.assertEqual(request.call_count, 2)

    def test_invalid_response(self):
        with patch.object(self.client, "_request", return_value={"error": "bad"}), self.assertRaises(APIError):
            self.client.get_matches(123)

    def test_match(self):
        with patch.object(self.client, "_request", return_value={"match_id": 999, "players": []}):
            self.assertEqual(self.client.get_match("https://opendota.com/matches/999")["match_id"], 999)

    def test_retry(self):
        failure = HTTPError("https://example.com", 429, "rate limit", {"Retry-After": "0"}, None)
        with patch("dota2parser.client.urlopen", side_effect=[failure, io.BytesIO(b"[]")]) as request, patch("dota2parser.client.time.sleep"):
            self.assertEqual(self.client.get_matches(123), [])
            self.assertEqual(request.call_count, 2)

    def test_no_key_in_error(self):
        client = DotaClient(api_key="secret", retries=0, min_interval=0)
        failure = HTTPError("https://example.com?api_key=secret", 403, "secret", {}, None)
        with patch("dota2parser.client.urlopen", side_effect=failure), self.assertRaises(APIError) as caught:
            client.get_matches(123)
        self.assertNotIn("secret", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
