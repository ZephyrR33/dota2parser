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

    def test_winrate_twenty_matches(self):
        page = [{"match_id": i + 1, "player_slot": 0 if i < 12 else 128,
                 "radiant_win": True} for i in range(20)]
        with patch.object(self.client, "_request", return_value=page) as request:
            result = self.client.get_winrate("opendota.com/players/123")
        self.assertEqual(result, {"requested_matches": 20, "total_matches": 20,
                                  "counted_matches": 20, "wins": 12, "losses": 8,
                                  "unknown_matches": 0, "winrate": 60.0})
        self.assertEqual(request.call_args.args[1], {"limit": 20, "offset": 0})

    def test_winrate_partial_and_unknown(self):
        page = [{"match_id": 1, "player_slot": 128, "radiant_win": False},
                {"match_id": 2, "player_slot": 0, "radiant_win": False},
                {"match_id": 3}]
        with patch.object(self.client, "_request", side_effect=[page, []]):
            result = self.client.get_winrate(123)
        self.assertEqual(result["total_matches"], 3)
        self.assertEqual(result["counted_matches"], 2)
        self.assertEqual(result["unknown_matches"], 1)
        self.assertEqual(result["winrate"], 50.0)

    def test_winrate_no_outcomes(self):
        for page in ([], [{"match_id": 1}]):
            with self.subTest(page=page), patch.object(self.client, "_request", side_effect=[page, []]):
                self.assertIsNone(self.client.get_winrate(123)["winrate"])

    def test_winrate_invalid_limit(self):
        for limit in (0, -1, True, 1.5):
            with self.subTest(limit=limit), self.assertRaises(InputError):
                self.client.get_winrate(123, limit=limit)

    def test_winrate_cli(self):
        from dota2parser.__main__ import main
        with patch("sys.argv", ["dota2parser", "123", "--winrate"]), patch.object(DotaClient, "get_winrate", return_value={"winrate": 60.0}) as request, patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(main(), 0)
            self.assertIn('"winrate": 60.0', output.getvalue())
            request.assert_called_once_with("123", limit=20)

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
