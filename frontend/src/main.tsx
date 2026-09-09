import React, { CSSProperties, FormEvent, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import packageInfo from "../package.json";
import "./style.css";

type Project = { id: number; key: string; name: string; description: string; color?: string; archived: boolean; todo_count: number; done_count: number; last_activity_at: string };
type Activity = { id: number; actor?: string; author?: string; type?: string; body?: string; created_at: string };
type Task = { id: number; title: string; description: string; status: "TODO" | "DONE"; priority: string; target_project: string; origin_project: string; tags: string[]; comments: Activity[]; events: Activity[]; updated_at: string };

const priorities = ["LOW", "NORMAL", "HIGH", "URGENT"];
const relative = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
const seenKey = "taskrelay-project-seen";
const neutralProjectColor = "#8b8175";

function updatedAgo(value: string) {
  const seconds = Math.round((new Date(value).getTime() - Date.now()) / 1000);
  if (Math.abs(seconds) < 60) return relative.format(seconds, "second");
  if (Math.abs(seconds) < 3600) return relative.format(Math.round(seconds / 60), "minute");
  if (Math.abs(seconds) < 86400) return relative.format(Math.round(seconds / 3600), "hour");
  return relative.format(Math.round(seconds / 86400), "day");
}

function projectColor(color?: string) { return /^#[0-9a-f]{6}$/i.test(color || "") ? color : neutralProjectColor; }

function taskTone(task: Task): CSSProperties {
  const days = Math.max(0, Math.min(14, (Date.now() - new Date(task.updated_at).getTime()) / 86_400_000));
  const [hue, saturation] = ({ LOW: [210, 24], NORMAL: [215, 13], HIGH: [38, 52], URGENT: [4, 48] } as Record<string, [number, number]>)[task.priority] || [215, 13];
  return { "--task-hue": hue, "--task-saturation": `${saturation}%`, "--task-tint": `${4 + (days / 14) * 10}%` } as CSSProperties;
}

function Dialog({ open, onClose, className, label, children }: { open: boolean; onClose: () => void; className: string; label: string; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);
  return <dialog ref={ref} className={className} aria-label={label} onCancel={(event) => { event.preventDefault(); onClose(); }} onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>{children}</dialog>;
}

function readSeen(): Record<string, string> { try { return JSON.parse(localStorage.getItem(seenKey) || "{}"); } catch { return {}; } }

function App() {
  const [token, setToken] = useState(localStorage.getItem("taskrelay-token") || "");
  const [projects, setProjects] = useState<Project[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [project, setProject] = useState(() => new URLSearchParams(location.search).get("project") || "");
  const [tag, setTag] = useState(""); const [priority, setPriority] = useState(""); const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Task | null>(null); const [creating, setCreating] = useState(false); const [projectForm, setProjectForm] = useState<Project | null | undefined>(undefined);
  const [quickTitle, setQuickTitle] = useState(""); const [summary, setSummary] = useState(""); const [changed, setChanged] = useState<number[]>([]); const [error, setError] = useState("");
  const [showArchived, setShowArchived] = useState(false); const [seen, setSeen] = useState(readSeen);
  const requestNumber = useRef(0); const knownUpdates = useRef(new Map<number, string>()); const knownProject = useRef(""); const changedTimer = useRef<number | undefined>(undefined);
  const request = async (path: string, init: RequestInit = {}) => { const response = await fetch(path, { ...init, headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}`, ...init.headers } }); if (!response.ok) throw new Error((await response.json()).detail || response.statusText); return response.status === 204 ? null : response.json(); };
  const saveSeen = (next: Record<string, string>) => { localStorage.setItem(seenKey, JSON.stringify(next)); setSeen(next); };
  const refresh = async () => {
    if (!token) return; localStorage.setItem("taskrelay-token", token); const number = ++requestNumber.current;
    try {
      const nextProjects: Project[] = await request(`/api/projects?include_archived=${showArchived}`);
      const nextTasks: Task[] = project ? await request(`/api/tasks?project=${encodeURIComponent(project)}&limit=200`) : [];
      if (number !== requestNumber.current) return;
      if (localStorage.getItem(seenKey) === null) saveSeen(Object.fromEntries(nextProjects.map((item) => [item.key, item.last_activity_at])));
      else if (project) { const focused = nextProjects.find((item) => item.key === project); if (focused) saveSeen({ ...readSeen(), [project]: focused.last_activity_at }); }
      if (project) { const advanced = knownProject.current === project ? nextTasks.filter((item) => !knownUpdates.current.has(item.id) || knownUpdates.current.get(item.id)! < item.updated_at).map((item) => item.id) : []; knownUpdates.current = new Map(nextTasks.map((item) => [item.id, item.updated_at])); knownProject.current = project; if (advanced.length) { setChanged(advanced); window.clearTimeout(changedTimer.current); changedTimer.current = window.setTimeout(() => setChanged([]), 1800); } } else { knownUpdates.current.clear(); knownProject.current = ""; }
      setProjects(nextProjects); setTasks(nextTasks); setError("");
    } catch (reason) { if (number === requestNumber.current) setError(String(reason)); }
  };
  useEffect(() => { void refresh(); }, [token, project, showArchived]);
  useEffect(() => { if (!token) return; const onFocus = () => void refresh(); const timer = window.setInterval(() => void refresh(), 5000); window.addEventListener("focus", onFocus); return () => { window.clearInterval(timer); window.removeEventListener("focus", onFocus); }; }, [token, project, showArchived]);
  useEffect(() => { const onPopState = () => setProject(new URLSearchParams(location.search).get("project") || ""); window.addEventListener("popstate", onPopState); return () => window.removeEventListener("popstate", onPopState); }, []);
  const chooseProject = (key: string) => { history.pushState({ taskrelayProject: !!key }, "", key ? `${location.pathname}?project=${encodeURIComponent(key)}` : location.pathname); setProject(key); setSelected(null); setTag(""); setPriority(""); setQuery(""); };
  const backToProjects = () => { if (history.state?.taskrelayProject) history.back(); else chooseProject(""); };
  const tags = useMemo(() => [...new Set(tasks.flatMap((task) => task.tags))].sort(), [tasks]);
  const visible = tasks.filter((task) => (!tag || task.tags.includes(tag)) && (!priority || task.priority === priority) && (!query || `${task.title} ${task.description}`.toLowerCase().includes(query.toLowerCase())));
  const todo = visible.filter((item) => item.status === "TODO");
  const done = visible.filter((item) => item.status === "DONE");
  const focused = projects.find((item) => item.key === project);
  const canCreateInFocused = !!focused && !focused.archived;
  const save = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); if (!selected) return; const data = new FormData(event.currentTarget); const updated = await request(`/api/tasks/${selected.id}`, { method: "PATCH", body: JSON.stringify({ title: data.get("title"), description: data.get("description"), priority: data.get("priority"), tags: String(data.get("tags") || "").split(","), target_project: data.get("target_project") }) }); setSelected(updated); await refresh(); };
  const complete = async () => { if (!selected || !summary.trim()) { setError("Completion summary is required."); return; } const updated = await request(`/api/tasks/${selected.id}/complete`, { method: "POST", body: JSON.stringify({ summary }) }); setSelected(updated); setSummary(""); await refresh(); };
  const quickAdd = async (event: FormEvent) => { event.preventDefault(); if (!canCreateInFocused || !quickTitle.trim()) return; await request("/api/tasks", { method: "POST", body: JSON.stringify({ title: quickTitle, target_project: project, origin_project: project }) }); setQuickTitle(""); await refresh(); };
  const create = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const data = new FormData(event.currentTarget); const target = String(data.get("target_project") || ""); const targetProject = projects.find((item) => item.key === target); if ((project && !canCreateInFocused) || !targetProject || targetProject.archived) { setError("Choose an active project for the new task."); return; } await request("/api/tasks", { method: "POST", body: JSON.stringify({ title: data.get("title"), target_project: target, origin_project: target }) }); setCreating(false); await refresh(); };
  const saveProject = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const data = new FormData(event.currentTarget); const body = { name: data.get("name"), description: data.get("description"), color: data.get("color") || null }; if (projectForm) await request(`/api/projects/${projectForm.key}`, { method: "PATCH", body: JSON.stringify(body) }); else await request("/api/projects", { method: "POST", body: JSON.stringify({ ...body, key: data.get("key") }) }); setProjectForm(undefined); await refresh(); };
  const archive = async () => { if (!project) return; const item = projects.find((candidate) => candidate.key === project); await request(`/api/projects/${project}`, { method: "PATCH", body: JSON.stringify({ archived: !item?.archived }) }); if (!item?.archived) chooseProject(""); await refresh(); };
  const taskRow = (item: Task) => <button className={`task ${changed.includes(item.id) ? "changed" : ""}`} key={item.id} onClick={() => { setSelected(item); setSummary(""); }} style={taskTone(item)}><span className={`priority ${item.priority.toLowerCase()}`}>{item.priority}</span><strong>{item.title}</strong>{item.description && <span className="task-description">{item.description}</span>}<span className="task-meta">{item.tags.map((value) => <em key={value}>{value}</em>)}{item.origin_project !== item.target_project && <em>from {item.origin_project}</em>}</span><small>Updated {updatedAgo(item.updated_at)}</small></button>;
  if (!token) return <main className="login"><h1>TaskRelay</h1><p>Workspace bearer token</p><input aria-label="Workspace bearer token" type="password" onKeyDown={(event) => event.key === "Enter" && setToken(event.currentTarget.value)} autoFocus /></main>;
  return <main><header><div className="brand"><h1><span>Task</span><strong>Relay</strong><sub>v{packageInfo.version}</sub></h1><small>{focused?.name || (project ? project : "Projects")}</small></div><div>{project && <><button className="quiet" onClick={() => setProjectForm(focused)}>Edit project</button><button className="quiet" onClick={() => void archive()}>{focused?.archived ? "Unarchive" : "Archive"}</button></>}{(!project || canCreateInFocused) && <button onClick={() => setCreating(true)}>+ Task</button>}{!project && <button onClick={() => setProjectForm(null)}>+ Project</button>}<button className="quiet" onClick={() => { localStorage.removeItem("taskrelay-token"); setToken(""); }}>Lock</button></div></header>{error && <p className="error">{error}</p>}
    {!project ? <><label className="archived-toggle"><input type="checkbox" checked={showArchived} onChange={(event) => setShowArchived(event.target.checked)} /> Show archived</label><section className="projects">{projects.map((item) => <button className="project-card" key={item.id} onClick={() => chooseProject(item.key)} style={{ "--project-color": projectColor(item.color) } as CSSProperties}><strong>{item.name} {(!seen[item.key] || seen[item.key] < item.last_activity_at) && <span className="activity-dot">New activity</span>}</strong>{item.description && <span className="project-description">{item.description}</span>}<span>{item.todo_count} Todo · {item.done_count} Done {item.archived && "· Archived"}</span><small>Updated {updatedAgo(item.last_activity_at)}</small></button>)}{!projects.length && <p className="empty">No projects yet. Create a project to start relaying work.</p>}</section></> : <section className="focused-layout"><div className="work-pane"><nav><button className="quiet" onClick={backToProjects}>← Projects</button><select aria-label="Filter by tag" value={tag} onChange={(event) => setTag(event.target.value)}><option value="">All tags</option>{tags.map((item) => <option key={item}>{item}</option>)}</select><select aria-label="Filter by priority" value={priority} onChange={(event) => setPriority(event.target.value)}><option value="">All priorities</option>{priorities.map((item) => <option key={item}>{item}</option>)}</select><input aria-label="Search tasks" placeholder="Search…" value={query} onChange={(event) => setQuery(event.target.value)} /></nav>{canCreateInFocused && <form className="quick-add" onSubmit={quickAdd}><input aria-label="New task title" placeholder="Add a task…" value={quickTitle} onChange={(event) => setQuickTitle(event.target.value)} required maxLength={240} /><button>Add Todo</button></form>}<section><h2>Todo <small>{todo.length}</small></h2><div className="task-list">{todo.map(taskRow)}{!todo.length && <p className="empty">No Todo tasks match these filters.</p>}</div></section></div><aside className="project-sidebar"><section><h2>{focused?.name || project}</h2>{focused?.description ? <p>{focused.description}</p> : <p className="muted">No project description.</p>}<dl><div><dt>Todo</dt><dd>{focused?.todo_count || 0}</dd></div><div><dt>Done</dt><dd>{focused?.done_count || 0}</dd></div></dl><small>Latest activity {focused ? updatedAgo(focused.last_activity_at) : "unknown"}</small></section><details><summary>Done {done.length}</summary><div className="task-list done-list">{done.map(taskRow)}{!done.length && <p className="empty">No completed tasks yet.</p>}</div></details></aside></section>}
    <Dialog open={!!selected} onClose={() => setSelected(null)} className="drawer" label={selected ? `Task ${selected.id}` : "Task"}>{selected && <><button aria-label="Close task" className="close" onClick={() => setSelected(null)}>×</button><h2>#{selected.id}</h2>{selected.status === "TODO" ? <><form key={selected.id} onSubmit={save}><label>Title<input name="title" defaultValue={selected.title} required maxLength={240} /></label><label>Description<textarea name="description" defaultValue={selected.description} rows={6} /></label><label>Priority<select name="priority" defaultValue={selected.priority}>{priorities.map((item) => <option key={item}>{item}</option>)}</select></label><label>Tags<input name="tags" defaultValue={selected.tags.join(", ")} /></label><label>Target project<select name="target_project" defaultValue={selected.target_project}>{projects.map((item) => <option key={item.id} value={item.key}>{item.name}</option>)}</select></label><p>Origin: {selected.origin_project}</p><button>Save changes</button></form><section className="complete"><label>Completion summary<textarea value={summary} onChange={(event) => setSummary(event.target.value)} required rows={3} /></label><button onClick={() => void complete()}>Complete</button></section></> : <><p>{selected.title}</p><p>{selected.description}</p><p>Completed tasks are read-only. Create a new task for follow-up work.</p></>}<section className="activity"><h3>Activity</h3>{[...selected.events, ...selected.comments].sort((a, b) => a.created_at.localeCompare(b.created_at)).map((item) => <p key={`${item.type || "comment"}-${item.id}`}><strong>{item.actor || item.author}</strong> {item.type || item.body}</p>)}</section></>}</Dialog>
    <Dialog open={creating} onClose={() => setCreating(false)} className="modal" label="New task"><form onSubmit={create}><button type="button" className="close" onClick={() => setCreating(false)}>×</button><h2>New task</h2><label>Title<input name="title" required maxLength={240} /></label><label>Project<select name="target_project" required defaultValue={project}>{!project && <option value="">Choose…</option>}{projects.filter((item) => !item.archived).map((item) => <option key={item.id} value={item.key}>{item.name}</option>)}</select></label><button>Create Todo</button></form></Dialog>
    <Dialog open={projectForm !== undefined} onClose={() => setProjectForm(undefined)} className="modal" label={projectForm ? "Edit project" : "New project"}><form onSubmit={saveProject}><button type="button" className="close" onClick={() => setProjectForm(undefined)}>×</button><h2>{projectForm ? "Edit project" : "New project"}</h2>{!projectForm && <label>Key<input name="key" required pattern="[a-z0-9]+(-[a-z0-9]+)*" maxLength={64} /></label>}<label>Name<input name="name" defaultValue={projectForm?.name} required maxLength={120} /></label><label>Description<textarea name="description" defaultValue={projectForm?.description} rows={4} /></label><label>Color<input type="color" name="color" defaultValue={projectColor(projectForm?.color)} /></label><button>{projectForm ? "Save project" : "Create project"}</button></form></Dialog>
  </main>;
}

createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);
