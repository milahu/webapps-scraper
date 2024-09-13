#!/usr/bin/env python3

import asyncio
import sys
import os
import json
import base64
import logging
import cdp_socket
import urllib.parse



output_path = "out"



# TODO better?

logging_level = "INFO"
#if options.debug:
if True:
    # TODO disable debug log from selenium (too verbose)
    logging_level = "DEBUG"

logging.basicConfig(
    #format='%(asctime)s %(levelname)s %(message)s',
    # also log the logger %(name)s, so we can filter by logger name
    format='%(asctime)s %(name)s %(levelname)s %(message)s',
    level=logging_level,
)

#logger = logging.getLogger("aiohttp_chromium")
logger = logging.getLogger(__name__)



#import aiohttp
sys.path.append("aiohttp_chromium/src")
#sys.path.append("aiohttp_chromium/stable-main/src")
import aiohttp_chromium as aiohttp



async def responseReceived(args, driver, target):

    #logger.debug(f"responseReceived {json.dumps(args, indent=2)}")

    response_data = args
    response_url = args["response"]["url"]
    response_status = args["response"]["status"]
    request_id = args["requestId"]

    if response_url.startswith("data:"):
        # captcha?
        return

    if response_url.startswith("blob:"):
        # file download from javascript
        return

    content_length = response_data["response"]["headers"].get("content-length", None)
    if content_length != None:
        content_length = int(content_length)

    if content_length == 0:
        return

    # NOTE content can be empty when content_length == None
    # or content_length can be wrong
    logger.debug(f"responseReceived {request_id} Network.getResponseBody ...")
    args = {
        "requestId": args["requestId"],
    }
    res = None
    try:
        res = await target.execute_cdp_cmd("Network.getResponseBody", args)
        logger.debug(f"responseReceived {request_id} Network.getResponseBody done")
    except cdp_socket.exceptions.CDPError as e:
        # {'code': -32000, 'message': 'No resource with given identifier found'}
        if e.code == -32000:
            logger.debug(f"responseReceived {request_id} Network.getResponseBody failed: {e}")
        else:
            raise
    if res == None:
        return
    response_body = base64.b64decode(res["body"]) if res["base64Encoded"] else res["body"]
    logger.debug(f"responseReceived {request_id} Network.getResponseBody -> {type(response_body)} {response_body[:100]}...")
    # TODO better
    response_body_path = response_url.replace("https://", "").replace("http://", "")
    response_body_path = urllib.parse.unquote(response_body_path) # "%20" -> " ", etc
    response_body_path = output_path + "/" + response_body_path
    logger.debug(f"responseReceived {request_id} writing {response_body_path}")
    os.makedirs(os.path.dirname(response_body_path), exist_ok=True)
    open_mode = "wb" if type(response_body) == bytes else "w"
    with open(response_body_path, open_mode) as f:
        f.write(response_body)



async def main():
    async with aiohttp.ClientSession() as session:
        #url = "https://boxy-svg.com/app"
        url = sys.argv[1]

        args = dict(
            listeners=dict(
                responseReceived=responseReceived,
            ),
        )

        async with session.get(url, **args) as response:
            logger.debug(response.status)
            logger.debug(await response.text())

            logger.debug("sleep")
            await asyncio.sleep(99999)

asyncio.run(main())
