"""Offline regression tests for external-source failures."""

from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

import render


def http_error(code=429, headers=None):
    error = HTTPError(render.STEAM, code, 'test failure', headers or {}, None)
    error.close()
    return error


class QuietTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(render, 'warning')
        self.warning = patcher.start()
        self.addCleanup(patcher.stop)


class FetchTests(QuietTests):
    def test_retry_after_seconds_then_success(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'ok'
        with patch.object(render, 'urlopen', side_effect=[http_error(headers={'Retry-After': '45'}), response]) as request, \
                patch.object(render, 'sleep') as sleep:
            self.assertEqual(render.fetch(render.STEAM), b'ok')
        sleep.assert_called_once_with(45)
        self.assertEqual(request.call_count, 2)

    def test_retry_after_http_date(self):
        now = datetime(2026, 11, 13, tzinfo=timezone.utc)
        error = http_error(headers={'Retry-After': format_datetime(now + timedelta(seconds=60), usegmt=True)})
        with patch.object(render, 'datetime') as clock:
            clock.now.return_value = now
            self.assertEqual(render.retry_delay(error, 0), 60)

    def test_exhausted_429_has_bounded_backoff(self):
        with patch.object(render, 'urlopen', side_effect=http_error()) as request, \
                patch.object(render, 'sleep') as sleep:
            with self.assertRaises(HTTPError):
                render.fetch(render.STEAM)
        self.assertEqual(request.call_count, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [15, 30])

    def test_permanent_error_and_long_cooldown_do_not_retry(self):
        for error in (http_error(404), http_error(headers={'Retry-After': '3600'})):
            with self.subTest(code=error.code), patch.object(render, 'urlopen', side_effect=error) as request, \
                    patch.object(render, 'sleep') as sleep:
                with self.assertRaises(HTTPError):
                    render.fetch(render.STEAM)
                request.assert_called_once()
                sleep.assert_not_called()

    def test_timeout_and_invalid_retry_header(self):
        with patch.object(render, 'urlopen', side_effect=TimeoutError()), patch.object(render, 'sleep') as sleep:
            with self.assertRaises(TimeoutError):
                render.fetch(render.STEAM)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [5, 10])
        self.assertEqual(render.retry_delay(http_error(headers={'Retry-After': 'invalid'}), 0), 15)


class CacheTests(QuietTests):
    def setUp(self):
        super().setUp()
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.cache = Path(temporary.name) / 'cache'
        patcher = patch.object(render, 'CACHE', self.cache)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.fallback = {'STEAM_GAMES': 'unavailable'}

    def test_success_survives_failure_and_then_recovers(self):
        old = {'STEAM_GAMES': 'old games'}
        self.assertEqual(render.cached_source('steam', lambda: old, self.fallback), old)
        path = self.cache / 'steam.json'
        saved = path.read_bytes()
        self.assertEqual(render.cached_source('steam', Mock(side_effect=http_error()), self.fallback), old)
        self.assertIn('using cached data from', self.warning.call_args.args[0])
        self.assertEqual(path.read_bytes(), saved)
        new = {'STEAM_GAMES': 'new games'}
        self.assertEqual(render.cached_source('steam', lambda: new, self.fallback), new)
        self.assertEqual(json.loads(path.read_text())['values'], new)

    def test_missing_corrupt_and_wrong_schema_cache(self):
        self.cache.mkdir()
        path = self.cache / 'steam.json'
        for content in (None, '{bad', '[]', '{"values": null}',
                        '{"values": {"WRONG": "key"}, "updated_at": "yesterday"}'):
            with self.subTest(content=content):
                if content is not None:
                    path.write_text(content)
                self.assertEqual(render.cached_source('steam', Mock(side_effect=http_error()), self.fallback), self.fallback)
                if content is None:
                    self.assertFalse(path.exists())
                else:
                    self.assertEqual(path.read_text(), content)

    def test_bad_parsed_data_keeps_good_cache(self):
        old = {'STEAM_GAMES': 'old games'}
        render.cached_source('steam', lambda: old, self.fallback)
        self.assertEqual(render.cached_source('steam', lambda: {}, self.fallback), old)

    def test_steam_failure_does_not_block_other_sections(self):
        render.cached_source('steam', lambda: {'STEAM_GAMES': 'cached games'}, self.fallback)
        with patch.object(render, 'recent_games', side_effect=http_error()), \
                patch.object(render, 'stats_card', return_value='fresh stats'), \
                patch.object(render, 'language_chart', return_value={'LANGUAGE_BAR': 'fresh bars', 'LANGUAGE_LEGEND': 'fresh legend'}), \
                patch.object(render, 'streak', return_value=[12, 2, 3]), \
                patch.object(render, 'activity', return_value={
                    'ACTIVITY_SUMMARY': 'fresh activity', 'CHART_ALT': 'chart',
                    'CHART_SCALE': 'scale', 'CHART_BARS': 'bars', 'CHART_DATES': 'dates',
                }):
            values = render.gather_values()
        self.assertEqual(values['STEAM_GAMES'], 'cached games')
        self.assertEqual(values['STATS_LIGHT'], 'fresh stats')
        self.assertEqual(values['LANGUAGE_BAR'], 'fresh bars')
        self.assertEqual(values['ACTIVITY_SUMMARY'], 'fresh activity')
        self.assertEqual(len(list(self.cache.glob('*.json'))), 5)

    def test_all_sources_down_on_first_run_still_reaches_capture(self):
        def capture(command, **kwargs):
            html = Path(command[2]).read_text(encoding='utf-8')
            self.assertNotIn('{{', html)
            self.assertIn('Steam data temporarily unavailable', html)
            self.assertNotIn('No recent games on Steam', html)

        with ExitStack() as stack:
            for name in ('stats_card', 'language_chart', 'recent_games', 'streak'):
                stack.enter_context(patch.object(render, name, side_effect=TimeoutError('offline')))
            run = stack.enter_context(patch.object(render, 'run', side_effect=capture))
            render.render()
            run.assert_called_once()
        self.assertFalse(self.cache.exists())

    def test_programming_error_is_not_hidden(self):
        with self.assertRaises(RuntimeError):
            render.cached_source('steam', Mock(side_effect=RuntimeError('bug')), self.fallback)


class SteamTests(unittest.TestCase):
    def test_error_page_and_changed_markup_are_not_cached_as_empty_games(self):
        for html in (b'<html>Try again later</html>',
                     b'<div class="profile_header"><div class="recent_games"><img class="game_capsule">'):
            with self.subTest(html=html), patch.object(render, 'fetch', return_value=html):
                with self.assertRaises(ValueError):
                    render.recent_games()

    def test_empty_profile_is_valid(self):
        with patch.object(render, 'fetch', return_value=b'<div class="profile_header"></div>'):
            self.assertIn('No recent games', render.recent_games())


if __name__ == '__main__':
    unittest.main()
