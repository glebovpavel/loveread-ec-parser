import logging
import sys
import urllib.request
from urllib.parse import parse_qs, urlsplit, urlunsplit
import re
import random
import time
import html

logger = logging.getLogger("app")

OUTPUT_DIR = '/usr/src/app/output'

CONTENT_START_MARKER = '<div class="MsoNormal"'
CONTENT_END_MARKER = '<div style="text-align: right; font-size: 0.8em;'

RE_CHAPTER_A = re.compile(r'<a name="gl_\d+"></a>')
RE_CHAPTER = re.compile(r'<div class="take_h(\d+)">(.+?)</div>')

RE_P_EM = re.compile(r'<p class=em>(.+?)</p>')
RE_P_CLASS = re.compile(r'<p class=.+?>')

RE_IMG = re.compile(r'<img.+?>')

RE_MULTISPACE = re.compile(r'\s+')

RE_NAVIGATION = re.compile(r"<div class='navigation'.+?>(.+?)</div>")
RE_NAVIGATION_A = re.compile(r'<a href=.+?>(\d+)</a>')

def parseContent(data):
    content = data [ data.index(CONTENT_START_MARKER) : ]
    content = content [ : content.index(CONTENT_END_MARKER) ]
    content = content [ content.index('<p class="MsoNormal"') : ]

    content = RE_CHAPTER_A.sub('', content)
    content = RE_CHAPTER.sub(r'<h\1>\2</h\1>', content)

    content = content.replace('<p class=MsoNormal>', '<p>')
    content = RE_P_EM.sub(r'<p><em>\1</em></p>', content)
    content = RE_P_CLASS.sub(r'<p>', content)

    content = RE_IMG.sub('', content)

    content = RE_MULTISPACE.sub(' ', content)

    #content = html.unescape(content)

    return content


def parsePage(url):
    data = fetchData(url)
    content = parseContent(data)

    return content


def fetchData(url):
    with urllib.request.urlopen(url) as response:
        try:
            charset = [ \
                f.split('=') \
                for f in response.headers['Content-Type'].split('; ') \
                if f.startswith('charset=') \
            ][0][1]
        except (AttributeError, IndexError, KeyError) as e:
            charset = 'utf-8'
        data = response.read().decode(charset)

    return data


def parseBook(url):
    scheme, netloc, path, qs, fragment = urlsplit(url)
    qsd = parse_qs(qs)
    firstPage = int(qsd.get('p', ['1'])[0])
    bookId = int(qsd['id'][0])
    url = urlunsplit((
        scheme,
        netloc,
        path,
        "&".join([ "%s=%s" % (k, v1) for k, v in qsd.items() if k != 'p' for v1 in v ]),
        fragment
    ))

    logger.info("Starting to parse bookId = %d from page #%d", bookId, firstPage)

    data = fetchData(url)
    content = parseContent(data)

    with open(
        '%s/%s.html' % (OUTPUT_DIR, bookId),
        'w' if firstPage == 1 else 'a'
    ) as fd:
        fd.write(content)

    pageCount = int( RE_NAVIGATION_A.findall(RE_NAVIGATION.findall(data)[0])[-1] )
    for page in range(firstPage + 1, pageCount + 1):
        pageUrl = "%s&p=%d" % (url, page)
        content = parsePage(pageUrl)

        with open('%s/%s.html' % (OUTPUT_DIR, bookId), 'a') as fd:
            fd.write(content)

        seconds = random.randint(10, 30)
        logger.info("Parsed page #%d of %d at %s. Sleeping for %d seconds", page, pageCount, pageUrl, seconds)
        time.sleep(seconds)


def splitByChapters(fname):
    with open('%s/%s' % (OUTPUT_DIR, fname), 'r') as fd:
        content = fd.read()

    from ebooklib import epub

    book = epub.EpubBook()

# set metadata
    book.set_identifier('id24380')
    book.set_title('Большая Пайка')
    book.set_language('ru')

    book.add_author('Юлий Дубов')

#     import os
#     os.makedirs('%s/%s' % (OUTPUT_DIR, fname[ : fname.rindex('.html')]), exist_ok = True)

    reChapter = re.compile(r'<h1>(.+?)</h1>')
    chs = [ c for c in reChapter.finditer(content) ]

    chapters = [
        epub.EpubHtml(
            title=title,
            file_name='chapter_%d.xhtml' % i,
            lang='ru',
            content = "<h1>%s</h1>%s" % (title, content[start: end])
        ) for i, start, end, title in zip(
            range(0, len(chs) + 1),
            [0] + [ c.end() for c in chs ],
            [ c.start() for c in chs ] + [ len(content) ],
            ["Введение"] + [ ch.groups()[0] for ch in chs ]
        )
    ]

    # add chapters
    for chapter in chapters:
        book.add_item(chapter)


# define Table Of Contents
    book.toc = [ epub.Section(chapter.title) if chapter.content.strip() == "" else chapter for chapter in chapters ]
# add default NCX and Nav file
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

# define CSS style
    style = 'BODY {color: white;}'
    nav_css = epub.EpubItem(uid="style_nav", file_name="style/nav.css", media_type="text/css", content=style)

# add CSS file
    book.add_item(nav_css)

# basic spine
    book.spine = ['nav'] + chapters

# write to the file
    epub.write_epub('%s/%s.epub' % (OUTPUT_DIR, fname), book, {})


def main():
    logging.basicConfig(
        format = "%(asctime)-15s %(levelname)s %(filename)s:%(funcName)s#%(lineno)d - %(message)s",
        level  = logging.ERROR
    )

    logger.setLevel(logging.DEBUG)
    logger.info("started")

    #parseBook(sys.argv[1])

    splitByChapters('24380.full.html')

    logger.info("finished")


if __name__ == '__main__':
    main()
