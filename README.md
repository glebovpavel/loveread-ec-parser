# http://loveread.ec/ Parser

This is a [dockerized](https://www.docker.com/) Python script, which can parse any book from http://loveread.ec/ web-resource.

## How it works

### Exec

1. Install [docker](https://www.docker.com/)
2. `$ git clone git:thisscript`
3. `$ cd there`
4. `docker-compose run --rm app 'http://loveread.ec/view_global.php?id=24382'`
5. ./app/output/ will contain the book in HTML and ePub formats

To continue parsing the book from a specific page, run `docker-compose run --rm app 'http://loveread.ec/read_book.php?id=24382&p=100'` at step 4, where `id=` is the book id, `p=` page number.

### Mobi

To convert an ePub book to mobi, `calibre` software can be used - https://calibre-ebook.com/download

`ebook-convert book.epub book.mobi`

converts an epub book into mobi format, which can be sent to a Kindle email account.
