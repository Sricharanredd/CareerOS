from __future__ import annotations

from fastapi import Query, Response

from app.core.deps import CurrentOwner, DbSession, Pagination
from app.core.errors import ConflictError
from app.core.routing import CommittingAPIRouter
from app.repositories import company as company_repo
from app.schemas.common import Page
from app.schemas.company import CompanyCreate, CompanyOption, CompanyUpdate, CompanyView
from app.services import company as company_service

router = CommittingAPIRouter(prefix="/companies", tags=["companies"])


def _view(company, counts: tuple[int, int] = (0, 0)) -> CompanyView:
    view = CompanyView.model_validate(company)
    view.application_count, view.job_description_count = counts
    return view


@router.get("", response_model=Page[CompanyView])
def list_companies(
    owner: CurrentOwner,
    db: DbSession,
    page: Pagination,
    search: str | None = Query(default=None, max_length=120),
    include_archived: bool = False,
    sort: str = Query(default="name", pattern="^-?(name|created_at)$"),
):
    items, total = company_repo.list_page(
        db,
        owner.id,
        search=search,
        include_archived=include_archived,
        sort=sort,
        page=page.page,
        page_size=page.page_size,
    )
    counts = company_repo.counts(db, owner.id, [c.id for c in items])
    return Page[CompanyView](
        items=[_view(company, counts.get(company.id, (0, 0))) for company in items],
        total=total,
        page=page.page,
        page_size=page.page_size,
    )


@router.get("/options", response_model=list[CompanyOption])
def company_options(owner: CurrentOwner, db: DbSession):
    return [CompanyOption.model_validate(row) for row in company_repo.list_options(db, owner.id)]


@router.post("", response_model=CompanyView, status_code=201)
def create_company(payload: CompanyCreate, owner: CurrentOwner, db: DbSession):
    company = company_service.create(db, owner.id, payload)
    return _view(company)


@router.get("/{company_id}", response_model=CompanyView)
def get_company(company_id: str, owner: CurrentOwner, db: DbSession):
    company = company_repo.get(db, owner.id, company_id)
    if company is None:
        from app.core.errors import NotFoundError

        raise NotFoundError("Company not found.")
    return _view(company, company_repo.usage(db, company.id))


@router.patch("/{company_id}", response_model=CompanyView)
def update_company(company_id: str, payload: CompanyUpdate, owner: CurrentOwner, db: DbSession):
    company = company_service.update(db, owner.id, company_id, payload)
    return _view(company, company_repo.usage(db, company.id))


@router.post("/{company_id}/archive", response_model=CompanyView)
def archive_company(company_id: str, owner: CurrentOwner, db: DbSession, archived: bool = True):
    company = company_service.set_archived(db, owner.id, company_id, archived)
    return _view(company, company_repo.usage(db, company.id))


@router.delete("/{company_id}", status_code=204)
def delete_company(company_id: str, owner: CurrentOwner, db: DbSession):
    from app.core.errors import NotFoundError

    company = company_repo.get(db, owner.id, company_id)
    if company is None:
        raise NotFoundError("Company not found.")
    applications, job_descriptions = company_repo.usage(db, company.id)
    if applications or job_descriptions:
        raise ConflictError(
            "This company has job descriptions or applications. Archive it instead.",
            code="in_use",
            details={"applications": applications, "job_descriptions": job_descriptions},
        )
    db.delete(company)
    db.flush()
    return Response(status_code=204)
