import asyncio

import pytest
from fastapi import FastAPI

from routers.translate import register_translate


@pytest.mark.asyncio
async def test_translate_shutdown_cancels_background_tasks_and_closes_tm(tmp_path):
    state = register_translate(
        FastAPI(),
        cloud_only=False,
        load_config=lambda: {},
        save_config=lambda value: None,
        build_cloud_client=lambda *args, **kwargs: None,
        mask_api_key=lambda value: value,
        is_masked=lambda value: False,
        validate_file_path=lambda value: value,
        runtime_dir=tmp_path,
        rag_store_getter=lambda: None,
    )
    sleeper = asyncio.create_task(asyncio.sleep(60))
    state["background_tasks"].add(sleeper)

    await state["shutdown"]()

    assert sleeper.cancelled()
    assert not state["background_tasks"]
    assert state["tm_store"]._conn is None
