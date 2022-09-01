import random

import aiohttp
from aiohttp import web

from models import manager, User, Query, migrate

TEXTS_LIMIT_PER_REQUEST = 10
TEXT_MAX_LENGTH = 1000
TAGGERS_URLS = [
    'http://127.0.0.1:5000/internal/tagging',
    'http://127.0.0.1:5001/internal/tagging',
]
ATTEMPTS = 5


async def validate_api_key(request: web.Request) -> (User, str):
    api_key = request.query.get('api_key')
    if not api_key:
        return None, 'You should pass API key'
    try:
        user = await manager.get(User, api_key=api_key)
    except User.DoesNotExist:
        return None, 'Wrong API key'
    if not user.active:
        return user, 'API key deactivate'
    return user, None


def is_valid_request(request_body: dict) -> bool:
    return not (
        not isinstance(request_body, dict) or
        'texts' not in request_body or
        not isinstance(request_body['texts'], list) or
        len(request_body['texts']) > TEXTS_LIMIT_PER_REQUEST or
        any(
            not isinstance(text, str) or len(text) > TEXT_MAX_LENGTH
            for text in request_body['texts']
        )
    )


async def route_request(request_body: dict) -> (int, dict):
    async with aiohttp.ClientSession() as session:
        for attempt in range(ATTEMPTS):
            tagger_url = random.choice(TAGGERS_URLS)
            try:
                response = await session.post(tagger_url, json=request_body)
            except Exception:
                continue
            if response.status < 500:
                break
        else:
            return 500, {'error': 'Internal error'}

        try:
            response_data = await response.json()
        except:
            return 500, {'error': 'Internal error'}
        else:
            return response.status, response_data


async def handle_tagging(request: web.Request):
    """
    Request:

    POST /tagging?api_key=123 HTTP/1.1
    Content-Type: application/json
    Content-Length: 94

    {
        "texts": [
            "text1",
            "text2",
            ...
        ]
    }

    Response:

    HTTP/1.1 200 OK
    Content-Type: application/json
    Content-Length: 94

    {
        "tags": [
            ["text1-tag1", "text1-tag2", ...],
            ["text2-tag1", "text2-tag2", ...],
            ...
        ]
    }
    """
    user, error_text = await validate_api_key(request)
    if error_text is not None:
        return web.json_response(status=403, data={'error': error_text})

    try:
        request_body = await request.json()
    except Exception:
        return web.json_response(status=400, data={'error': 'Expected JSON body'})
    if not is_valid_request(request_body):
        return web.json_response(status=400, data={'error': 'Wrong body format'})

    status, response = await route_request(request_body)
    await manager.create(Query, user=user, request=request_body, response=response)
    return web.json_response(status=status, data=response)


def make_app():
    migrate()

    app = web.Application()
    app.add_routes([
        web.post('/tagging', handle_tagging)
    ])

    return app


if __name__ == '__main__':
    web.run_app(make_app())