import logging
import sys
import urllib.request
from urllib.parse import parse_qs, urlsplit, urlunsplit
import re
import random
import time
import html

from ebooklib.plugins.booktype import BooktypeFootnotes
from ebooklib import epub

logger = logging.getLogger("app")

OUTPUT_DIR = '/usr/src/app/output'

URL_PREFIX = 'http://loveread.ec'
READ_BOOK_ENDPOINT = '/read_book.php'
BOOK_COVER_ENDPOINT = '/view_global.php'

CONTENT_START_MARKER = '<div class="MsoNormal"'
CONTENT_END_MARKER = '<div style="text-align: right; font-size: 0.8em;'

RE_CHAPTER_A = re.compile(r'<a name="gl_\d+"></a>')
RE_CHAPTER = re.compile(r'<div class="take_h(\d+)">(.+?)</div>')

RE_P_EM = re.compile(r'<p class=em>(.+?)</p>')
RE_P_CLASS = re.compile(r'<p class=.+?>')

# Example:
# <a href="notes.php?id=24380#30" target="_blank" title=" Извините, мы закрываемся. Вы хотите что-нибудь из этого? (англ.) ">[30]</a>
RE_NOTE = re.compile(r'<a.+?title="(.+?)".*?>.*?(\d+).*?</a>')

RE_IMG = re.compile(r'<img.+?>')

RE_MULTISPACE = re.compile(r'\s+')

RE_NAVIGATION = re.compile(r"<div class='navigation'.+?>(.+?)</div>")
RE_NAVIGATION_A = re.compile(r'<a href=.+?>(\d+)</a>')

FOOTNOTES = []
class Footnote:
    def __init__(self, footnoteId, note):
        self.footnoteId = footnoteId
        self.note = note


def footnotesRepl(matchobj):

    # <span id="InsertNoteID_1_marker1" class="InsertNoteMarker"><sup><a href="#InsertNoteID_1">1</a></sup><span>
    # <ol id="InsertNote_NoteList"><li id="InsertNoteID_1">prvi footnote <span id="InsertNoteID_1_LinkBacks"><sup><a href="#InsertNoteID_1_marker1">^</a></sup></span></li>

    FOOTNOTES.append(Footnote(matchobj.group(2), matchobj.group(1)))
    return '<span id="InsertNoteID_{fid}_marker1" class="InsertNoteMarker"><sup><a href="#InsertNoteID_{fid}">{matchedId}</a></sup><span>'.format(fid = matchobj.group(2), matchedId = matchobj.group(2))


class BookCover():
    def __init__(self, bookId, author, title, description, imgFileName):
        self.bookId = bookId
        self.author = author
        self.title  = title
        self.description = description
        self.imgFileName = imgFileName

    @staticmethod
    def parseBookCover(url, bookId):
        content = fetchData(url)
        content = RE_MULTISPACE.sub(' ', content)
        meta    = re.search(r'<td.+?class="span_str".*?>(.+?)</td>', content)[1]
        imgUrl  = "%s/%s" % (URL_PREFIX, re.search(r'<img.+?src="(.+?)"', meta)[1])
        imgFileName = '%s/%s.%s' % (OUTPUT_DIR, bookId, imgUrl[imgUrl.rindex(".") + 1 : ])
        urllib.request.urlretrieve(imgUrl, imgFileName)
        reg = re.compile(r"(?:<a.+?)?<strong>(.+?)</strong>(?:.*?</a>)?")
        metaList = [
            (k, reg.sub(r"\1", v).strip()) for k, v in
            re.findall(r"<span>(.+?)</span>(.+?)<br>", meta)
        ]
        author = next(( v for k, v in metaList if k == 'Автор: ' ), "N/A")
        title  = next(( v for k, v in metaList if k == 'Название: ' ), "N/A")
        metaStr = "<p>%s</p>" % "<br />".join([ "%s%s" % (k, v) for k, v in metaList ])
        description = "%s<p>%s</p>" % (
            metaStr,
            re.search(r'<p class="span_str">(.+?)(?:\s*В нашей библиотеке вы.+?)?</p>', content)[1]
        )

        return BookCover(bookId, author, title, description, imgFileName)


def parseContent(data):
    content = data [ data.index(CONTENT_START_MARKER) : ]
    content = content [ : content.index(CONTENT_END_MARKER) ]
    content = content [ content.index('<p class="MsoNormal"') : ]

    content = RE_MULTISPACE.sub(' ', content)

    content = RE_CHAPTER_A.sub('', content)
    content = RE_CHAPTER.sub(r'<h\1>\2</h\1>', content)

    content = content.replace('<p class=MsoNormal>', '<p>')
    content = RE_P_EM.sub(r'<p><em>\1</em></p>', content)
    content = RE_P_CLASS.sub(r'<p>', content)

    content = RE_IMG.sub('', content)

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
    if not url.startswith(URL_PREFIX):
        raise ValueError('Only URL_PREFIX="%s" is supported. Current url is "%s"' % (URL_PREFIX, url))

    scheme, netloc, path, qs, fragment = urlsplit(url)
    qsd = parse_qs(qs)
    firstPage = int(qsd.get('p', ['1'])[0])
    bookId = int(qsd['id'][0])

    makeUrl = lambda endpoint: urlunsplit((
        scheme,
        netloc,
        endpoint,
        "&".join([ "%s=%s" % (k, v1) for k, v in qsd.items() if k != 'p' for v1 in v ]),
        fragment
    ))

    readBookUrl = makeUrl(READ_BOOK_ENDPOINT)
    bookCoverUrl = makeUrl(BOOK_COVER_ENDPOINT)

    if path != READ_BOOK_ENDPOINT and path != BOOK_COVER_ENDPOINT:
        raise ValueError('Unknown endpoint in url = "%s"' % url)

    cover = BookCover.parseBookCover(bookCoverUrl, bookId)
    fname = parseBookContent(readBookUrl, bookId, firstPage)
    return (cover, fname)


def parseBookContent(url, bookId, firstPage):
    logger.info("Starting to parse bookId = %d from page #%d", bookId, firstPage)

    data = fetchData(url)
    content = parseContent(data)
    pageCount = int( RE_NAVIGATION_A.findall(RE_NAVIGATION.findall(data)[0])[-1] )
    fname = '%s/%s.html' % (OUTPUT_DIR, bookId)

    if firstPage > pageCount:
        logger.info("firstPage > pageCount : %d > %d", firstPage, pageCount)
        return fname

    with open(fname, 'w' if firstPage == 1 else 'a') as fd:
        fd.write(content)

    for page in range(firstPage + 1, pageCount + 1):
        pageUrl = "%s&p=%d" % (url, page)
        content = parsePage(pageUrl)

        with open(fname, 'a') as fd:
            fd.write(content)

        seconds = random.randint(10, 30)
        logger.info("Parsed page #%d of %d at %s. Sleeping for %d seconds", page, pageCount, pageUrl, seconds)
        time.sleep(seconds)

    return fname


def createEpub(bookCover, htmlBookFileName):
    with open(htmlBookFileName, 'r') as fd:
        content = fd.read()

    book = epub.EpubBook()

# set metadata
    book.set_identifier('id%d' % bookCover.bookId)
    book.set_title(bookCover.title)
    book.set_language('ru')

    book.add_author(bookCover.author)

    book.set_cover("cover.jpg", open(bookCover.imgFileName, 'rb').read())

    reChapter = re.compile(r'<h1>(.+?)</h1>')
    chs = [ c for c in reChapter.finditer(content) ]

    reTitle = re.compile(r'<(?P<tag>[\w\d]+).*?>(?:.*?</\s*(?P=tag)>)?')

    def addFootnotes(chapterContent):
        start = len(FOOTNOTES)
        chapterContent = RE_NOTE.sub(footnotesRepl, chapterContent)
        footnotes = FOOTNOTES[start:]
        if len(footnotes) > 0:
            chapterContent = '%s <ol id="InsertNote_NoteList">%s' % (
                chapterContent,
                "".join([ '<li id="InsertNoteID_{fid}">{fid} - {note}<span id="InsertNoteID_{fid}_LinkBacks"><sup><a href="#InsertNoteID_{fid}_marker1">^</a></sup></span></li>'.format(fid = f.footnoteId, note = f.note) for f in footnotes ])
            )
        return chapterContent

    chapters = [ epub.EpubHtml(
            title='Описание',
            file_name='description.xhtml',
            lang='ru',
            content = "<h1>Описание</h1>%s" % bookCover.description
        ) ] + [
            epub.EpubHtml(
                title=title,
                file_name='chapter_%d.xhtml' % i,
                lang='ru',
                content = "<h1>%s</h1>%s" % (title, addFootnotes(content[start: end]))
            ) for i, start, end, title in zip(
                range(0, len(chs) + 1),
                [0] + [ c.end() for c in chs ],
                [ c.start() for c in chs ] + [ len(content) ],
                ["Введение"] + [ RE_MULTISPACE.sub(' ', reTitle.sub(' - ', ch.groups()[0])) for ch in chs ]
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
    epub.write_epub('%s/%s.epub' % (OUTPUT_DIR, bookCover.bookId), book, {'plugins' : [ BooktypeFootnotes(book) ]})


def main():
    logging.basicConfig(
        format = "%(asctime)-15s %(levelname)s %(filename)s:%(funcName)s#%(lineno)d - %(message)s",
        level  = logging.ERROR
    )

    logger.setLevel(logging.DEBUG)
    logger.info("started")

    url = sys.argv[1]

    cover, htmlBookFileName = parseBook(url)
    createEpub(cover, htmlBookFileName)

    logger.info("finished")


if __name__ == '__main__':
    main()
