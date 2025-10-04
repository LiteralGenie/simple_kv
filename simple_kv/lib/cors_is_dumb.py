from litestar.datastructures import Headers, MutableScopeHeaders
from litestar.enums import ScopeType
from litestar.middleware import ASGIMiddleware


class MyCorsMiddleware(ASGIMiddleware):
    scopes = (ScopeType.HTTP, ScopeType.ASGI)

    async def handle(self, scope, receive, send, next_app) -> None:
        async def send_wrapper(message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableScopeHeaders.from_message(message=message)
                headers["Access-Control-Allow-Origin"] = (
                    Headers.from_scope(scope=scope).get("origin") or "*"
                )
                headers["Access-Control-Allow-Credentials"] = "true"
                headers["Access-Control-Allow-Headers"] = "Content-Type, Accept"
                print("here", Headers.from_scope(scope=scope).get("origin"))
            await send(message)

        await next_app(scope, receive, send_wrapper)
