"""Render and check the shipped offline reading guide from its repository documents."""
import argparse
import html
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT/'docs'
WEB = ROOT/'discprobe/web/home/learn'
SOURCES = ('how-disc-images-work.md','how-disc-images-work.zh.md','grating-card.md',
           'grating-card.zh.md','goals/colour-solver-audit.md','why-calibrate.md',
           'why-calibrate.zh.md','first-colour-disc.md','first-colour-disc.zh.md')
PAGES = {DOCS/source:Path(source).with_suffix('.html').name for source in SOURCES}
INLINE = re.compile(r'`([^`]+)`|\*\*([^*]+)\*\*|(!?)\[([^\]]+)\]\(([^)]+)\)')
HEADING = re.compile(r'^(#{1,3}) (.+)$',re.M)


def slug(text):
    return re.sub(r'[^\w -]','',text.lower()).replace(' ','-')


def inline(line, source, output):
    result, end = [], 0
    for token in INLINE.finditer(line):
        result.append(html.escape(line[end:token.start()]))
        code, strong, image, title, href = token.groups()
        if code:
            result.append(f'<code>{html.escape(code)}</code>')
        elif strong:
            result.append(f'<strong>{html.escape(strong)}</strong>')
        else:
            filename, _, fragment = href.partition('#')
            target = (source.parent/filename).resolve() if filename else source
            if not target.is_relative_to(ROOT) or not target.is_file():
                raise ValueError(f'{source.name}: missing local link {href}')
            if fragment and target.suffix == '.md' and fragment not in heading_ids(target):
                raise ValueError(f'{source.name}: missing heading {href}')
            if image:
                assert target.is_relative_to(DOCS/'showcase')
                path = f'media/{target.name}'
                output[WEB/path] = target.read_bytes()
                result.append(f'<img src="{path}" alt="{html.escape(title)}" loading="lazy">')
            elif target in PAGES:
                url = PAGES[target] + (f'#{fragment}' if fragment else '')
                result.append(f'<a href="{html.escape(url)}" data-doc>{html.escape(title)}</a>')
            else:
                # References to other repository material stay in the Markdown edition.
                result.append(html.escape(title))
        end = token.end()
    result.append(html.escape(line[end:]))
    return ''.join(result)


def heading_ids(source):
    return {slug(text) for _,text in HEADING.findall(source.read_text(encoding='utf-8'))}


def blocks(text, source, output):
    def fmt(line):
        return inline(line,source,output)
    for block in re.split(r'\n[ \t]*\n',text.strip()):
        if block.startswith('```') and block.endswith('```'):
            yield '<pre><code>'+html.escape('\n'.join(block.splitlines()[1:-1]))+'</code></pre>'
        elif block == '<!-- start-guide-diagram -->':
            yield '<div class="learn-diagram"></div>'
        elif block.startswith('<details>\n<summary>') and block.endswith('</summary>'):
            yield '<details><summary>'+html.escape(block[19:-10])+'</summary>'
        elif block == '</details>':
            yield block
        elif heading := HEADING.fullmatch(block):
            level = len(heading[1])
            title = heading[2]
            yield f'<h{level} id="{html.escape(slug(title))}">{fmt(title)}</h{level}>'
        elif block.startswith('| '):
            rows = [line.strip('|').split('|') for line in block.splitlines()]
            head = ''.join(f'<th scope="col">{fmt(cell.strip())}</th>' for cell in rows[0])
            body = ''.join('<tr>'+''.join(f'<td>{fmt(cell.strip())}</td>' for cell in row)+'</tr>' for row in rows[2:])
            yield f'<div class="learn-table"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'
        elif block.startswith('- ') and all(line.startswith('- ') for line in block.splitlines()):
            yield '<ul>'+''.join(f'<li>{fmt(line[2:])}</li>' for line in block.splitlines())+'</ul>'
        else:
            yield f'<p>{fmt(block)}</p>'


def render():
    output = {}
    for source,name in PAGES.items():
        text = source.read_text(encoding='utf-8')
        title = text.splitlines()[0].removeprefix('# ')
        lang = 'zh-CN' if source.name.endswith('.zh.md') or source.parent.name == 'goals' else 'en'
        body = '\n'.join(blocks(text,source,output))
        output[WEB/name] = f'''<!doctype html>
<!-- Generated from docs/{source.relative_to(DOCS).as_posix()} by tools/render_learning_guide.py. -->
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} · disc-probe</title>
<link rel="icon" type="image/x-icon" href="../../brand/probe/favicon.ico">
<link rel="apple-touch-icon" sizes="180x180" href="../../brand/probe/apple-touch-icon.png">
<link rel="stylesheet" href="../guide.css">
<link rel="stylesheet" href="./page.css">
<link rel="stylesheet" href="../../fonts/titles.css">
<script type="module" src="./page.mjs"></script>
</head>
<body><main>
{body}
</main></body>
</html>
'''.encode('utf-8')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    args = parser.parse_args()
    generated = render()
    for path,data in generated.items():
        if args.check:
            current = path.read_bytes() if path.is_file() else b''
            if path.suffix == '.html':
                current = current.replace(b'\r\n',b'\n')
            if current != data:
                raise SystemExit(f'Needs regeneration: {path.relative_to(ROOT)}')
        else:
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(data)
    print(f'{len(PAGES)} pages and {len(generated)-len(PAGES)} illustrations checked')
