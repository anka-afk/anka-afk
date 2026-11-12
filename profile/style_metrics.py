"""Apply the profile palette to existing Metrics SVG output."""

from math import ceil
import re
from xml.etree import ElementTree as ET


SVG = 'http://www.w3.org/2000/svg'
ET.register_namespace('', SVG)
ET.register_namespace('xhtml', 'http://www.w3.org/1999/xhtml')


def configure(svg, width, height, css):
    svg.set('width', str(width))
    svg.set('height', str(height))
    svg.set('viewBox', f'0 0 {width} {height}')
    ET.SubElement(svg, f'{{{SVG}}}style').text = css
    return ET.tostring(svg, encoding='utf-8')


def terminal(source):
    css = '''
      .header { height: 26px; background: #3f3154; border-radius: 7px 7px 0 0; }
      .button { color: #21192e; background: #b3a0ca; text-shadow: none; }
      .button.exit { background: #e0a8c6; }
      .title { color: #f3e8ff; }
      pre { color: #f0e8f9; background: #2b203b; border-radius: 0 0 7px 7px; }
      .stdin, .stdout { animation: none !important; }
      .stdin { width: auto !important; }
      .stdout { max-height: none !important; }
      .ps1-path { color: #dcc1ff; }
      .ps1-location { color: #c4d1f2; }
      .stdout span[style="color:#9be9a8"] { color: #af90d5 !important; }
      .stdout span[style="color:#40c463"] { color: #c0a2e8 !important; }
      .stdout span[style="color:#30a14e"] { color: #d1b5ef !important; }
      .stdout span[style="color:#216e39"] { color: #ebd7ff !important; }
      :root { --color-calendar-graph-day-bg: #574369;
              --color-calendar-graph-day-L1-bg: #9d7cbf;
              --color-calendar-graph-day-L2-bg: #b491da;
              --color-calendar-graph-day-L3-bg: #c9a8ed;
              --color-calendar-graph-day-L4-bg: #e1c7fa; }
    '''
    svg = ET.fromstring(source)
    width, height = int(svg.attrib['width']), int(svg.attrib['height'])
    return configure(svg, width, height, css)


def achievements(source, columns, width):
    source = source.decode('utf-8')
    replacements = {'2088ff': '7754b1', '79b8ff': 'b395db', '7d6cff': '69509b',
                    'b2a8ff': 'bca8df', 'b59151': 'a17b3c', 'ffd576': 'e0bd78',
                    'ff48bd': 'b9628c', 'ff92d8': 'e2a3bf'}
    source = re.sub(r'#([\da-f]{6})\b', lambda m: '#' + replacements.get(m[1].lower(), m[1]), source, flags=re.I)
    css = f'''
      .items-wrapper > section > h2 {{ display: none; }}
      .achievements.compact {{ display: grid; grid-template-columns: repeat({columns}, minmax(0, 1fr)); }}
      .achievements.compact .achievement {{ width: auto; min-width: 0; }}
      .achievement.c .title, .achievement.c .gauge.info {{ color: #63418e; }}
      .achievement.b .title, .achievement.b .gauge.info {{ color: #5d4a91; }}
      .achievement.a .title, .achievement.a .gauge.info {{ color: #805a23; }}
      .achievement.secret .title, .achievement.secret .gauge.info {{ color: #9b4974; }}
      .achievement .value {{ background-color: #b895d82b; }}
      @media (prefers-color-scheme: dark) {{
        .achievement.c .title, .achievement.c .gauge.info {{ color: #e0c3ff; }}
        .achievement.b .title, .achievement.b .gauge.info {{ color: #cdc4fd; }}
        .achievement.a .title, .achievement.a .gauge.info {{ color: #f2d59e; }}
        .achievement.secret .title, .achievement.secret .gauge.info {{ color: #f4b6d6; }}
      }}
    '''
    svg = ET.fromstring(source)
    badges = sum('achievement' in node.get('class', '').split() for node in svg.iter())
    height = max(95, ceil(badges / columns) * 85 + 10)
    return configure(svg, width, height, css)


def more_metrics(source):
    svg = ET.fromstring(source)
    wrapper = next(element for element in svg.iter() if element.get('class') == 'items-wrapper')
    for section in list(wrapper):
        if section.get('class') not in {'habits', 'stargazers'}:
            wrapper.remove(section)
    assert {section.get('class') for section in wrapper} == {'habits', 'stargazers'}
    svg.set('height', '245')
    svg.set('viewBox', '0 0 480 245')
    css = ET.SubElement(svg, f'{{{SVG}}}style')
    css.text = '''
      svg { color: #645b72; }
      h2, h3, .field svg { color: #63418e; fill: #63418e; }
      :root { --color-calendar-graph-day-bg: #efe8f7;
              --color-calendar-graph-day-L1-bg: #ded0f0;
              --color-calendar-graph-day-L2-bg: #bf9fdf;
              --color-calendar-graph-day-L3-bg: #966fc5;
              --color-calendar-graph-day-L4-bg: #63418e; }
      @media (prefers-color-scheme: dark) {
        svg { color: #c1b5d2; }
        h2, h3, .field svg { color: #d8baff; fill: #d8baff; }
        :root { --color-calendar-graph-day-bg: #2d233b;
                --color-calendar-graph-day-L1-bg: #49345e;
                --color-calendar-graph-day-L2-bg: #6a4b88;
                --color-calendar-graph-day-L3-bg: #946cc0;
                --color-calendar-graph-day-L4-bg: #c5a2ea; }
      }
    '''
    return ET.tostring(svg, encoding='utf-8')
