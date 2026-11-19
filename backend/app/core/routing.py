"""Route base class that commits the request transaction before responding.

FastAPI runs the teardown of ``yield`` dependencies *after* the response has been
sent. That means a client which immediately refetches a collection (for example
right after creating a task) can race the commit and read stale rows. Committing
inside the route handler, once serialization has happened, closes that window.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.routing import APIRoute


class CommitBeforeResponseRoute(APIRoute):
    """Commit the request-scoped session before the response leaves the app."""

    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            response = await original(request)
            session = getattr(request.state, "db_session", None)
            if session is not None and session.in_transaction():
                session.commit()
            return response

        return handler


class CommittingAPIRouter(APIRouter):
    """APIRouter whose routes use :class:`CommitBeforeResponseRoute`."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("route_class", CommitBeforeResponseRoute)
        super().__init__(*args, **kwargs)
