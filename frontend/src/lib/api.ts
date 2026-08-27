export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const TOKEN_KEY = "access_token";

export type AuthUser = {
  user_id: number;
  name: string;
  email: string;
};

export type TokenResponse = {
  access_token: string;
  token_type: string;
  user: AuthUser;
};

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setSession(data: TokenResponse): void {
  localStorage.setItem(TOKEN_KEY, data.access_token);
}

export function clearSession(): void {
  localStorage.removeItem(TOKEN_KEY);
}

async function readError(response: Response): Promise<string> {
  const data: unknown = await response.json().catch(() => null);
  if (data && typeof data === "object" && "detail" in data) {
    const detail = (data as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail[0] && typeof detail[0] === "object" && "msg" in detail[0]) {
      return String((detail[0] as { msg: unknown }).msg);
    }
  }
  return "İstek başarısız";
}

export async function registerUser(body: {
  name: string;
  email: string;
  password: string;
}): Promise<TokenResponse> {
  const response = await fetch(`${API_URL}/api/v1/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export async function loginUser(body: {
  email: string;
  password: string;
}): Promise<TokenResponse> {
  const response = await fetch(`${API_URL}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export async function requestPasswordReset(email: string): Promise<{ message: string; reset_url: string | null }> {
  const response = await fetch(`${API_URL}/api/v1/auth/forgot-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export async function resetPassword(body: { token: string; password: string }): Promise<TokenResponse> {
  const response = await fetch(`${API_URL}/api/v1/auth/reset-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export async function fetchMe(token: string): Promise<AuthUser> {
  const response = await fetch(`${API_URL}/api/v1/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export async function updateProfile(name: string): Promise<AuthUser> {
  const response = await fetch(`${API_URL}/api/v1/auth/me`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeader() },
    body: JSON.stringify({ name }),
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export async function changePassword(body: {
  current_password: string;
  new_password: string;
}): Promise<AuthUser> {
  const response = await fetch(`${API_URL}/api/v1/auth/change-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader() },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export type MeetingStatus = "uploaded" | "transcribed" | "analyzed" | "failed";
export type TaskStatus = "in_progress" | "done";

export type Person = {
  person_id: number;
  name: string;
  note: string | null;
  label: string;
  attendee?: boolean;
  meetings?: { meeting_id: number; title: string; date: string | null }[];
};

export type Meeting = {
  meeting_id: number;
  title: string;
  date: string | null;
  status: MeetingStatus;
  duration: number | null;
  attendees: string | null;
  named_attendees?: string | null;
  description: string | null;
  language?: "tr" | "en";
  audio_path: string | null;
};

export type TranscriptFlag = {
  original: string;
  suggestion: string;
  reason: string;
};

export type TranscriptLine = {
  seq: number;
  timestamp: number;
  text: string;
  speaker: string | null;
  speaker_origin?: string | null;
  flags?: TranscriptFlag[];
};

export type ActionItem = {
  seq: number;
  description: string;
  assignee: string | null;
  assignee_id: number | null;
  due_date: string | null;
  notes: string;
  task_status: TaskStatus | null;
};

export type Decision = {
  seq?: number | null;
  text: string;
  source_seq: number | null;
  source_end_seq?: number | null;
  timestamp: number | null;
  end_timestamp?: number | null;
  speaker: string | null;
};

export type MeetingDetail = Meeting & {
  transcript: TranscriptLine[];
  summary: string | null;
  decisions: Decision[];
  actions: ActionItem[];
  people?: Person[];
  transcription: {
    progress: number;
    message: string;
    error: string | null;
    elapsed_seconds: number;
  } | null;
};

function authHeader(): HeadersInit {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function fetchMeetings(): Promise<Meeting[]> {
  const response = await fetch(`${API_URL}/api/v1/meetings`, {
    headers: authHeader(),
  });
  if (!response.ok) throw new Error(await readError(response));
  const data: { items: Meeting[] } = await response.json();
  return data.items;
}

export async function fetchMeeting(id: number): Promise<MeetingDetail> {
  const response = await fetch(`${API_URL}/api/v1/meetings/${id}`, {
    headers: authHeader(),
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export async function fetchMeetingAudioUrl(id: number): Promise<string> {
  const response = await fetch(`${API_URL}/api/v1/meetings/${id}/audio`, {
    headers: authHeader(),
  });
  if (!response.ok) throw new Error(await readError(response));
  const blob = await response.blob();
  return URL.createObjectURL(blob);
}

export async function createMeeting(body: {
  title: string;
  date: string;
  attendees: string;
  description: string;
  language: "tr" | "en";
  audio: File;
}): Promise<Meeting> {
  const form = new FormData();
  form.append("title", body.title);
  form.append("date", body.date);
  form.append("attendees", body.attendees);
  form.append("description", body.description);
  form.append("language", body.language);
  form.append("audio", body.audio);
  const response = await fetch(`${API_URL}/api/v1/meetings`, {
    method: "POST",
    headers: authHeader(),
    body: form,
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export async function updateMeeting(
  id: number,
  body: { title: string; date: string; attendees?: string; named_attendees?: string; description?: string },
): Promise<Meeting> {
  const response = await fetch(`${API_URL}/api/v1/meetings/${id}`, {
    method: "PATCH",
    headers: { ...authHeader(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export async function renameMeetingSpeaker(
  id: number,
  body: {
    speaker?: string;
    seq?: number;
    from_speaker?: string;
    action?: "confirm" | "reject";
  },
): Promise<MeetingDetail> {
  const response = await fetch(`${API_URL}/api/v1/meetings/${id}/speakers`, {
    method: "PATCH",
    headers: { ...authHeader(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export async function updateTranscriptLine(
  id: number,
  body: { seq: number; text: string; flags?: TranscriptFlag[] | null },
): Promise<MeetingDetail> {
  const response = await fetch(`${API_URL}/api/v1/meetings/${id}`, {
    method: "PATCH",
    headers: { ...authHeader(), "Content-Type": "application/json" },
    body: JSON.stringify({ update_transcript: body }),
  });
  if (!response.ok) throw new Error(await readError(response));
  return fetchMeeting(id);
}

export async function updateMeetingSummary(id: number, summary: string): Promise<MeetingDetail> {
  const response = await fetch(`${API_URL}/api/v1/meetings/${id}`, {
    method: "PATCH",
    headers: { ...authHeader(), "Content-Type": "application/json" },
    body: JSON.stringify({ summary }),
  });
  if (!response.ok) throw new Error(await readError(response));
  return fetchMeeting(id);
}

export async function updateMeetingDecision(id: number, seq: number, text: string): Promise<MeetingDetail> {
  const response = await fetch(`${API_URL}/api/v1/meetings/${id}`, {
    method: "PATCH",
    headers: { ...authHeader(), "Content-Type": "application/json" },
    body: JSON.stringify({ update_decision: { seq, text } }),
  });
  if (!response.ok) throw new Error(await readError(response));
  return fetchMeeting(id);
}

export async function updateMeetingAction(
  id: number,
  body: {
    seq: number;
    description?: string;
    assignee?: string | null;
    assignee_id?: number | null;
    due_date?: string | null;
    notes?: string | null;
  },
): Promise<void> {
  const response = await fetch(`${API_URL}/api/v1/meetings/${id}`, {
    method: "PATCH",
    headers: { ...authHeader(), "Content-Type": "application/json" },
    body: JSON.stringify({ update_action: body }),
  });
  if (!response.ok) throw new Error(await readError(response));
}

export async function dismissMeetingAction(id: number, seq: number): Promise<MeetingDetail> {
  const response = await fetch(`${API_URL}/api/v1/meetings/${id}`, {
    method: "PATCH",
    headers: { ...authHeader(), "Content-Type": "application/json" },
    body: JSON.stringify({ dismiss_action: seq }),
  });
  if (!response.ok) throw new Error(await readError(response));
  return fetchMeeting(id);
}

export async function analyzeMeeting(id: number): Promise<MeetingDetail> {
  const response = await fetch(`${API_URL}/api/v1/meetings/${id}/analyze`, {
    method: "POST",
    headers: authHeader(),
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export async function deleteMeeting(id: number): Promise<void> {
  const response = await fetch(`${API_URL}/api/v1/meetings/${id}`, {
    method: "DELETE",
    headers: authHeader(),
  });
  if (!response.ok) throw new Error(await readError(response));
}

export type Task = {
  meeting_id: number;
  action_seq: number;
  title: string;
  status: TaskStatus;
  assignee: string | null;
  assignee_id: number | null;
  due_date: string | null;
  description: string;
  notes?: string;
  meeting_title: string;
};

export async function fetchTasks(): Promise<Task[]> {
  const data = await fetchTaskBoard();
  return data.items;
}

export type SuggestedAction = {
  meeting_id: number;
  action_seq: number;
  title: string;
  assignee: string | null;
  assignee_id: number | null;
  due_date: string | null;
  description: string;
  meeting_title: string;
};

function withDateOnly<T extends { due_date?: string | null }>(row: T): T {
  if (!row.due_date) return row;
  return { ...row, due_date: row.due_date.slice(0, 10) };
}

export async function fetchTaskBoard(): Promise<{ items: Task[]; suggestions: SuggestedAction[]; people: Person[] }> {
  const response = await fetch(`${API_URL}/api/v1/tasks`, {
    headers: authHeader(),
  });
  if (!response.ok) throw new Error(await readError(response));
  const data: { items: Task[]; suggestions?: SuggestedAction[]; people?: Person[] } = await response.json();
  return {
    items: data.items.map(withDateOnly),
    suggestions: (data.suggestions ?? []).map(withDateOnly),
    people: data.people ?? [],
  };
}

export async function updateTask(
  meetingId: number,
  actionSeq: number,
  body: Partial<Pick<Task, "title" | "status" | "assignee" | "assignee_id" | "due_date" | "description">>,
): Promise<Task> {
  const response = await fetch(`${API_URL}/api/v1/tasks/${meetingId}/${actionSeq}`, {
    method: "PATCH",
    headers: { ...authHeader(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await readError(response));
  return withDateOnly(await response.json());
}

export async function deleteTask(meetingId: number, actionSeq: number): Promise<void> {
  const response = await fetch(`${API_URL}/api/v1/tasks/${meetingId}/${actionSeq}`, {
    method: "DELETE",
    headers: authHeader(),
  });
  if (!response.ok) throw new Error(await readError(response));
}

export async function createTask(body: {
  meeting_id: number;
  title: string;
  assignee: string;
  assignee_id?: number | null;
  due_date: string;
  description: string;
  action_seq?: number;
}): Promise<Task> {
  const response = await fetch(`${API_URL}/api/v1/tasks`, {
    method: "POST",
    headers: { ...authHeader(), "Content-Type": "application/json" },
    body: JSON.stringify({
      ...body,
      assignee: body.assignee || null,
      assignee_id: body.assignee_id ?? null,
      due_date: body.due_date,
    }),
  });
  if (!response.ok) throw new Error(await readError(response));
  return withDateOnly(await response.json());
}

export async function fetchPeople(meetingId?: number): Promise<Person[]> {
  const query = meetingId ? `?meeting_id=${meetingId}` : "";
  const response = await fetch(`${API_URL}/api/v1/people${query}`, {
    headers: authHeader(),
  });
  if (!response.ok) throw new Error(await readError(response));
  const data: { items: Person[] } = await response.json();
  return data.items;
}

export async function createPerson(body: { name: string; note?: string }): Promise<Person> {
  const response = await fetch(`${API_URL}/api/v1/people`, {
    method: "POST",
    headers: { ...authHeader(), "Content-Type": "application/json" },
    body: JSON.stringify({
      name: body.name.trim(),
      note: body.note?.trim() || null,
    }),
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export async function updatePerson(
  personId: number,
  body: { name?: string; note?: string | null },
): Promise<Person> {
  const response = await fetch(`${API_URL}/api/v1/people/${personId}`, {
    method: "PATCH",
    headers: { ...authHeader(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export async function deletePerson(personId: number): Promise<void> {
  const response = await fetch(`${API_URL}/api/v1/people/${personId}`, {
    method: "DELETE",
    headers: authHeader(),
  });
  if (!response.ok) throw new Error(await readError(response));
}

export async function ensurePerson(
  personId: number | null,
  name: string,
  note?: string,
): Promise<{ assignee: string; assignee_id: number | null }> {
  if (personId) return { assignee_id: personId, assignee: name };
  const trimmed = name.trim();
  if (!trimmed) return { assignee_id: null, assignee: "" };
  const extra = note?.trim();
  if (!extra) return { assignee_id: null, assignee: trimmed };
  const person = await createPerson({ name: trimmed, note: extra });
  return { assignee_id: person.person_id, assignee: person.name };
}
