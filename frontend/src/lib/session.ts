const KEY = "jobe.session";

export type Session = {
  profileId: string | null;
  roleId: string | null;
};

export function readSession(): Session {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return { profileId: null, roleId: "role_llm_app" };
    return JSON.parse(raw) as Session;
  } catch {
    return { profileId: null, roleId: "role_llm_app" };
  }
}

export function writeSession(next: Session): void {
  sessionStorage.setItem(KEY, JSON.stringify(next));
}
