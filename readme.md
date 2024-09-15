# webapps-scraper

scrape webapps by writing all HTTP responses to disk



## status

working prototype



## limitations

the scraping process requires manual interaction with the website,
so ideally all code paths are reached and all assets are fetched (js, css, png, json, ...)

in most cases, the result

- will not work when hosted on a different webserver (like `localhost`)
- will require manual patching to make it portable to different webservers
  - remove hard-coded hostnames
  - use relative paths, remove all absolute paths, to make it work on github-pages
- will contain dynamic data, which must be replaced by variables
- will contain garbage files, which should be removed or deduplicated
- can contain obfuscated javascript, which should be deobfuscated with tools like [webcrack](https://github.com/j4k0xb/webcrack) and [wakaru](https://github.com/pionxzh/wakaru)



## example use

```
$ ./nix-shell.sh

$ ./webapps-scraper.py https://boxy-svg.com/app
```

the output files are written to `out/boxy-svg.com/`



## example results

- [github.com/milahu/boxy-svg-censored](https://github.com/milahu/boxy-svg-censored)
- [github.com/milahu/myjdownloader](https://github.com/milahu/myjdownloader)



## todo



### also capture requests in new windows

currently, when the app opens a new window to show some page,
then the requests to that page are not captured



## keywords

- archiving web apps
- archiving progressive web apps
- scraping web apps
- scraping progressive web apps
- cloning web apps
- cloning progressive web apps
- for self-hosting
- for offline use
- headful scraper
- semi-automatic webscraper
- semi-automatic webscraping
