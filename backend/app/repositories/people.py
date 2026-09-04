from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.action import Action
from app.models.meeting import Meeting
from app.models.meeting_person import MeetingPerson
from app.models.person import Person
from app.models.task import Task
from app.models.transcript import Transcript
from app.schemas.person import PersonOut, PersonMeetingOut
from app.services.turkish import lower_tr


class PersonNameConflict(Exception):
    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


def names_match(left: str | None, right: str | None) -> bool:
    return lower_tr((left or "").strip()) == lower_tr((right or "").strip())


def _label(person: Person, *, duplicate_index: int | None = None) -> str:
    base = f"{person.name} · {person.note}" if person.note else person.name
    if duplicate_index is not None:
        return f"{base} · #{duplicate_index}"
    return base


def to_out(
    person: Person,
    *,
    attendee: bool = False,
    duplicate_index: int | None = None,
    meetings: list[PersonMeetingOut] | None = None,
) -> PersonOut:
    return PersonOut(
        person_id=person.person_id,
        name=person.name,
        note=person.note,
        label=_label(person, duplicate_index=duplicate_index),
        attendee=attendee,
        meetings=meetings or [],
    )


def _duplicate_indexes(rows: list[Person]) -> dict[int, int | None]:
    groups: dict[tuple[str, str], list[Person]] = {}
    for row in rows:
        key = (row.name.casefold(), (row.note or "").casefold())
        groups.setdefault(key, []).append(row)
    indexes: dict[int, int | None] = {}
    for members in groups.values():
        members.sort(key=lambda person: person.person_id)
        if len(members) == 1:
            indexes[members[0].person_id] = None
            continue
        for index, person in enumerate(members, start=1):
            indexes[person.person_id] = index
    return indexes


def to_out_in_directory(db: Session, user_id: int, person: Person, *, attendee: bool = False) -> PersonOut:
    indexes = _duplicate_indexes(list_for_user(db, user_id))
    meetings = _meetings_by_person_id(db, user_id)
    return to_out(
        person,
        attendee=attendee,
        duplicate_index=indexes.get(person.person_id),
        meetings=meetings.get(person.person_id, []),
    )


def list_for_user(db: Session, user_id: int) -> list[Person]:
    return list(
        db.scalars(select(Person).where(Person.user_id == user_id).order_by(Person.name, Person.person_id)).all()
    )


def prune_unassigned_people(db: Session) -> None:
    # Directory people stay even if they have no tasks or meetings.
    return


def _meetings_by_person_id(db: Session, user_id: int) -> dict[int, list[PersonMeetingOut]]:
    grouped: dict[int, dict[int, PersonMeetingOut]] = {}

    def add(person_id: int | None, meeting_id: int, title: str, date) -> None:
        if person_id is None:
            return
        bucket = grouped.setdefault(person_id, {})
        if meeting_id in bucket:
            return
        bucket[meeting_id] = PersonMeetingOut(
            meeting_id=meeting_id,
            title=title,
            date=date.isoformat() if date is not None else None,
        )

    for person_id, meeting_id, title, date in db.execute(
        select(MeetingPerson.person_id, Meeting.meeting_id, Meeting.title, Meeting.date)
        .join(Meeting, Meeting.meeting_id == MeetingPerson.meeting_id)
        .where(Meeting.user_id == user_id)
    ).all():
        add(person_id, meeting_id, title, date)

    for person_id, meeting_id, title, date in db.execute(
        select(Task.assignee_id, Meeting.meeting_id, Meeting.title, Meeting.date)
        .join(Meeting, Meeting.meeting_id == Task.meeting_id)
        .where(Meeting.user_id == user_id, Task.assignee_id.isnot(None))
    ).all():
        add(person_id, meeting_id, title, date)

    out: dict[int, list[PersonMeetingOut]] = {}
    for person_id, by_id in grouped.items():
        items = list(by_id.values())
        items.sort(key=lambda row: (row.date or "", row.meeting_id), reverse=True)
        out[person_id] = items
    return out


def list_out_for_user(db: Session, user_id: int) -> list[PersonOut]:
    rows = list_for_user(db, user_id)
    indexes = _duplicate_indexes(rows)
    meetings = _meetings_by_person_id(db, user_id)
    return [
        to_out(
            row,
            duplicate_index=indexes.get(row.person_id),
            meetings=meetings.get(row.person_id, []),
        )
        for row in rows
    ]


def get_for_user(db: Session, user_id: int, person_id: int) -> Person | None:
    person = db.get(Person, person_id)
    if person is None or person.user_id != user_id:
        return None
    return person


def find_by_name(
    db: Session,
    user_id: int,
    name: str,
    *,
    exclude_id: int | None = None,
) -> Person | None:
    needle = lower_tr((name or "").strip())
    if not needle:
        return None
    for person in list_for_user(db, user_id):
        if exclude_id is not None and person.person_id == exclude_id:
            continue
        if lower_tr(person.name) == needle:
            return person
    return None


def _assert_name_available(db: Session, user_id: int, name: str, *, exclude_id: int | None = None) -> None:
    if find_by_name(db, user_id, name, exclude_id=exclude_id) is not None:
        raise PersonNameConflict("Bu isimde biri zaten var")


def speaker_name_taken(meeting: Meeting, name: str, aliases: list[str] | None = None) -> bool:
    target = lower_tr((name or "").strip())
    if not target:
        return False
    skip = {lower_tr(alias.strip()) for alias in (aliases or []) if alias and alias.strip()}
    for row in meeting.transcripts:
        speaker = (row.speaker or "").strip()
        if not speaker:
            continue
        key = lower_tr(speaker)
        if key == target and key not in skip:
            return True
    return False


def person_for_speaker(db: Session, meeting_id: int, speaker: str) -> Person | None:
    needle = (speaker or "").strip()
    if not needle:
        return None
    for link, person in meeting_people(db, meeting_id):
        if names_match(person.name, needle) or names_match(link.speaker_label, needle):
            return person
    return match_meeting_person(db, meeting_id, needle)


def _person_meeting_ids(db: Session, person_id: int) -> set[int]:
    ids = _linked_meeting_ids(db, person_id)
    ids.update(db.scalars(select(Task.meeting_id).where(Task.assignee_id == person_id)).all())
    ids.update(db.scalars(select(Action.meeting_id).where(Action.assignee_id == person_id)).all())
    return ids


def _meetings_for_person(db: Session, user_id: int, person_id: int) -> list[Meeting]:
    ids = _person_meeting_ids(db, person_id)
    if not ids:
        return []
    return list(
        db.scalars(
            select(Meeting)
            .options(selectinload(Meeting.transcripts))
            .where(Meeting.user_id == user_id, Meeting.meeting_id.in_(ids))
        ).all()
    )


def _aliases_for_person(db: Session, person: Person, old_name: str | None) -> list[str]:
    aliases: list[str] = []
    seen: set[str] = set()

    def add(value: str | None) -> None:
        name = (value or "").strip()
        key = lower_tr(name)
        if not name or key in seen:
            return
        seen.add(key)
        aliases.append(name)

    add(old_name)
    add(person.name)
    for link in db.scalars(select(MeetingPerson).where(MeetingPerson.person_id == person.person_id)).all():
        add(link.speaker_label)
    return aliases


def _copy_assignee_name(db: Session, person_id: int, name: str) -> None:
    for action in db.scalars(select(Action).where(Action.assignee_id == person_id)).all():
        action.assignee = name
    for task in db.scalars(select(Task).where(Task.assignee_id == person_id)).all():
        task.assignee = name


def _assert_meetings_accept_name(
    db: Session,
    user_id: int,
    person: Person,
    new_name: str,
    aliases: list[str],
) -> None:
    for meeting in _meetings_for_person(db, user_id, person.person_id):
        if speaker_name_taken(meeting, new_name, aliases):
            raise PersonNameConflict(
                f"Bu isim “{meeting.title}” toplantısında başka bir konuşmacıda kullanılıyor"
            )


def update_person(
    db: Session,
    person: Person,
    *,
    name: str | None = None,
    note_set: bool = False,
    note: str | None = None,
) -> Person:
    from app.repositories import meetings as meetings_repo

    if name is not None:
        new_name = name.strip()
        if not new_name:
            raise PersonNameConflict("İsim gerekli")
        old_name = person.name
        aliases = _aliases_for_person(db, person, old_name)
        if not names_match(new_name, old_name):
            _assert_name_available(db, person.user_id, new_name, exclude_id=person.person_id)
            _assert_meetings_accept_name(db, person.user_id, person, new_name, aliases)
        person.name = new_name
        _copy_assignee_name(db, person.person_id, person.name)
        mapping = {alias: person.name for alias in aliases if alias != person.name}
        if mapping:
            for meeting in _meetings_for_person(db, person.user_id, person.person_id):
                meetings_repo.replace_speaker_names(db, meeting, mapping, commit=False)
    if note_set:
        person.note = (note or "").strip() or None
    db.commit()
    db.refresh(person)
    return person


def create_person(db: Session, *, user_id: int, name: str, note: str | None = None) -> Person:
    cleaned = name.strip()
    _assert_name_available(db, user_id, cleaned)
    person = Person(user_id=user_id, name=cleaned, note=(note or "").strip() or None)
    db.add(person)
    db.commit()
    db.refresh(person)
    return person


def create_person_flush(db: Session, *, user_id: int, name: str, note: str | None = None) -> Person:
    cleaned = name.strip()
    existing = find_by_name(db, user_id, cleaned)
    extra = (note or "").strip() or None
    if existing is not None:
        if extra and not existing.note:
            existing.note = extra
        return existing
    person = Person(user_id=user_id, name=cleaned, note=extra)
    db.add(person)
    db.flush()
    return person


def delete_person(db: Session, person: Person) -> None:
    db.delete(person)
    db.commit()


def meeting_people(db: Session, meeting_id: int) -> list[tuple[MeetingPerson, Person]]:
    stmt = (
        select(MeetingPerson, Person)
        .join(Person, Person.person_id == MeetingPerson.person_id)
        .where(MeetingPerson.meeting_id == meeting_id)
        .order_by(Person.name, Person.person_id)
    )
    return list(db.execute(stmt).all())


def list_out_for_meeting(db: Session, user_id: int, meeting_id: int) -> list[PersonOut]:
    rows = [person for _link, person in meeting_people(db, meeting_id) if person.user_id == user_id]
    indexes = _duplicate_indexes(list_for_user(db, user_id))
    return [to_out(row, attendee=True, duplicate_index=indexes.get(row.person_id)) for row in rows]


def link_attendee(db: Session, meeting_id: int, person_id: int, speaker_label: str | None) -> None:
    existing = db.get(MeetingPerson, (meeting_id, person_id))
    if existing is None:
        db.add(MeetingPerson(meeting_id=meeting_id, person_id=person_id, speaker_label=speaker_label))
        return
    if speaker_label and not existing.speaker_label:
        existing.speaker_label = speaker_label


def speaker_labels(rows: list) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for row in rows:
        name = (getattr(row, "speaker", None) or "").strip()
        key = name.casefold()
        if not name or key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def _linked_meeting_ids(db: Session, person_id: int) -> set[int]:
    return set(db.scalars(select(MeetingPerson.meeting_id).where(MeetingPerson.person_id == person_id)).all())


def _repoint_assignees(db: Session, from_id: int, to_id: int) -> None:
    if from_id == to_id:
        return
    for action in db.scalars(select(Action).where(Action.assignee_id == from_id)).all():
        action.assignee_id = to_id
    for task in db.scalars(select(Task).where(Task.assignee_id == from_id)).all():
        task.assignee_id = to_id


def _merge_person_into(db: Session, keep: Person, drop: Person) -> None:
    if keep.person_id == drop.person_id:
        return
    if not keep.note and drop.note:
        keep.note = drop.note
    drop_links = list(db.scalars(select(MeetingPerson).where(MeetingPerson.person_id == drop.person_id)).all())
    for link in drop_links:
        existing = db.get(MeetingPerson, (link.meeting_id, keep.person_id))
        if existing is None:
            db.add(
                MeetingPerson(
                    meeting_id=link.meeting_id,
                    person_id=keep.person_id,
                    speaker_label=link.speaker_label,
                )
            )
        elif not existing.speaker_label and link.speaker_label:
            existing.speaker_label = link.speaker_label
        db.delete(link)
    db.flush()
    _repoint_assignees(db, drop.person_id, keep.person_id)
    db.flush()
    db.delete(drop)
    db.flush()


def _only_used_in_meeting(db: Session, person_id: int, meeting_id: int) -> bool:
    linked = _linked_meeting_ids(db, person_id)
    if linked and linked != {meeting_id}:
        return False
    other_action = db.scalars(
        select(Action.meeting_id).where(Action.assignee_id == person_id, Action.meeting_id != meeting_id).limit(1)
    ).first()
    if other_action is not None:
        return False
    other_task = db.scalars(
        select(Task.meeting_id).where(Task.assignee_id == person_id, Task.meeting_id != meeting_id).limit(1)
    ).first()
    return other_task is None


def merge_same_name_in_meeting(db: Session, meeting_id: int) -> None:
    by_id: dict[int, Person] = {}
    for _link, person in meeting_people(db, meeting_id):
        by_id[person.person_id] = person
    for action in db.scalars(select(Action).where(Action.meeting_id == meeting_id, Action.assignee_id.isnot(None))).all():
        if action.assignee_id is None:
            continue
        person = db.get(Person, action.assignee_id)
        if person is not None:
            by_id[person.person_id] = person
    groups: dict[str, list[Person]] = {}
    for person in by_id.values():
        groups.setdefault(person.name.casefold(), []).append(person)
    for members in groups.values():
        local = [person for person in members if _only_used_in_meeting(db, person.person_id, meeting_id)]
        if len(local) < 2:
            continue
        local.sort(key=lambda person: person.person_id)
        keep = local[0]
        for drop in local[1:]:
            _merge_person_into(db, keep, drop)


def sync_speakers_for_meeting(
    db: Session,
    meeting: Meeting,
    speakers: list | None = None,
    *,
    commit: bool = True,
) -> None:
    names = speaker_labels(speakers if speakers is not None else meeting.transcripts)
    if names:
        meeting.attendees = ", ".join(names)
    if commit:
        db.commit()


def rename_speaker_person(db: Session, meeting: Meeting, from_speaker: str, to_speaker: str) -> None:
    sync_speakers_for_meeting(db, meeting, commit=False)


def match_meeting_person(db: Session, meeting_id: int, name: str) -> Person | None:
    needle = name.strip()
    if not needle:
        return None
    for _link, person in meeting_people(db, meeting_id):
        if names_match(person.name, needle):
            return person
    for action in db.scalars(select(Action).where(Action.meeting_id == meeting_id, Action.assignee_id.isnot(None))).all():
        if not names_match(action.assignee, needle) or action.assignee_id is None:
            continue
        person = db.get(Person, action.assignee_id)
        if person is not None:
            return person
    return None


def _speaker_to_bind(
    meeting: Meeting,
    person: Person,
    speaker_label: str | None,
    assignee_name: str | None,
) -> str | None:
    speakers = speaker_labels(meeting.transcripts)
    for candidate in (speaker_label, assignee_name, person.name):
        needle = (candidate or "").strip()
        if not needle:
            continue
        for speaker in speakers:
            if names_match(speaker, needle):
                return speaker
    return None


def _bind_person_speaker(
    db: Session,
    meeting: Meeting,
    person: Person,
    speaker_label: str | None,
    assignee_name: str | None,
) -> None:
    bind = _speaker_to_bind(meeting, person, speaker_label, assignee_name)
    link_attendee(db, meeting.meeting_id, person.person_id, bind)
    if bind and not names_match(bind, person.name):
        from app.repositories import meetings as meetings_repo

        meetings_repo.replace_speaker_names(db, meeting, {bind: person.name}, commit=False)


def resolve_assignee(
    db: Session,
    *,
    user_id: int,
    meeting: Meeting,
    assignee_id: int | None,
    assignee_name: str | None,
    speaker_label: str | None = None,
    as_attendee: bool = True,
) -> tuple[str | None, int | None]:
    if assignee_id is not None:
        person = get_for_user(db, user_id, assignee_id)
        if person is None:
            return None, None
        _bind_person_speaker(db, meeting, person, speaker_label, assignee_name)
        return person.name, person.person_id

    name = (assignee_name or "").strip()
    if not name:
        return None, None

    matched = match_meeting_person(db, meeting.meeting_id, name) or find_by_name(db, user_id, name)
    if matched is None:
        matched = create_person_flush(db, user_id=user_id, name=name)
    _bind_person_speaker(db, meeting, matched, speaker_label, name)
    return matched.name, matched.person_id


def backfill(db: Session) -> None:
    meetings = list(db.scalars(select(Meeting)).all())
    for meeting in meetings:
        transcripts = list(
            db.scalars(
                select(Transcript)
                .where(Transcript.meeting_id == meeting.meeting_id)
                .order_by(Transcript.seq)
            ).all()
        )
        sync_speakers_for_meeting(db, meeting, transcripts, commit=False)

        actions = list(db.scalars(select(Action).where(Action.meeting_id == meeting.meeting_id)).all())
        for action in actions:
            task = db.get(Task, (action.meeting_id, action.seq))
            if task is None:
                continue
            if not (
                task.assignee_id
                or action.assignee_id
                or (task.assignee or "").strip()
                or (action.assignee or "").strip()
            ):
                continue
            name, person_id = resolve_assignee(
                db,
                user_id=meeting.user_id,
                meeting=meeting,
                assignee_id=task.assignee_id or action.assignee_id,
                assignee_name=task.assignee or action.assignee,
            )
            action.assignee = name
            action.assignee_id = person_id
            task.assignee = name
            task.assignee_id = person_id
        merge_same_name_in_meeting(db, meeting.meeting_id)

    for action in db.scalars(select(Action)).all():
        if db.get(Task, (action.meeting_id, action.seq)) is None:
            action.assignee_id = None

    prune_unassigned_people(db)
    db.commit()
