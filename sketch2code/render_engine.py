import asyncio
from typing import List

import imageio
from pyppeteer import launch
from pyppeteer.browser import Browser
from pyppeteer.page import Page

from sketch2code.data_model import Tag


def patch_pyppeteer():
    import pyppeteer.connection
    original_method = pyppeteer.connection.websockets.client.connect

    def new_method(*args, **kwargs):
        kwargs['ping_interval'] = None
        kwargs['ping_timeout'] = None
        return original_method(*args, **kwargs)

    pyppeteer.connection.websockets.client.connect = new_method


patch_pyppeteer()


class RenderEngine:

    instance = None

    def __init__(self, browser: Browser, pages: List[Page]):
        self.browser = browser
        self.pages = pages
        self.n_pages = len(pages)

    def __del__(self):
        asyncio.get_event_loop().run_until_complete(self.async_shutdown())

    @staticmethod
    def get_instance(template_html: str, n_cpu: int = 16, viewport_width: int = 800, viewport_height: int = 600):
        if RenderEngine.instance is None:
            browser, pages = asyncio.get_event_loop().run_until_complete(
                RenderEngine.async_init(template_html, n_cpu, viewport_width, viewport_height))

            RenderEngine.instance = RenderEngine(browser, pages)
        return RenderEngine.instance

    def render_pages(self, tags: List[Tag], format='jpeg'):
        return asyncio.get_event_loop().run_until_complete(self.async_render_pages(tags, format))

    @staticmethod
    async def async_init(template_html: str, n_cpu: int, viewport_width: int, viewport_height: int):
        browser = await launch(headless=True)
        pages = []

        for i in range(n_cpu):
            page = await browser.newPage()
            await page.setViewport({"width": viewport_width, "height": viewport_height})
            await page.setContent(template_html)
            pages.append(page)

        return browser, pages

    async def async_shutdown(self):
        # for page in reversed(self.pages):
        #     await page.close()
        await self.browser.close()

    async def async_render_pages(self, tags: List[Tag], format='jpeg'):
        event_loop = asyncio.get_event_loop()
        pages, n_pages = self.pages, self.n_pages
        tasks = []
        results = []

        for i, tag in enumerate(tags):
            task = event_loop.create_task(RenderEngine.async_render_page(pages[i % n_pages], tag.to_body(), format))
            tasks.append(task)

            if len(tasks) == n_pages:
                results += await asyncio.gather(*tasks)
                tasks = []

        if len(tasks) > 0:
            results += await asyncio.gather(*tasks)

        return results

    @staticmethod
    async def async_render_page(page: Page, body: str, format: str = 'jpeg'):
        await page.evaluate('(x) => {document.body.innerHTML = x;}', body)
        result = await page.screenshot({'fullPage': True, 'type': format})
        return imageio.imread(result)


if __name__ == '__main__':
    import time, ujson, h5py, numpy as np
    from sketch2code.config import ROOT_DIR

    with open(ROOT_DIR / "datasets/pix2code/data.json", "r") as f:
        tags = [Tag.deserialize(o) for o in ujson.load(f)]

    start = time.time()
    render_engine = RenderEngine.get_instance(tags[0].to_html(), 32)
    print(f"Start up take: {time.time() - start:.4f} seconds")

    start = time.time()
    results = render_engine.render_pages(tags)
    print(f"Render a page take: {(time.time() - start) / len(results):.4f} seconds. ({len(tags)} pages)")

    start = time.time()
    print("max-width:", max(x.shape[0] for x in results), "max-height:", max(x.shape[1] for x in results))
    # results = np.asarray(results)
    # with h5py.File(ROOT_DIR / "datasets/pix2code/data.hdf5", "w") as f:
    #     dataset = f.create_dataset("images", results.shape, dtype='f')
    # # for i, example in enumerate(results):
    # #     with open(f"./tmp/example_{i}.jpg", "wb") as f:
    # #         f.write(example)
    print(f"Misc process take: {time.time() - start:.4f} seconds")