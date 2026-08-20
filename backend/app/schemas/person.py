from pydantic import BaseModel, Field


class PersonOut(BaseModel):
    person_id: int
    name: str
    note: str | None = None
    label: str
    attendee: bool = False


class PersonCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    note: str | None = Field(default=None, max_length=255)


class PersonUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    note: str | None = Field(default=None, max_length=255)


class PersonListOut(BaseModel):
    items: list[PersonOut]
