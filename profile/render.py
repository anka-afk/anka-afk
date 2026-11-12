"""Gather public profile data and populate the card renderer."""

from base64 import b64encode
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from html import escape, unescape
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from subprocess import run
from time import sleep
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

from style_metrics import achievements, more_metrics, terminal


PROFILE = Path(__file__).resolve().parent
REPO = PROFILE.parent
SVG = 'http://www.w3.org/2000/svg'
USER = 'anka-afk'
STATS = 'https://my-github-stats-lilac.vercel.app/api'
STEAM = 'https://steamcommunity.com/profiles/76561198807374746/'


def fetch(url):
    request = Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'en-US,en;q=0.9'})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=15) as response:
                return response.read()
        except OSError:
            if attempt == 2:
                raise
            sleep(attempt + 1)


def image(data, mime='image/svg+xml'):
    return f'data:{mime};base64,' + b64encode(data).decode('ascii')


def stats_card(colors):
    text, accent, ring = colors
    query = urlencode({
        'username': USER, 'custom_title': 'GitHub Stats', 'show_icons': 'true',
        'include_all_commits': 'true', 'count_private': 'true', 'hide_rank': 'false',
        'hide_border': 'true', 'bg_color': '00000000', 'title_color': text, 'text_color': text,
        'icon_color': accent, 'ring_color': ring, 'card_width': '448',
        'disable_animations': 'true', 'number_format': 'long',
    })
    data = fetch(f'{STATS}?{query}')
    title = ET.fromstring(data).findtext(f'{{{SVG}}}title', '')
    if not re.search(r'Rank: [SABC][+-]?', title):
        raise ValueError(f'Unexpected stats card: {title!r}')
    return image(data)


def language_chart():
    query = urlencode({'username': USER, 'layout': 'compact', 'langs_count': 6})
    root = ET.fromstring(fetch(f'{STATS}/top-langs/?{query}'))
    entries = []
    for text in root.iter(f'{{{SVG}}}text'):
        if match := re.fullmatch(r'(.+?)\s+(\d+(?:\.\d+)?)%', ''.join(text.itertext()).strip()):
            entries.append(match.groups())
    if not entries:
        raise ValueError('The language card returned no languages')
    colors = ('html', 'python', 'jupyter', 'js', 'css', 'ts')
    bars, legend = [], []
    for (name, percent), color in zip(entries, colors):
        bars.append(f'<span class="lang-{color}" style="flex:{percent}"></span>')
        legend.append(f'<div><dt><i class="dot lang-{color}"></i>{escape(name)}</dt><dd>{percent}%</dd></div>')
    return {'LANGUAGE_BAR': ''.join(bars), 'LANGUAGE_LEGEND': ''.join(legend)}


def streak():
    params = urlencode({'user': USER, 'hide_border': 'true', 'theme': 'default'})
    root = ET.fromstring(fetch(f'https://github-readme-streak-stats.herokuapp.com/?{params}'))
    values = [''.join(text.itertext()).strip() for text in root.iter(f'{{{SVG}}}text')]
    numbers = [int(value.replace(',', '')) for value in values if re.fullmatch(r'[\d,]+', value)]
    if len(numbers) != 3:
        raise ValueError('Unexpected number of fields on the contribution streak card')
    return numbers


def activity(streak_values):
    calendar = fetch(f'https://github.com/users/{USER}/contributions').decode()
    day_ids = dict(re.findall(r'<td[^>]*data-date="([^"]+)"[^>]*id="(contribution-day-component-[^"]+)"', calendar))
    counts = dict(re.findall(r'<tool-tip[^>]*for="(contribution-day-component-[^"]+)"[^>]*>([\d,]+|No) contributions? on ', calendar))
    end = max(date.fromisoformat(day) for day in day_ids)
    days = [end - timedelta(days=offset) for offset in range(30, -1, -1)]
    counts = [counts[day_ids[day.isoformat()]] for day in days]
    counts = [0 if count == 'No' else int(count.replace(',', '')) for count in counts]
    ceiling = max(10, ((max(counts) + 9) // 10) * 10)
    total, current, longest = streak_values
    stats = (
        ('Contributions in 31 days', f'{sum(counts):,}'), ('Current streak', f'{current} days'),
        ('Longest streak', f'{longest} days'), ('All-time contributions', f'{total:,}'),
    )

    def label(day):
        return f'{day:%b} {day.day}'

    bars = [
        f'<div class="chart-bar"><span style="height:{100 * count / ceiling:.2f}%"></span></div>'
        for count in counts
    ]
    return {
        'ACTIVITY_SUMMARY': ''.join(f'<div><dt>{key}</dt><dd>{value}</dd></div>' for key, value in stats),
        'CHART_ALT': f'Daily contributions from {label(days[0])} to {label(days[-1])}.',
        'CHART_SCALE': ''.join(f'<span>{tick}</span>' for tick in (ceiling, ceiling // 2, 0)),
        'CHART_BARS': ''.join(bars),
        'CHART_DATES': ''.join(f'<span>{label(days[index])}</span>' for index in (0, 10, 20, 30)),
    }


def recent_games():
    profile = fetch(STEAM).decode()
    recent = profile.partition('class="recent_games"')[2]
    pattern = (
        r'<img class="game_capsule" src="([^"]+)".*?'
        r'<div class="game_info_details">\s*([\d,.]+) hrs? on record\s*<br\s*/?>\s*'
        r'last played on ([^<]+)</div>\s*<div class="game_name"><a[^>]*>([^<]+)</a>'
    )
    entries = re.findall(pattern, recent, re.S)[:2]
    if not entries:
        return '<li class="steam-game-meta">No recent games on Steam.</li>'
    games = []
    for cover, hours, day, name in entries:
        if not cover.startswith('https://shared.fastly.steamstatic.com/'):
            raise ValueError('Unexpected Steam capsule host')
        cover = image(fetch(unescape(cover)), 'image/jpeg')
        name = escape(unescape(name))
        unit = 'hr' if hours == '1' else 'hrs'
        day = escape(' '.join(day.split()))
        games.append(
            f'<li class="steam-game"><img src="{cover}" alt="" />'
            f'<div><span class="steam-game-name">{name}</span><div class="steam-game-meta">'
            f'<span>{hours} {unit} played</span><span>Last played {day}</span></div></div></li>'
        )
    return ''.join(games)


def render():
    with ThreadPoolExecutor(max_workers=5) as pool:
        light = pool.submit(stats_card, ('29223a', '63418e', '8a63b8'))
        dark = pool.submit(stats_card, ('f2ebff', 'd8baff', 'b58de6'))
        languages = pool.submit(language_chart)
        steam = pool.submit(recent_games)
        streak_values = pool.submit(streak)
        values = {
            'STATS_LIGHT': light.result(), 'STATS_DARK': dark.result(),
            **languages.result(), 'STEAM_GAMES': steam.result(), **activity(streak_values.result()),
        }
    raw_terminal = (REPO / 'github-metrics-terminal.svg').read_bytes()
    raw_achievements = (REPO / 'github-metrics-achievements.svg').read_bytes()
    raw_plugins = (REPO / 'github-metrics-plugins.svg').read_bytes()
    values.update({
        'COVER': image((REPO / 'images/background.jpg').read_bytes(), 'image/jpeg'),
        'TERMINAL': image(terminal(raw_terminal)),
        'ACHIEVEMENTS': image(achievements(raw_achievements, 8, 800)),
        'ACHIEVEMENTS_MOBILE': image(achievements(raw_achievements, 4, 350)),
        'MORE_METRICS': image(more_metrics(raw_plugins)),
    })
    template = (PROFILE / 'layout.html').read_text(encoding='utf-8')
    html = re.sub(r'\{\{([A-Z_]+)\}\}', lambda match: values[match[1]], template)
    with TemporaryDirectory(prefix='anka-profile-') as temporary:
        source = Path(temporary) / 'profile.html'
        source.write_text(html, encoding='utf-8')
        run(['node', str(PROFILE / 'capture.mjs'), str(source), str(REPO / 'images/profile')], check=True)


if __name__ == '__main__':
    render()
