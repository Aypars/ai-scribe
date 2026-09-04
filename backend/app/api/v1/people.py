from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.repositories import meetings as meetings_repo
from app.repositories import people as people_repo
from app.schemas.person import PersonCreate, PersonListOut, PersonOut, PersonUpdate

router = APIRouter()


@router.get("", response_model=PersonListOut)
def list_people(
    meeting_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PersonListOut:
    if meeting_id is not None:
        meeting = meetings_repo.get_for_user(db, current_user.user_id, meeting_id)
        if meeting is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Toplantı bulunamadı")
        return PersonListOut(items=people_repo.list_out_for_meeting(db, current_user.user_id, meeting_id))
    return PersonListOut(items=people_repo.list_out_for_user(db, current_user.user_id))


@router.post("", response_model=PersonOut, status_code=status.HTTP_201_CREATED)
def create_person(
    body: PersonCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PersonOut:
    try:
        person = people_repo.create_person(
            db,
            user_id=current_user.user_id,
            name=body.name,
            note=body.note,
        )
    except people_repo.PersonNameConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.detail) from exc
    return people_repo.to_out_in_directory(db, current_user.user_id, person)


@router.patch("/{person_id}", response_model=PersonOut)
def update_person(
    person_id: int,
    body: PersonUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PersonOut:
    person = people_repo.get_for_user(db, current_user.user_id, person_id)
    if person is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kişi bulunamadı")
    try:
        person = people_repo.update_person(
            db,
            person,
            name=body.name,
            note_set="note" in body.model_fields_set,
            note=body.note,
        )
    except people_repo.PersonNameConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.detail) from exc
    return people_repo.to_out_in_directory(db, current_user.user_id, person)


@router.delete("/{person_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_person(
    person_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    person = people_repo.get_for_user(db, current_user.user_id, person_id)
    if person is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kişi bulunamadı")
    people_repo.delete_person(db, person)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
