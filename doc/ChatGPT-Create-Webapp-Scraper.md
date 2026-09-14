# Create Webapp Scraper

**User:** Anonymous  
**Created:** 2026/9/14 7:53:48  
**Updated:** 2026/9/14 8:08:02  
**Exported:** 2026/9/14 8:10:41  
**Link:** [<https://chatgpt.com/c/6aa78beb-bda8-83eb-9533-0013b4a27431>](https://chatgpt.com/c/6aa78beb-bda8-83eb-9533-0013b4a27431)

## Prompt:

9/14/2026, 7:58:22 AM

help me create a generic webapp scraper in python

it should start a headful chrome browser, let the user manually use the app (manually generate HTTP traffic), and write **all** HTTP requests and responses to disk for later data extraction (and maybe later automation of the scraping process)

i have already implemented such a scraper in my <https://github.com/milahu/webapps-scraper> but currently that fails to record **all** HTTP responses, it records only some HTTP responses but fails to record other HTTP responses...

my scraper is based on my aiohttp_chromium (<https://github.com/milahu/aiohttp_chromium>) which is based on selenium_driverless (<https://github.com/ttlns/Selenium-Driverless>)

but maybe now there are better "state of the art" solutions for this?

in any case, the script should write (stream) all HTTP traffic directly to disk, it should not buffer HTTP traffic in memory, so in theory, this should also work with "infinite" size HTTP traffic

## Response:

9/14/2026, 7:58:23 AM

> **Searching 2 websites**
>
> Worked for a couple of seconds

Yes. I think there is a substantially better architecture for what you want, and it also explains why your current `aiohttp_chromium` approach is losing responses.

Your existing project is essentially trying to make Chromium's CDP network events behave like a raw HTTP capture layer. [`webapps-scraper`](https://github.com/milahu/webapps-scraper?utm_source=chatgpt.com) and [`aiohttp_chromium`](https://github.com/milahu/aiohttp_chromium?utm_source=chatgpt.com) explicitly run into this problem: Chromium/CDP does not expose arbitrary response bodies as an unbounded streaming interface. ([GitHub](https://github.com/milahu/aiohttp_chromium?utm_source=chatgpt.com))

## My recommendation

Use this architecture:

``` text
                    ┌─────────────────────────┐
                    │        Python           │
                    │                         │
                    │  launcher / controller  │
                    └────────────┬────────────┘
                                 │
                         launches Chrome
                                 │
                    ┌────────────▼────────────┐
                    │     Headful Chrome      │
                    │                         │
                    │ user interacts manually │
                    └────────────┬────────────┘
                                 │
                         HTTP(S) proxy
                                 │
                    ┌────────────▼────────────┐
                    │       mitmproxy         │
                    │                         │
                    │ TLS interception        │
                    │ HTTP/1.1                │
                    │ HTTP/2                  │
                    │ HTTP/3*                 │
                    │ WebSockets              │
                    └────────────┬────────────┘
                                 │
                         Internet
```

The important change is:

> **Don't use CDP as the packet/body capture mechanism. Use CDP/Selenium only to control Chrome.**

Let a real HTTP proxy sit underneath Chrome.

That gives you a much cleaner separation:

- Chrome = browser
- Selenium/Driverless/Playwright = browser control
- mitmproxy = traffic capture
- filesystem = traffic storage
- later Python programs = extraction/replay/automation

And, crucially, you can stream bodies directly to files instead of asking CDP for `Network.getResponseBody()`.

------------------------------------------------------------------------

# Why your current CDP approach loses responses

CDP's `Network` domain is fundamentally an event/inspection interface.

You get things like:

``` text
requestWillBeSent
responseReceived
dataReceived
loadingFinished
loadingFailed
```

but the body is normally retrieved separately with:

``` text
Network.getResponseBody
```

There are internal buffering limits such as `maxTotalBufferSize` and `maxResourceBufferSize`. CDP also has "durable messages", but those are still about retaining response bodies for later retrieval, not giving you an arbitrary-size raw stream to a file. ([Chrome DevTools](https://chromedevtools.github.io/devtools-protocol/tot/Network/?utm_source=chatgpt.com))

That's almost exactly the wrong abstraction for:

> "Record every byte of every response, regardless of size."

CDP's newer `Fetch.takeResponseBodyAsStream` is much more interesting. It exposes an `IO.StreamHandle` instead of returning the entire body, and is specifically intended for sequential reading. ([Chrome DevTools](https://chromedevtools.github.io/devtools-protocol/tot/Fetch/?utm_source=chatgpt.com))

However, it comes with an important complication:

``` text
Fetch.requestPaused
       │
       ▼
takeResponseBodyAsStream
       │
       ▼
IO.read
       │
       ▼
your disk writer
       │
       ▼
continue/fulfill response
```

You have now inserted yourself into the browser's response path.

That's considerably more complicated than a proxy, particularly if your goal is **"record absolutely everything, don't interfere with the browser."**

------------------------------------------------------------------------

# mitmproxy is a very good fit

[mitmproxy](https://mitmproxy.org/?utm_source=chatgpt.com) already has the concept you need: streaming HTTP bodies.

Its API has a `stream` attribute on requests/responses. When enabled, the body isn't buffered by mitmproxy; it is forwarded incrementally. ([Mitmproxy Documentation](https://docs.mitmproxy.org/stable/overview/features/?utm_source=chatgpt.com))

For example, the conceptual addon is basically:

``` python
from mitmproxy import http

def responseheaders(flow: http.HTTPFlow):
    flow.response.stream = True
```

The official documentation explicitly gives this as the mechanism for streaming all responses. ([Mitmproxy Documentation](https://docs.mitmproxy.org/stable/addons/examples/?utm_source=chatgpt.com))

There is one subtlety, though:

**mitmproxy's normal streaming mode doesn't automatically mean "save every streamed byte to disk."**

Its `store_streamed_bodies` option exists, but the documentation explicitly warns that storing streamed bodies increases memory consumption. ([Mitmproxy Documentation](https://docs.mitmproxy.org/stable/concepts/options/?utm_source=chatgpt.com))

So I would **not** simply enable that and call it solved.

Instead, I'd write a small mitmproxy addon whose job is:

``` text
responseheaders()
       │
       ├── create metadata file
       ├── create body file
       └── enable streaming
       
response body chunks
       │
       ▼
streaming writer
       │
       ▼
body.bin
```

That gives you actual disk-backed capture.

------------------------------------------------------------------------

# One important issue: HTTP/3 / QUIC

This is something I'd explicitly design for.

Modern web applications increasingly use HTTP/3.

mitmproxy currently has HTTP/3 support, based on `aioquic`, although its documentation lists limitations and notes that HTTP/3 has been extensively tested primarily with cURL. ([Mitmproxy Documentation](https://docs.mitmproxy.org/stable/concepts/protocols/?utm_source=chatgpt.com))

For a **generic recorder**, I'd therefore initially launch Chrome with QUIC disabled:

``` text
--disable-quic
```

That makes Chrome fall back to HTTP/2/HTTP/1.1 through the proxy.

This is actually desirable for your first implementation because:

``` text
Chrome
  │
  │ HTTP/2
  ▼
mitmproxy
  │
  │ HTTP/2 / HTTP/1.1
  ▼
server
```

is much easier to make deterministic.

Later you can experiment with HTTP/3 if you discover an application that actually requires it.

------------------------------------------------------------------------

# The storage format I'd use

I wouldn't create one giant `.har` file.

HAR is useful for interoperability, but it is not particularly attractive as your primary storage format when you explicitly want arbitrarily large bodies.

Instead, I'd make every HTTP transaction a directory:

``` text
capture/
    000000001/
        request.json
        request-body.bin
        response.json
        response-body.bin

    000000002/
        request.json
        response.json
        response-body.bin

    000000003/
        request.json
        request-body.bin
        response.json
        response-body.bin
```

For example:

``` json
{
    "id": 123,
    "timestamp": "2026-09-14T07:31:22.123Z",
    "method": "GET",
    "url": "https://example.com/api/items?page=1",
    "http_version": "HTTP/2",
    "headers": {
        "accept": "application/json"
    },
    "body_file": null
}
```

and:

``` json
{
    "status_code": 200,
    "reason": "OK",
    "http_version": "HTTP/2",
    "headers": {
        "content-type": "application/json",
        "content-length": "..."
    },
    "body_file": "response-body.bin"
}
```

The important property is:

``` text
JSON = small metadata
BIN  = potentially infinite body
```

So a 500 GB response doesn't cause a 500 GB Python object.

------------------------------------------------------------------------

# Even better: append-only storage

I'd actually go one step further.

For millions of requests, creating a directory containing several files per request can become annoying.

A very nice format would be:

``` text
capture/
    requests/
        000000001.json
        000000002.json
        ...
    
    responses/
        000000001.bin
        000000002.bin
        ...

    metadata/
        000000001.json
        000000002.json
        ...
```

Or:

``` text
capture/
    index.jsonl
    bodies/
        000000001.request
        000000001.response
        ...
```

where `index.jsonl` contains one JSON object per transaction.

For example:

``` json
{"id":1,"request":"bodies/000000001.request","response":"bodies/000000001.response","url":"https://example.com/","status":200}
{"id":2,"request":"bodies/000000002.request","response":"bodies/000000002.response","url":"https://example.com/api","status":200}
```

That makes later processing extremely easy:

``` python
for line in open("index.jsonl"):
    entry = json.loads(line)

    with open(entry["response"], "rb") as f:
        ...
```

------------------------------------------------------------------------

# But there's another important distinction

You said:

> write **all** HTTP requests and responses

There are actually three different meanings of "all":

### 1. All browser HTTP requests

``` text
GET
POST
PUT
PATCH
DELETE
OPTIONS
HEAD
...
```

Easy with the proxy.

### 2. All HTTP response bodies

Also feasible.

### 3. Literally all network traffic

This includes things such as:

``` text
WebSocket
WebTransport
HTTP/3 / QUIC
DNS
CONNECT
Direct Sockets
RTC
```

That is a different problem.

For a webapp scraper I would define the first version as:

``` text
HTTP/1.1
HTTP/2
WebSocket
HTTPS
```

and make the architecture extensible.

------------------------------------------------------------------------

# WebSockets deserve special treatment

A modern webapp can do a lot of its useful work over WebSockets:

``` text
HTTP:
    GET /app
    GET /static/app.js

WebSocket:
    connect /socket

    {"type":"subscribe", ...}
    {"type":"update", ...}
    {"type":"message", ...}
```

So if your objective is really "everything the webapp communicates", WebSocket capture is essential.

mitmproxy supports WebSockets, although its current documentation notes that it doesn't store ping/pong frames in the same way as ordinary WebSocket messages. ([Mitmproxy Documentation](https://docs.mitmproxy.org/stable/concepts/protocols/?utm_source=chatgpt.com))

I'd therefore record them separately:

``` text
websocket/
    00001.jsonl
    00002.jsonl
```

with records like:

``` json
{"direction":"client->server","timestamp":123.4,"opcode":1,"data":"..."}
{"direction":"server->client","timestamp":123.5,"opcode":1,"data":"..."}
```

Binary frames should go to `.bin` files rather than being converted to JSON/base64.

------------------------------------------------------------------------

# Chrome configuration

The browser side can remain extremely simple.

Conceptually:

``` python
from selenium_driverless import webdriver

options = webdriver.ChromeOptions()

options.add_argument(
    "--proxy-server=http://127.0.0.1:8080"
)

async with webdriver.Chrome(options=options) as driver:
    await driver.get("https://example.com")

    input("Use the browser manually, then press ENTER...")
```

Your existing [Selenium-Driverless](https://github.com/ttlns/Selenium-Driverless?utm_source=chatgpt.com) already supports proxy configuration, so you don't necessarily need to replace your browser-control layer. ([GitHub](https://github.com/ttlns/Selenium-Driverless?utm_source=chatgpt.com))

In fact, I'd keep it.

The architectural change I'd make is:

``` text
BEFORE

selenium-driverless
        │
        ▼
       CDP
        │
        ▼
   aiohttp_chromium
        │
        ▼
    scraper

AFTER

selenium-driverless
        │
        ▼
      Chrome
        │
        ▼
    mitmproxy
        │
        ▼
  streaming recorder
        │
        ▼
       disk
```

Your `aiohttp_chromium` layer then becomes optional rather than being responsible for capture.

------------------------------------------------------------------------

# One caveat: Chrome's own network activity

A proxy sees network connections made through the proxy.

That means you should make sure Chrome isn't bypassing it for some classes of traffic.

In particular I'd investigate:

``` text
QUIC
WebRTC
Direct Sockets
service workers
extensions
Chrome internal traffic
DNS
```

For the initial recorder I'd deliberately constrain the environment.

Something like:

``` text
--proxy-server=http://127.0.0.1:8080
--disable-quic
--disable-extensions
```

and use a fresh temporary Chrome profile.

Then your capture becomes much more reproducible.

------------------------------------------------------------------------

# The architecture I'd implement

I'd make a project roughly like this:

``` text
webapp-recorder/
│
├── recorder.py
├── browser.py
├── proxy.py
│
├── capture/
│   ├── writer.py
│   ├── http.py
│   ├── websocket.py
│   └── index.py
│
├── replay/
│   └── ...
│
└── extract/
    └── ...
```

### `browser.py`

Only handles:

``` text
launch Chrome
configure proxy
create profile
navigate
wait for user
close browser
```

### `proxy.py`

Starts mitmproxy.

### `capture/http.py`

Handles:

``` text
request headers
request body
response headers
response body
connection metadata
timing
errors
redirects
```

### `capture/writer.py`

The most important component.

Its API should be something like:

``` python
capture.start_request(metadata)

capture.write_request_body(chunk)

capture.finish_request()

capture.start_response(metadata)

capture.write_response_body(chunk)

capture.finish_response()
```

And **none of these functions should accumulate the body**.

For example:

``` python
def write_response_body(self, request_id, chunk):
    with self.lock:
        self.files[request_id].write(chunk)
```

or, preferably, keep the file descriptor open for the lifetime of the stream.

------------------------------------------------------------------------

# The really important invariant

I'd make this an explicit design requirement:

> **At no point should the recorder need to know the total size of a request or response.**

So this should work:

``` text
Content-Length: 10 GB
```

but also:

``` text
Transfer-Encoding: chunked
```

and:

``` text
no Content-Length
       +
connection stays open forever
```

The writer simply does:

``` text
chunk
chunk
chunk
chunk
chunk
...
```

until EOF.

That gives you your theoretical "infinite HTTP stream" property.

------------------------------------------------------------------------

# What I would NOT do

I would not build the new version around:

``` python
Network.responseReceived
Network.getResponseBody
```

even though it looks attractive.

I would also avoid:

``` python
await response.body()
```

or equivalents anywhere in the capture path.

Those APIs are fundamentally designed around obtaining a completed response body, whereas your requirement is fundamentally a **streaming capture** requirement.

The existence of CDP's `Fetch.takeResponseBodyAsStream` is evidence that Chrome now has a lower-level mechanism, but it is still interception-oriented and requires you to pause and manage the response yourself. ([Chrome DevTools](https://chromedevtools.github.io/devtools-protocol/tot/Fetch/?utm_source=chatgpt.com))

------------------------------------------------------------------------

# There is also a potentially interesting hybrid

If you want maximum information, I'd actually consider:

``` text
                   Chrome
                  /      \
                 /        \
               CDP       proxy
                │           │
                │           │
         browser metadata   raw HTTP
                │           │
                └─────┬─────┘
                      ▼
                   recorder
```

CDP gives you useful browser-side information that a proxy doesn't necessarily know:

``` text
frame ID
document URL
resource type
initiator
redirect chain
request ID
navigation
service-worker involvement
cache information
```

while mitmproxy gives you the actual HTTP transaction.

You can correlate them by URL/timing and maintain a richer dataset.

That would be an excellent foundation for your **later automation** idea.

------------------------------------------------------------------------

## My preferred end result

I'd aim for a command like:

``` bash
python webapp_recorder.py \
    --url https://some-webapp.example \
    --output ./captures/my-session
```

which produces:

``` text
captures/
└── my-session/
    ├── session.json
    ├── index.jsonl
    │
    ├── http/
    │   ├── 00000001/
    │   │   ├── request.json
    │   │   ├── request-body.bin
    │   │   ├── response.json
    │   │   └── response-body.bin
    │   │
    │   └── ...
    │
    ├── websocket/
    │   ├── 00000001.jsonl
    │   └── ...
    │
    └── chrome/
        └── ...
```

Then the **next stage** becomes very powerful:

``` text
capture
   │
   ├── inspect
   │
   ├── extract
   │
   ├── search
   │
   └── generate automation
```

For example, an extractor could discover:

``` text
POST /api/search
POST /api/search
GET  /api/results/123
GET  /api/results/124
```

and eventually generate a Python client that reproduces those requests using the cookies/tokens discovered during the browser session.

------------------------------------------------------------------------

## So, in short

I would **not replace Selenium-Driverless yet**.

I'd replace the **network-capture architecture**:

**Current:**

``` text
Chrome → CDP → Python → response body API → disk
```

**Recommended:**

``` text
Chrome → mitmproxy → streaming files
   ↑
Selenium-Driverless
```

This is much closer to the actual requirement, and mitmproxy already provides the crucial streaming primitive. ([Mitmproxy Documentation](https://docs.mitmproxy.org/stable/overview/features/?utm_source=chatgpt.com))

And your existing `aiohttp_chromium` README actually points at essentially this fundamental problem: Chromium/CDP isn't a good generic infinite-stream HTTP client/capture interface. ([GitHub](https://github.com/milahu/aiohttp_chromium?utm_source=chatgpt.com))

**If you want, I can next build the actual Python prototype** - a single runnable script that launches headful Chrome + mitmproxy, automatically installs/uses the mitmproxy CA, records request/response metadata and bodies **chunk-by-chunk directly to disk**, handles redirects and WebSockets, and leaves the browser under manual user control.

------------------------------------------------------------------------

**Sources:**

- [GitHub - milahu/aiohttp_chromium: aiohttp-like interface to chromium. based on selenium_driverless to bypass cloudflare · GitHub](https://github.com/milahu/aiohttp_chromium?utm_source=chatgpt.com)
- [Chrome DevTools Protocol - Network domain](https://chromedevtools.github.io/devtools-protocol/tot/Network/?utm_source=chatgpt.com)
- [Features](https://docs.mitmproxy.org/stable/overview/features/?utm_source=chatgpt.com)

## Prompt:

9/14/2026, 8:07:37 AM

> CDP gives you useful browser-side information that a proxy doesn't necessarily know:

interesting! so my existing <https://github.com/milahu/webapps-scraper> is still useful, and we should build on that, by adding mitmproxy to capture all HTTP traffic, and by correlating the lossless HTTP traffic with the lossy "CDP traffic"

ok, help me to add mitmproxy to my webapps-scraper

## Response:

9/14/2026, 8:07:38 AM

> **Searching github.com**
>
> Worked for 5s

Yes - and after looking at the current repository, I think we should **keep your existing CDP recorder intact and add mitmproxy as a second, independent capture plane**, rather than replacing the current implementation. Your current `webapps-scraper.py` is only ~120 lines and currently hooks `Network.responseReceived` and calls `Network.getResponseBody`; the README also explicitly identifies missing/new-window capture as a TODO. ([GitHub](https://github.com/milahu/webapps-scraper/blob/main/webapps-scraper.py))

The key architectural change should be:

``` text
                         ┌─────────────────────┐
                         │       Chrome        │
                         │     headful/user     │
                         └──────────┬──────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
              CDP / Driverless                HTTP proxy
                    │                               │
                    ▼                               ▼
             cdp-capture                    mitmproxy-capture
                    │                               │
                    │                               │
                    └──────────────┬────────────────┘
                                   ▼
                              correlation
                                   │
                                   ▼
                               capture/
```

The important point is that **mitmproxy becomes the authoritative byte-level capture**, while CDP remains the authoritative *browser-context* capture.

Mitmproxy's streaming API is particularly well suited to this: streaming is enabled at `requestheaders` / `responseheaders`, and the body is then forwarded without buffering it in the proxy. ([Mitmproxy Documentation](https://docs.mitmproxy.org/stable/overview/features/?utm_source=chatgpt.com))

## 1. First change: introduce a proxy module

I'd add:

``` text
webapps-scraper/
├── webapps-scraper.py
├── mitmproxy_addon.py       # new
├── capture.py               # new, shared capture format
├── ...
```

But I would **not** make the addon responsible for starting Chrome.

Instead:

``` text
webapps-scraper.py
        │
        ├── start mitmproxy
        │
        ├── start Chrome with --proxy-server
        │
        └── CDP listeners
```

That keeps process lifetime under your control.

------------------------------------------------------------------------

# 2. The mitmproxy addon

There is one important wrinkle in mitmproxy's API.

You can do:

``` python
flow.response.stream = True
```

but once streaming is enabled, mitmproxy intentionally doesn't retain the body in `flow.response.content`. Instead, the stream callback receives chunks. ([Mitmproxy Documentation](https://docs.mitmproxy.org/stable/api/mitmproxy/http.html?utm_source=chatgpt.com))

That's exactly what we want.

So let's use the streaming callback as the disk writer.

I'd start with something like:

``` python
#!/usr/bin/env python3

import json
import os
import time
from pathlib import Path

from mitmproxy import http

class Recorder:
    def __init__(self, output_dir):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.http_dir = self.output_dir / "http"
        self.http_dir.mkdir(exist_ok=True)

        self.counter = 0

    def next_id(self):
        self.counter += 1
        return f"{self.counter:08d}"

    def requestheaders(self, flow: http.HTTPFlow):
        flow.metadata["capture_id"] = self.next_id()

        capture_id = flow.metadata["capture_id"]

        directory = self.http_dir / capture_id
        directory.mkdir()

        metadata = {
            "capture_id": capture_id,
            "timestamp": time.time(),

            "request": {
                "method": flow.request.method,
                "url": flow.request.url,
                "http_version": flow.request.http_version,
                "headers": list(flow.request.headers.items()),
            },
        }

        (directory / "request.json").write_text(
            json.dumps(metadata, indent=2),
            encoding="utf-8",
        )

        request_body = open(
            directory / "request-body.bin",
            "wb",
        )

        flow.metadata["request_body_file"] = request_body

        def stream(chunk):
            if chunk:
                request_body.write(chunk)
                request_body.flush()
            else:
                request_body.close()

            return chunk

        flow.request.stream = stream

    def responseheaders(self, flow: http.HTTPFlow):
        capture_id = flow.metadata.get("capture_id")

        if capture_id is None:
            return

        directory = self.http_dir / capture_id

        metadata = {
            "status_code": flow.response.status_code,
            "reason": flow.response.reason,
            "http_version": flow.response.http_version,
            "headers": list(flow.response.headers.items()),
        }

        (directory / "response.json").write_text(
            json.dumps(metadata, indent=2),
            encoding="utf-8",
        )

        response_body = open(
            directory / "response-body.bin",
            "wb",
        )

        flow.metadata["response_body_file"] = response_body

        def stream(chunk):
            if chunk:
                response_body.write(chunk)
                response_body.flush()
            else:
                response_body.close()

            return chunk

        flow.response.stream = stream

    def error(self, flow: http.HTTPFlow):
        capture_id = flow.metadata.get("capture_id")

        if capture_id is None:
            return

        directory = self.http_dir / capture_id

        (directory / "error.json").write_text(
            json.dumps({
                "error": str(flow.error),
            }, indent=2),
            encoding="utf-8",
        )

def load(loader):
    pass

addons = [
    Recorder("out"),
]
```

**But don't use this exact version yet.** There are two things I'd change before merging it into your project:

1.  request/response bodies need more careful lifecycle handling;
2.  the capture ID should be designed specifically for **CDP ↔ proxy correlation**.

That's the interesting part.

------------------------------------------------------------------------

# 3. Don't correlate by URL

We should **not** do:

``` python
proxy_request.url == cdp_request.url
```

because a page can legitimately have:

``` text
GET /api/foo
GET /api/foo
GET /api/foo
```

simultaneously.

And you can have redirects, retries, service workers, cached requests, etc.

Instead, create a **capture UUID** for every proxy transaction:

``` text
proxy:
    capture_id = 01J...
```

and independently record the relevant CDP information:

``` text
cdp:
    requestId = "1234.56"
    loaderId = "..."
    frameId = "..."
    url = "..."
    timestamp = ...
```

Then later:

``` text
capture_id
    │
    ├── proxy transaction
    │
    └── candidate CDP transactions
```

We can correlate using:

``` text
timestamp
+ URL
+ method
+ host
+ resource type
+ request headers
```

and eventually make the correlation algorithm smarter.

------------------------------------------------------------------------

# 4. Actually, let's exploit a very useful trick

Since **we control Chrome's proxy configuration**, we can add a special correlation header to the browser's requests.

But we don't want to modify the web application's HTTP traffic because that can break things.

So I would *not* inject something like:

``` http
X-Webapps-Scraper-ID: ...
```

into requests.

Instead, mitmproxy itself can assign the ID and we can correlate after the fact.

The proxy sees the actual request and CDP sees the browser event.

That's clean and non-invasive.

------------------------------------------------------------------------

# 5. Preserve your existing CDP capture

Your current code:

``` python
async def responseReceived(args, driver, target):
```

should remain.

But I would modify it so that instead of treating CDP as the primary body storage mechanism, it writes a small event record:

``` json
{
    "timestamp": 123456.789,
    "request_id": "1234.56",
    "url": "https://example.com/foo",
    "status": 200,
    "mime_type": "application/json",
    "resource_type": "XHR"
}
```

Then:

``` text
cdp/
    events.jsonl
```

becomes a **lossy browser event log**.

That is extremely useful later.

------------------------------------------------------------------------

# 6. This solves one of the biggest problems in your current code

Right now you do:

``` python
res = await target.execute_cdp_cmd(
    "Network.getResponseBody",
    args,
)
```

and if Chrome says:

``` text
No resource with given identifier found
```

you simply lose the response. Your current implementation explicitly handles that error by returning. ([GitHub](https://github.com/milahu/webapps-scraper/blob/main/webapps-scraper.py))

After the change:

``` text
CDP succeeds
    │
    └── useful browser metadata

CDP fails
    │
    └── that's OK
          │
          ▼
      proxy still has
      the HTTP body
```

That's exactly the redundancy we want.

------------------------------------------------------------------------

# 7. Make mitmproxy the lossless layer

I'd define a very explicit invariant:

### CDP

``` text
best effort
lossy
browser semantics
```

### mitmproxy

``` text
authoritative
lossless
HTTP bytes
```

So the data model becomes:

``` text
capture/
│
├── http/
│   ├── 00000001/
│   │   ├── request.json
│   │   ├── request-body.bin
│   │   ├── response.json
│   │   └── response-body.bin
│   │
│   └── ...
│
├── cdp/
│   └── events.jsonl
│
└── index.jsonl
```

And `index.jsonl` is where we eventually store the correlation:

``` json
{
    "capture_id": "00000001",
    "cdp_request_ids": [
        "1234.1"
    ]
}
```

------------------------------------------------------------------------

# 8. We should also capture *headers before streaming*

This is important.

Mitmproxy says the streaming flag must be set in `requestheaders` or `responseheaders`; setting it later is too late because the body may already have been buffered. ([Mitmproxy Documentation](https://docs.mitmproxy.org/stable/api/mitmproxy/http.html?utm_source=chatgpt.com))

So:

``` python
def responseheaders(flow):
    flow.response.stream = ...
```

is the correct architecture.

And we should **never** do:

``` python
def response(flow):
    body = flow.response.content
```

for our lossless recorder.

The whole point is that `response()` happens after the streamed body has already passed through.

Mitmproxy documents this explicitly: with response streaming, the `response` event occurs after the body has been streamed. ([Mitmproxy Documentation](https://docs.mitmproxy.org/stable/api/events.html?utm_source=chatgpt.com))

------------------------------------------------------------------------

# 9. One change I'd make to the storage format

I'd actually avoid:

``` text
response-body.bin
```

for zero-length bodies.

Instead:

``` text
00000001/
    request.json
    response.json
    request-body
    response-body
```

where empty files are perfectly valid.

That means every HTTP exchange has the same shape.

And importantly:

``` text
Content-Length: 0
```

should **not** cause us to skip the response.

Your current CDP implementation explicitly skips responses with:

``` python
if content_length == 0:
    return
```

which is reasonable for your original scraper, but the proxy layer should not do this. ([GitHub](https://github.com/milahu/webapps-scraper/blob/main/webapps-scraper.py))

------------------------------------------------------------------------

# 10. Your Nix environment

I also noticed your project is deliberately using a Nix shell and packages `aiohttp-chromium`, `selenium-driverless`, and `cdp-socket` through `shell.nix`. ([GitHub](https://github.com/milahu/webapps-scraper/blob/main/shell.nix))

So I would integrate mitmproxy **there**, rather than introducing another installation mechanism.

Something along the lines of:

``` nix
python = pkgs.python3.withPackages (pythonPackages:
  (with pythonPackages; [
    aiohttp
    mitmproxy
    legacy-cgi
  ])
  ++
  (with extraPythonPackages; [
    aiohttp-chromium
    selenium-driverless
    cdp-socket
  ])
);
```

Whether `pkgs.python3Packages.mitmproxy` is available in the particular nixpkgs revision you're using is something I'd verify before committing this exact expression.

------------------------------------------------------------------------

# 11. Chrome needs one additional argument

We want:

``` python
--proxy-server=http://127.0.0.1:<port>
```

and, initially, I'd also use:

``` python
--disable-quic
```

The latter is important because otherwise Chrome may use HTTP/3/QUIC, which isn't necessarily going through the ordinary HTTP proxy path we want to capture.

So the process becomes:

``` text
webapps-scraper.py
        │
        ├── choose free localhost port
        │
        ├── start mitmproxy
        │
        ├── wait until proxy is ready
        │
        ├── start aiohttp_chromium
        │      └── --proxy-server=http://127.0.0.1:PORT
        │
        └── install CDP listeners
```

------------------------------------------------------------------------

# 12. And I think we should use mitmdump, not mitmproxy

For your use case:

``` bash
mitmproxy
```

would give us an interactive proxy UI that we don't need.

I'd use:

``` bash
mitmdump
```

programmatically.

Something like:

``` python
process = await asyncio.create_subprocess_exec(
    "mitmdump",
    "--listen-host", "127.0.0.1",
    "--listen-port", str(port),
    "--set", "ssl_insecure=false",
    "-s", "mitmproxy_addon.py",
)
```

Then your only GUI is Chrome.

This is a much cleaner user experience.

------------------------------------------------------------------------

# 13. CA certificate handling

For HTTPS interception, mitmproxy needs its CA trusted by Chrome.

The first time mitmproxy runs, it creates its CA under its configuration directory.

I'd **not** install the CA globally into the operating system.

Instead:

``` text
capture/session/
    chrome-profile/
```

and configure Chrome with a session-specific profile / trust setup.

There are several ways to do this, and this is one part where I would like to be careful because Chrome's Linux certificate trust behavior varies depending on the Chromium build and NSS/system trust configuration.

For a first prototype, we can make the recorder explicitly use a generated CA and a dedicated Chrome profile.

------------------------------------------------------------------------

# 14. One more thing: anticache

This is worth enabling.

Mitmproxy has an `anticache` facility which strips:

``` text
If-None-Match
If-Modified-Since
```

so that the server is less likely to respond with:

``` text
304 Not Modified
```

instead of the actual resource. The mitmproxy documentation explicitly describes anticache as useful when you want to capture an HTTP exchange in its entirety. ([GitHub](https://github.com/mitmproxy/mitmproxy/blob/main/docs/src/content/overview/features.md?utm_source=chatgpt.com))

But I would make this **optional**:

``` bash
--anticache
```

rather than silently modifying traffic.

For faithful recording, the default should probably be:

``` text
do not modify requests
```

and an optional:

``` text
capture-complete-resources mode
```

can enable anticache.

------------------------------------------------------------------------

# 15. I suggest we do this incrementally

Rather than immediately rewriting `webapps-scraper.py`, I'd make the first commit extremely small:

``` text
commit 1
========

Add mitmproxy dependency
Add mitmproxy_addon.py
Add standalone streaming HTTP recorder
```

Then test:

``` bash
mitmdump -s mitmproxy_addon.py
```

with:

``` bash
curl -x http://127.0.0.1:8080 https://example.com
```

and verify:

``` text
out/
└── http/
    └── 00000001/
        ├── request.json
        ├── request-body
        ├── response.json
        └── response-body
```

**before involving Chrome at all.**

Then:

``` text
commit 2
========

Start mitmdump from webapps-scraper.py
Configure Chrome proxy
```

Then:

``` text
commit 3
========

Add CDP event logging
```

Then:

``` text
commit 4
========

CDP ↔ mitmproxy correlation
```

This gives us very small, testable steps.

------------------------------------------------------------------------

## One correction to my previous answer

After inspecting your actual repository, I'd change one detail from what I suggested earlier.

I **wouldn't immediately make the proxy addon write directly from the stream callback into the final capture file without first defining the capture lifecycle carefully**.

Mitmproxy's streaming callback gets chunks, but those chunks are not guaranteed to correspond to network packet/frame boundaries; the API explicitly warns about this. ([Mitmproxy Documentation](https://docs.mitmproxy.org/stable/api/mitmproxy/http.html?utm_source=chatgpt.com))

That's fine for our purpose - we're reconstructing the HTTP body, not packet-capturing - but we should make the recorder's semantics explicit:

``` text
body file = exact logical HTTP message body
             reconstructed from stream chunks
```

rather than:

``` text
body file = packets
```

That's actually exactly what we want for later web-app extraction.

------------------------------------------------------------------------

### So I propose the next concrete step

**Let's implement commit \#1 against your actual repo structure:**

``` text
nix/
shell.nix
webapps-scraper.py
```

adding:

``` text
mitmproxy_addon.py
```

with:

- lossless request-body streaming
- lossless response-body streaming
- JSON metadata
- monotonically increasing capture IDs
- error recording
- no body buffering
- no CDP changes yet
- no Chrome changes yet

Then we can wire it into `webapps-scraper.py` in the next step.

That keeps the existing scraper working while we establish that the **mitmproxy capture layer itself really is lossless for arbitrarily large HTTP bodies**. ([Mitmproxy Documentation](https://docs.mitmproxy.org/stable/overview/features/?utm_source=chatgpt.com))

------------------------------------------------------------------------

**Sources:**

- [webapps-scraper/webapps-scraper.py at main · milahu/webapps-scraper · GitHub](https://github.com/milahu/webapps-scraper/blob/main/webapps-scraper.py)
- [Features](https://docs.mitmproxy.org/stable/overview/features/?utm_source=chatgpt.com)

------------------------------------------------------------------------

Powered by [ChatGPT Exporter](https://www.chatgptexporter.com)
